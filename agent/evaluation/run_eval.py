"""
AGRA — RAG Evaluation Runner (Priority 4)
Runs all 30 evaluation Q&A pairs through the RAG pipeline and computes
RAGAS-equivalent metrics using the local LLM as judge.

Usage:
    cd /workspace/Nothing/agent
    python -m evaluation.run_eval [--limit N]

Outputs a JSON report to evaluation/eval_results.json
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

# Setup path so imports work
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evaluation.metrics import compute_all_metrics

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(name)s │ %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("agra.eval")

_EVAL_DIR = Path(__file__).resolve().parent
_DATASET_PATH = _EVAL_DIR / "eval_dataset.json"
_RESULTS_PATH = _EVAL_DIR / "eval_results.json"


def _load_dataset(limit: int = 0) -> List[Dict[str, Any]]:
    """Load evaluation dataset from JSON file."""
    with open(_DATASET_PATH, "r", encoding="utf-8") as f:
        dataset = json.load(f)
    if limit > 0:
        dataset = dataset[:limit]
    logger.info("Loaded %d evaluation questions.", len(dataset))
    return dataset


def _retrieve_and_answer(question: str) -> Dict[str, Any]:
    """
    Run a question through the RAG retrieval pipeline (synchronous version).
    Returns: {"answer": str, "chunks": List[Dict], "sources": List[Dict]}
    """
    from api.rag import embedder, reranker
    from api.rag.vector_store import get_store
    from api.rag.query_rewriter import rewrite_query
    from api.rag import llm as llm_engine

    store = get_store()

    # 1. Rewrite query
    rewritten = rewrite_query(question)

    # 2. Embed
    query_emb = embedder.embed_query(rewritten)

    # 3. Hybrid search
    candidates = store.hybrid_search(
        query_text=rewritten,
        query_embedding=query_emb,
        top_k=10,
    )

    if not candidates:
        return {"answer": "[No results]", "chunks": [], "sources": []}

    # 4. Rerank → top 5
    top_chunks = reranker.rerank(question, candidates, top_k=5)

    # 5. Build prompt and generate
    context_lines = []
    for i, c in enumerate(top_chunks, 1):
        meta = c.get("metadata", {})
        fname = meta.get("filename", "Unknown")
        page = meta.get("page", "?")
        context_lines.append(f"[{i}] {fname} — Page {page}")
        context_lines.append(c["text"][:500])
        context_lines.append("")

    system_msg = f"""You are AGRA, the AI assistant for Indian Coast Guard Headquarters.
Answer ONLY based on the provided context. Cite sources using [N] notation.

CONTEXT:
{chr(10).join(context_lines)}"""

    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": question},
    ]

    answer = llm_engine.generate(messages, max_tokens=1024, temperature=0.1)

    return {
        "answer": answer,
        "chunks": top_chunks,
        "sources": [c.get("metadata", {}).get("filename", "") for c in top_chunks],
    }


def run_evaluation(limit: int = 0) -> Dict[str, Any]:
    """
    Run full evaluation suite.
    
    Args:
        limit: Maximum number of questions to evaluate (0 = all).
    
    Returns:
        Full evaluation report as a dict.
    """
    # Initialize models
    logger.info("Initializing models for evaluation...")
    from api.rag.vector_store import init_vector_store
    from api.rag.embedder import load_embedder
    from api.rag.reranker import load_reranker
    from api.rag.llm import load_llm

    init_vector_store()
    load_embedder()
    load_reranker()
    load_llm()
    logger.info("All models loaded.")

    dataset = _load_dataset(limit)
    results: List[Dict[str, Any]] = []
    totals = {
        "context_precision": 0.0,
        "context_recall": 0.0,
        "answer_faithfulness": 0.0,
        "answer_relevancy": 0.0,
        "overall": 0.0,
    }

    for i, item in enumerate(dataset, 1):
        qid = item["id"]
        question = item["question"]
        ground_truth = item["ground_truth"]
        expected_source = item.get("expected_source", "")
        category = item.get("category", "")

        logger.info("━━━ [%d/%d] %s ━━━", i, len(dataset), qid)
        logger.info("Q: %s", question)

        start = time.time()
        try:
            rag_result = _retrieve_and_answer(question)
        except Exception as e:
            logger.error("RAG pipeline failed for %s: %s", qid, e)
            results.append({
                "id": qid,
                "question": question,
                "error": str(e),
                "metrics": {k: 0.0 for k in totals},
            })
            continue

        elapsed = time.time() - start

        # Check if expected source was retrieved
        source_hit = any(
            expected_source in s for s in rag_result.get("sources", [])
        ) if expected_source else None

        # Compute metrics
        logger.info("Computing metrics...")
        try:
            metrics = compute_all_metrics(
                question=question,
                answer=rag_result["answer"],
                retrieved_chunks=rag_result["chunks"],
                ground_truth=ground_truth,
            )
        except Exception as e:
            logger.error("Metrics computation failed for %s: %s", qid, e)
            metrics = {k: 0.0 for k in totals}

        for k in totals:
            totals[k] += metrics.get(k, 0.0)

        result = {
            "id": qid,
            "category": category,
            "question": question,
            "expected_source": expected_source,
            "source_retrieved": source_hit,
            "answer_preview": rag_result["answer"][:300],
            "response_time_s": round(elapsed, 2),
            "metrics": metrics,
        }
        results.append(result)

        logger.info(
            "Scores: CP=%.2f CR=%.2f AF=%.2f AR=%.2f | Overall=%.2f | %.1fs",
            metrics["context_precision"],
            metrics["context_recall"],
            metrics["answer_faithfulness"],
            metrics["answer_relevancy"],
            metrics["overall"],
            elapsed,
        )

    # Compute averages
    n = len(dataset)
    averages = {k: round(v / n, 3) if n > 0 else 0.0 for k, v in totals.items()}

    # Source retrieval accuracy
    source_hits = sum(1 for r in results if r.get("source_retrieved") is True)
    source_total = sum(1 for r in results if r.get("source_retrieved") is not None)

    report = {
        "evaluation_date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_questions": n,
        "average_metrics": averages,
        "source_retrieval_accuracy": round(source_hits / source_total, 3) if source_total > 0 else None,
        "per_question_results": results,
    }

    # Save report
    with open(_RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    logger.info("Results saved to %s", _RESULTS_PATH)

    # Print summary
    print("\n" + "=" * 60)
    print("  AGRA RAG EVALUATION REPORT")
    print("=" * 60)
    print(f"  Questions evaluated: {n}")
    print(f"  Source retrieval:    {source_hits}/{source_total} ({report['source_retrieval_accuracy']:.1%})" if source_total else "")
    print(f"  ─────────────────────────────────────")
    print(f"  Context Precision:   {averages['context_precision']:.3f}")
    print(f"  Context Recall:      {averages['context_recall']:.3f}")
    print(f"  Answer Faithfulness: {averages['answer_faithfulness']:.3f}")
    print(f"  Answer Relevancy:    {averages['answer_relevancy']:.3f}")
    print(f"  ─────────────────────────────────────")
    print(f"  OVERALL SCORE:       {averages['overall']:.3f}")
    print("=" * 60)

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AGRA RAG Evaluation Runner")
    parser.add_argument("--limit", type=int, default=0, help="Max questions to evaluate (0=all)")
    args = parser.parse_args()
    run_evaluation(args.limit)

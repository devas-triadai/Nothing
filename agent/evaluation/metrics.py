"""
AGRA — Offline RAG Evaluation Metrics (Priority 4)
Implements RAGAS-equivalent metrics using the local Gemma 4 LLM as the
evaluator judge. No internet connection required.

Metrics:
  1. Context Precision  — Are the retrieved chunks actually relevant?
  2. Context Recall     — Do retrieved chunks cover the ground truth?
  3. Answer Faithfulness — Does the answer stick to retrieved context?
  4. Answer Relevancy   — Does the answer address the question?
"""

import logging
import re
from typing import Any, Dict, List

logger = logging.getLogger("agra.eval.metrics")


def _judge(prompt: str) -> str:
    """Run a short LLM evaluation prompt and return the response."""
    from api.rag import llm as llm_engine
    messages = [{"role": "user", "content": prompt}]
    return llm_engine.generate(messages, max_tokens=256, temperature=0.0)


def _parse_score(response: str) -> float:
    """Extract a numeric score (0-1) from the LLM's evaluation response."""
    # Look for patterns like "Score: 0.8", "0.75", "score=0.9"
    patterns = [
        r'[Ss]core\s*[:=]\s*([01](?:\.\d+)?)',
        r'\b([01](?:\.\d+)?)\s*/\s*1\b',
        r'^([01](?:\.\d+)?)\s*$',
    ]
    for pattern in patterns:
        match = re.search(pattern, response.strip())
        if match:
            return float(match.group(1))
    # Fallback: try to find any float between 0 and 1
    floats = re.findall(r'\b(0\.\d+|1\.0|0|1)\b', response)
    if floats:
        return float(floats[0])
    logger.warning("Could not parse score from: %r", response[:100])
    return 0.0


def context_precision(
    question: str,
    retrieved_chunks: List[Dict[str, Any]],
    ground_truth: str,
) -> float:
    """
    Context Precision: What fraction of retrieved chunks are actually relevant?
    
    Uses the LLM to judge each chunk's relevance to the ground truth answer.
    Returns a score between 0 and 1.
    """
    if not retrieved_chunks:
        return 0.0

    relevant_count = 0
    for i, chunk in enumerate(retrieved_chunks):
        prompt = f"""You are evaluating whether a retrieved text chunk is relevant to answering a question.

QUESTION: {question}

EXPECTED ANSWER: {ground_truth}

RETRIEVED CHUNK #{i+1}:
{chunk.get('text', '')[:500]}

Is this chunk relevant to answering the question? Consider it relevant if it contains information that would help produce the expected answer.

Answer with ONLY a score: 1.0 if relevant, 0.0 if not relevant.
Score:"""
        response = _judge(prompt)
        score = _parse_score(response)
        if score >= 0.5:
            relevant_count += 1

    return relevant_count / len(retrieved_chunks)


def context_recall(
    question: str,
    retrieved_chunks: List[Dict[str, Any]],
    ground_truth: str,
) -> float:
    """
    Context Recall: Does the retrieved context cover all key facts from ground truth?
    
    Asks the LLM to estimate what fraction of the ground truth is covered.
    Returns a score between 0 and 1.
    """
    if not retrieved_chunks:
        return 0.0

    context = "\n---\n".join(
        c.get("text", "")[:400] for c in retrieved_chunks
    )

    prompt = f"""You are evaluating whether retrieved context contains enough information to produce the expected answer.

QUESTION: {question}

EXPECTED ANSWER: {ground_truth}

RETRIEVED CONTEXT:
{context[:2000]}

What fraction of the key facts in the expected answer are present in the retrieved context?
- 1.0 = all key facts are present
- 0.5 = about half the facts are present
- 0.0 = none of the facts are present

Answer with ONLY a decimal score between 0.0 and 1.0.
Score:"""
    response = _judge(prompt)
    return _parse_score(response)


def answer_faithfulness(
    answer: str,
    retrieved_chunks: List[Dict[str, Any]],
) -> float:
    """
    Answer Faithfulness: Does the answer contain ONLY information from the context?
    
    Detects hallucination by checking if the answer sticks to retrieved facts.
    Returns a score between 0 and 1.
    """
    if not answer or not retrieved_chunks:
        return 0.0

    context = "\n---\n".join(
        c.get("text", "")[:400] for c in retrieved_chunks
    )

    prompt = f"""You are evaluating whether an AI answer is faithful to the provided context (no hallucination).

CONTEXT DOCUMENTS:
{context[:2000]}

AI ANSWER:
{answer[:1000]}

Evaluate faithfulness:
- 1.0 = every claim in the answer is supported by the context
- 0.5 = some claims are supported, some are not
- 0.0 = the answer contains mostly unsupported claims

Answer with ONLY a decimal score between 0.0 and 1.0.
Score:"""
    response = _judge(prompt)
    return _parse_score(response)


def answer_relevancy(
    question: str,
    answer: str,
) -> float:
    """
    Answer Relevancy: Does the answer actually address the question?
    
    Returns a score between 0 and 1.
    """
    if not answer:
        return 0.0

    prompt = f"""You are evaluating whether an AI answer is relevant to the question asked.

QUESTION: {question}

AI ANSWER:
{answer[:1000]}

Evaluate relevancy:
- 1.0 = the answer directly and completely addresses the question
- 0.5 = the answer partially addresses the question
- 0.0 = the answer does not address the question at all

Answer with ONLY a decimal score between 0.0 and 1.0.
Score:"""
    response = _judge(prompt)
    return _parse_score(response)


def compute_all_metrics(
    question: str,
    answer: str,
    retrieved_chunks: List[Dict[str, Any]],
    ground_truth: str,
) -> Dict[str, float]:
    """
    Compute all four RAGAS-equivalent metrics for a single Q&A evaluation.
    
    Returns:
        Dict with keys: context_precision, context_recall, 
        answer_faithfulness, answer_relevancy, and overall (average).
    """
    cp = context_precision(question, retrieved_chunks, ground_truth)
    cr = context_recall(question, retrieved_chunks, ground_truth)
    af = answer_faithfulness(answer, retrieved_chunks)
    ar = answer_relevancy(question, answer)

    overall = (cp + cr + af + ar) / 4.0

    return {
        "context_precision": round(cp, 3),
        "context_recall": round(cr, 3),
        "answer_faithfulness": round(af, 3),
        "answer_relevancy": round(ar, 3),
        "overall": round(overall, 3),
    }

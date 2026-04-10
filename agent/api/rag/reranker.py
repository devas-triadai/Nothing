"""
AGRA Phase 2 — RAG: Cross-Encoder Reranker
Loads BAAI/bge-reranker-v2-m3 for high-precision reranking of
candidate chunks before LLM consumption.
"""

import logging
import threading
from pathlib import Path
from typing import Any, Dict, List

import torch

logger = logging.getLogger("agra.reranker")

_MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "models"
_RERANKER_PATH = _MODELS_DIR / "bge-reranker-v2-m3"


class _RerankerSingleton:
    """Thread-safe singleton for the cross-encoder reranker."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._tokenizer = None
                    cls._instance._model = None
        return cls._instance

    def load(self) -> None:
        if self._model is not None:
            return
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        model_path = str(_RERANKER_PATH) if _RERANKER_PATH.exists() else "BAAI/bge-reranker-v2-m3"
        logger.info("Loading reranker from %s …", model_path)
        self._tokenizer = AutoTokenizer.from_pretrained(model_path)
        self._model = AutoModelForSequenceClassification.from_pretrained(model_path)
        self._model.eval()

        if torch.cuda.is_available():
            self._model = self._model.to("cuda")
            logger.info("Reranker loaded on CUDA.")
        else:
            logger.info("Reranker loaded on CPU.")

    def rerank(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Rerank chunks by cross-encoder relevance to the query.

        Args:
            query:  User question.
            chunks: List of dicts with at least "text" key.
            top_k:  Number of top results to return.

        Returns:
            Top-k chunks sorted by reranker score (descending),
            each enriched with a "rerank_score" field.
        """
        if not chunks:
            return []

        if self._model is None:
            self.load()

        pairs = [[query, c["text"]] for c in chunks]

        # Tokenise and score
        inputs = self._tokenizer(
            pairs,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt",
        )
        if torch.cuda.is_available():
            inputs = {k: v.to("cuda") for k, v in inputs.items()}

        with torch.no_grad():
            scores = self._model(**inputs, return_dict=True).logits.view(-1).float()

        scores_list = scores.cpu().tolist()

        # Attach scores and sort
        scored = []
        for chunk, score in zip(chunks, scores_list):
            scored.append({**chunk, "rerank_score": score})

        scored.sort(key=lambda x: x["rerank_score"], reverse=True)
        return scored[:top_k]


# Module-level singleton
_reranker = _RerankerSingleton()


def load_reranker() -> None:
    """Pre-load the reranker model into memory (call at startup)."""
    _reranker.load()


def rerank(
    query: str,
    chunks: List[Dict[str, Any]],
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """Rerank chunks by cross-encoder score. Returns top_k best."""
    return _reranker.rerank(query, chunks, top_k)

"""
AGRA Phase 2 — RAG: Embedding Engine
Loads BAAI/bge-m3 from local disk and exposes a singleton embedder.
Dense embeddings: 1024 dimensions, normalised, multilingual.
"""

import logging
import threading
from pathlib import Path
from typing import List

import numpy as np

logger = logging.getLogger("agra.embedder")

_MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "models"
_BGE_M3_PATH = _MODELS_DIR / "bge-m3"

_BATCH_SIZE = 32


class _EmbedderSingleton:
    """Thread-safe singleton around SentenceTransformer for bge-m3."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._model = None
        return cls._instance

    def load(self) -> None:
        if self._model is not None:
            return
        from sentence_transformers import SentenceTransformer

        model_path = str(_BGE_M3_PATH) if _BGE_M3_PATH.exists() else "BAAI/bge-m3"
        logger.info("Loading embedding model from %s …", model_path)
        self._model = SentenceTransformer(model_path)
        logger.info("Embedding model loaded — dim=%d", self._model.get_sentence_embedding_dimension())

    @property
    def model(self):
        if self._model is None:
            self.load()
        return self._model

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        Embed a list of strings into 1024-d dense vectors.
        Processes in batches of 32, normalises output.
        Returns plain Python lists (JSON-serialisable).
        """
        if not texts:
            return []
        embeddings: np.ndarray = self.model.encode(
            texts,
            batch_size=_BATCH_SIZE,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return embeddings.tolist()

    def embed_query(self, query: str) -> List[float]:
        """Embed a single query string. Convenience wrapper."""
        return self.embed_texts([query])[0]


# Module-level singleton
_embedder = _EmbedderSingleton()


def load_embedder() -> None:
    """Call during startup to pre-load the model into GPU/CPU memory."""
    _embedder.load()


def embed_texts(texts: List[str]) -> List[List[float]]:
    """Embed a batch of texts → list of 1024-d float vectors."""
    return _embedder.embed_texts(texts)


def embed_query(query: str) -> List[float]:
    """Embed a single query → 1024-d float vector."""
    return _embedder.embed_query(query)

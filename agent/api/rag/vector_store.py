"""
AGRA Phase 2 — RAG: Vector Store (Qdrant Embedded + BM25 Hybrid)
Persistent local Qdrant instance at agent/qdrant_storage/.
Hybrid search combines dense cosine similarity (0.6) with BM25 keyword score (0.4).
"""

import logging
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)
from rank_bm25 import BM25Okapi

import os

logger = logging.getLogger("agra.vector_store")

# Persistent storage — survives RunPod restarts
_DATA_DIR = Path(os.environ.get("AGRA_DATA_DIR", "/workspace/agra_data"))
if not _DATA_DIR.exists():
    _DATA_DIR = Path(__file__).resolve().parent.parent.parent / "agra_data"
_STORAGE_DIR = _DATA_DIR / "qdrant_storage"
_COLLECTION = "agra_docs"
_VECTOR_DIM = 1024
_BM25_WEIGHT = 0.4
_DENSE_WEIGHT = 0.6


class VectorStore:
    """Thread-safe singleton wrapping Qdrant embedded + BM25."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._client = None
                    cls._instance._bm25_corpus: List[List[str]] = []
                    cls._instance._bm25_ids: List[str] = []
                    cls._instance._bm25_index: Optional[BM25Okapi] = None
                    cls._instance._chunk_texts: Dict[str, str] = {}
                    cls._instance._chunk_meta: Dict[str, Dict] = {}
        return cls._instance

    def init(self) -> None:
        """Initialise Qdrant client and ensure collection exists."""
        if self._client is not None:
            return
        _STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        logger.info("Initialising Qdrant (embedded) at %s", _STORAGE_DIR)
        self._client = QdrantClient(path=str(_STORAGE_DIR))

        collections = [c.name for c in self._client.get_collections().collections]
        if _COLLECTION not in collections:
            self._client.create_collection(
                collection_name=_COLLECTION,
                vectors_config=VectorParams(
                    size=_VECTOR_DIM,
                    distance=Distance.COSINE,
                ),
            )
            logger.info("Created collection '%s' (dim=%d)", _COLLECTION, _VECTOR_DIM)
        else:
            logger.info("Collection '%s' already exists.", _COLLECTION)

        # Rebuild BM25 index from existing points
        self._rebuild_bm25()

    @property
    def client(self) -> QdrantClient:
        if self._client is None:
            self.init()
        return self._client

    # ── BM25 helpers ──

    def _tokenise(self, text: str) -> List[str]:
        return text.lower().split()

    def _rebuild_bm25(self) -> None:
        """Scan all points in Qdrant and rebuild the in-memory BM25 index."""
        self._bm25_corpus = []
        self._bm25_ids = []
        self._chunk_texts = {}
        self._chunk_meta = {}

        offset = None
        while True:
            results, offset = self.client.scroll(
                collection_name=_COLLECTION,
                limit=500,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            if not results:
                break
            for pt in results:
                pid = str(pt.id)
                text = pt.payload.get("text", "")
                self._bm25_corpus.append(self._tokenise(text))
                self._bm25_ids.append(pid)
                self._chunk_texts[pid] = text
                self._chunk_meta[pid] = pt.payload.get("metadata", {})
            if offset is None:
                break

        if self._bm25_corpus:
            self._bm25_index = BM25Okapi(self._bm25_corpus)
            logger.info("BM25 index rebuilt with %d documents.", len(self._bm25_corpus))
        else:
            self._bm25_index = None

    def _add_to_bm25(self, point_id: str, text: str, metadata: Dict) -> None:
        tokens = self._tokenise(text)
        self._bm25_corpus.append(tokens)
        self._bm25_ids.append(point_id)
        self._chunk_texts[point_id] = text
        self._chunk_meta[point_id] = metadata
        # Rebuild full index (BM25Okapi doesn't support incremental add)
        self._bm25_index = BM25Okapi(self._bm25_corpus)

    def _remove_from_bm25(self, point_ids: List[str]) -> None:
        ids_set = set(point_ids)
        new_corpus, new_ids = [], []
        for i, pid in enumerate(self._bm25_ids):
            if pid not in ids_set:
                new_corpus.append(self._bm25_corpus[i])
                new_ids.append(pid)
            else:
                self._chunk_texts.pop(pid, None)
                self._chunk_meta.pop(pid, None)
        self._bm25_corpus = new_corpus
        self._bm25_ids = new_ids
        self._bm25_index = BM25Okapi(self._bm25_corpus) if self._bm25_corpus else None

    # ── Public API ──

    def upsert_chunks(
        self,
        chunks: List[Dict[str, Any]],
        embeddings: List[List[float]],
    ) -> int:
        """
        Insert or update chunks into Qdrant + BM25 index.
        Returns number of points upserted.
        """
        if not chunks or not embeddings:
            return 0

        points: List[PointStruct] = []
        for chunk, emb in zip(chunks, embeddings):
            point_id = str(uuid.uuid4())
            payload = {
                "text": chunk["text"],
                "metadata": chunk["metadata"],
            }
            points.append(PointStruct(id=point_id, vector=emb, payload=payload))
            self._add_to_bm25(point_id, chunk["text"], chunk["metadata"])

        # Upsert in batches of 100
        for i in range(0, len(points), 100):
            batch = points[i:i + 100]
            self.client.upsert(collection_name=_COLLECTION, points=batch)

        logger.info("Upserted %d chunks into '%s'.", len(points), _COLLECTION)
        return len(points)

    def hybrid_search(
        self,
        query_text: str,
        query_embedding: List[float],
        top_k: int = 10,
        doc_ids_filter: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Hybrid search: dense cosine (weight 0.6) + BM25 keyword (weight 0.4).
        Returns top_k results sorted by combined score.
        """
        # ── Dense Search ──
        qdrant_filter = None
        if doc_ids_filter:
            from qdrant_client.models import MatchAny
            qdrant_filter = Filter(
                must=[FieldCondition(key="metadata.doc_id", match=MatchAny(any=doc_ids_filter))]
            )

        response = self.client.query_points(
            collection_name=_COLLECTION,
            query=query_embedding,
            limit=min(top_k * 3, 50),
            query_filter=qdrant_filter,
            with_payload=True,
        )
        dense_results = response.points

        dense_scores: Dict[str, float] = {}
        result_map: Dict[str, Dict[str, Any]] = {}
        for hit in dense_results:
            pid = str(hit.id)
            dense_scores[pid] = float(hit.score)
            result_map[pid] = {
                "text": hit.payload.get("text", ""),
                "metadata": hit.payload.get("metadata", {}),
                "dense_score": float(hit.score),
            }

        # ── BM25 Search ──
        bm25_scores: Dict[str, float] = {}
        if self._bm25_index and self._bm25_corpus:
            query_tokens = self._tokenise(query_text)
            raw_scores = self._bm25_index.get_scores(query_tokens)
            max_bm25 = max(raw_scores) if max(raw_scores) > 0 else 1.0
            for i, score in enumerate(raw_scores):
                pid = self._bm25_ids[i]
                normalised = float(score) / max_bm25
                bm25_scores[pid] = normalised
                if pid not in result_map:
                    result_map[pid] = {
                        "text": self._chunk_texts.get(pid, ""),
                        "metadata": self._chunk_meta.get(pid, {}),
                        "dense_score": 0.0,
                    }

        # ── Combine scores ──
        combined: List[Dict[str, Any]] = []
        for pid, data in result_map.items():
            # Apply doc_ids filter to BM25 results too
            if doc_ids_filter and data["metadata"].get("doc_id") not in doc_ids_filter:
                continue
            d_score = dense_scores.get(pid, 0.0)
            b_score = bm25_scores.get(pid, 0.0)
            final = _DENSE_WEIGHT * d_score + _BM25_WEIGHT * b_score
            combined.append({
                **data,
                "bm25_score": b_score,
                "combined_score": final,
            })

        combined.sort(key=lambda x: x["combined_score"], reverse=True)
        return combined[:top_k]

    def document_exists(self, filename: str) -> bool:
        """Check if a document with the given filename exists in the store."""
        for meta in self._chunk_meta.values():
            if meta.get("filename") == filename:
                return True
        return False

    def delete_document(self, doc_id: str) -> int:
        """Delete all chunks belonging to a document. Returns count deleted."""
        # Find matching point IDs
        ids_to_delete: List[str] = []
        offset = None
        while True:
            results, offset = self.client.scroll(
                collection_name=_COLLECTION,
                scroll_filter=Filter(
                    must=[FieldCondition(key="metadata.doc_id", match=MatchValue(value=doc_id))]
                ),
                limit=500,
                offset=offset,
                with_payload=False,
            )
            ids_to_delete.extend(str(pt.id) for pt in results)
            if offset is None:
                break

        if ids_to_delete:
            self.client.delete(
                collection_name=_COLLECTION,
                points_selector=ids_to_delete,
            )
            self._remove_from_bm25(ids_to_delete)
            logger.info("Deleted %d chunks for doc_id=%s", len(ids_to_delete), doc_id)

        return len(ids_to_delete)

    def get_chunks_by_doc(self, doc_id: str) -> List[Dict[str, Any]]:
        """Retrieve all chunks for a given document."""
        all_chunks: List[Dict[str, Any]] = []
        offset = None
        while True:
            results, offset = self.client.scroll(
                collection_name=_COLLECTION,
                scroll_filter=Filter(
                    must=[FieldCondition(key="metadata.doc_id", match=MatchValue(value=doc_id))]
                ),
                limit=500,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            for pt in results:
                all_chunks.append({
                    "text": pt.payload.get("text", ""),
                    "metadata": pt.payload.get("metadata", {}),
                })
            if offset is None:
                break
        all_chunks.sort(key=lambda c: c["metadata"].get("chunk_index", 0))
        return all_chunks

    def collection_count(self) -> int:
        """Total number of points in the collection."""
        info = self.client.get_collection(collection_name=_COLLECTION)
        return info.points_count


# ── Module-level convenience ──
_store = VectorStore()


def init_vector_store() -> None:
    _store.init()


def get_store() -> VectorStore:
    if _store._client is None:
        _store.init()
    return _store

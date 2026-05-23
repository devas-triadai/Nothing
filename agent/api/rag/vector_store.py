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
import re
from api.utils.crypto import encrypt_text, decrypt_text

_STOP_WORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "is", "are", "was", "were", 
    "of", "to", "in", "for", "with", "on", "at", "by", "from", "as", "this", "that", 
    "it", "be", "has", "have", "not", "which"
}

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
    _upsert_lock = threading.Lock()

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
        # Lowercase, remove punctuation, split, remove stop words
        clean_text = re.sub(r'[^\w\s]', ' ', text.lower())
        tokens = clean_text.split()
        return [t for t in tokens if t not in _STOP_WORDS and len(t) > 1]

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
                ciphertext = pt.payload.get("text", "")
                text = decrypt_text(ciphertext)
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
        Workstream H: BM25 now rebuilds once after all chunks, not per-chunk.
        """
        if not chunks or not embeddings:
            return 0

        with self._upsert_lock:
            points: List[PointStruct] = []
            for chunk, emb in zip(chunks, embeddings):
                point_id = str(uuid.uuid4())
                payload = {
                    "text": encrypt_text(chunk["text"]),
                    "metadata": chunk["metadata"],
                }
                points.append(PointStruct(id=point_id, vector=emb, payload=payload))
                # Workstream H: Add to corpus arrays WITHOUT rebuilding BM25 per chunk
                tokens = self._tokenise(chunk["text"])
                self._bm25_corpus.append(tokens)
                self._bm25_ids.append(point_id)
                self._chunk_texts[point_id] = chunk["text"]
                self._chunk_meta[point_id] = chunk["metadata"]

            # Upsert in batches of 100
            for i in range(0, len(points), 100):
                batch = points[i:i + 100]
                self.client.upsert(collection_name=_COLLECTION, points=batch)

            # Workstream H: Single BM25 rebuild after ALL chunks are inserted
            if self._bm25_corpus:
                self._bm25_index = BM25Okapi(self._bm25_corpus)
                logger.info("BM25 index rebuilt: %d total docs (added %d).", len(self._bm25_corpus), len(points))
            
            logger.info("Upserted %d chunks into '%s'.", len(points), _COLLECTION)
            return len(points)

    def hybrid_search(
        self,
        query_text: str,
        query_embedding: List[float],
        top_k: int = 10,
        doc_ids_filter: Optional[List[str]] = None,
        date_range: Optional[tuple] = None,
        doc_type: Optional[str] = None,
        version: Optional[int] = None,
        category: Optional[str] = None,
        user_clearance: int = 4,  # Default to max clearance if not provided
    ) -> List[Dict[str, Any]]:
        """
        Hybrid search: dense cosine (weight 0.6) + BM25 keyword (weight 0.4).
        Returns top_k results sorted by combined score.
        """
        # ── Dense Search ──
        must_conditions = []
        if doc_ids_filter:
            from qdrant_client.models import MatchAny
            must_conditions.append(FieldCondition(key="metadata.doc_id", match=MatchAny(any=doc_ids_filter)))
        if doc_type:
            from qdrant_client.models import MatchValue
            must_conditions.append(FieldCondition(key="metadata.document_type", match=MatchValue(value=doc_type)))
        if version is not None:
            from qdrant_client.models import MatchValue
            must_conditions.append(FieldCondition(key="metadata.version", match=MatchValue(value=version)))
        if category:
            from qdrant_client.models import MatchValue
            must_conditions.append(FieldCondition(key="metadata.category", match=MatchValue(value=category)))
        # ── Security Clearance Filter ──
        from qdrant_client.models import Range
        must_conditions.append(FieldCondition(
            key="metadata.clearance_level",
            range=Range(lte=user_clearance)
        ))
            
        qdrant_filter = Filter(must=must_conditions) if must_conditions else None

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
                "text": decrypt_text(hit.payload.get("text", "")),
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
                if score <= 0: continue
                pid = self._bm25_ids[i]
                meta = self._chunk_meta.get(pid, {})
                
                # Apply rich metadata filters to BM25 results as well
                if doc_ids_filter and meta.get("doc_id") not in doc_ids_filter: continue
                if doc_type and meta.get("document_type") != doc_type: continue
                if version is not None and meta.get("version") != version: continue
                if category and meta.get("category") != category: continue
                
                # Security Clearance BM25 Filter
                if meta.get("clearance_level", 1) > user_clearance: continue
                
                normalised = float(score) / max_bm25
                bm25_scores[pid] = normalised
                if pid not in result_map:
                    result_map[pid] = {
                        "text": self._chunk_texts.get(pid, ""),
                        "metadata": self._chunk_meta.get(pid, {}),
                    }

        # ── Reciprocal Rank Fusion (RRF) ──
        # RRF formula: score = 1 / (k + rank_A) + 1 / (k + rank_B)
        k_rrf = 60
        
        dense_ranked = sorted(dense_scores.items(), key=lambda x: x[1], reverse=True)
        dense_ranks = {pid: rank for rank, (pid, _) in enumerate(dense_ranked, start=1)}
        
        bm25_ranked = sorted(bm25_scores.items(), key=lambda x: x[1], reverse=True)
        bm25_ranks = {pid: rank for rank, (pid, _) in enumerate(bm25_ranked, start=1)}

        combined: List[Dict[str, Any]] = []
        for pid, data in result_map.items():
            # Apply doc_ids filter to BM25 results too
            if doc_ids_filter and data["metadata"].get("doc_id") not in doc_ids_filter:
                continue
                
            d_rank = dense_ranks.get(pid, 1000)
            b_rank = bm25_ranks.get(pid, 1000)
            
            rrf_score = (1.0 / (k_rrf + d_rank)) + (1.0 / (k_rrf + b_rank))
            
            combined.append({
                "pid": pid,
                "text": data["text"],
                "metadata": data["metadata"],
                "dense_score": dense_scores.get(pid, 0.0),
                "bm25_score": bm25_scores.get(pid, 0.0),
                "combined_score": rrf_score,
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

    def delete_chunk(self, chunk_id: str) -> bool:
        """
        Delete a single chunk by its point ID.
        Returns True if deleted, False if not found.
        """
        try:
            self.client.delete(
                collection_name=_COLLECTION,
                points_selector=[chunk_id],
            )
            self._remove_from_bm25([chunk_id])
            logger.debug("Deleted chunk %s", chunk_id)
            return True
        except Exception as e:
            logger.warning("Failed to delete chunk %s: %s", chunk_id, e)
            return False

    def update_chunk(self, chunk_id: str, chunk_data: Dict[str, Any]) -> bool:
        """
        Update a chunk's payload (text and metadata) while preserving embedding.
        Note: If text changes significantly, embedding should be recomputed by caller.
        
        Args:
            chunk_id: Point ID of chunk to update
            chunk_data: New chunk data with 'text' and 'metadata'
        
        Returns:
            True if updated successfully
        """
        try:
            from qdrant_client.models import PointStruct
            
            # Get existing point to preserve vector
            existing = self.client.retrieve(
                collection_name=_COLLECTION,
                ids=[chunk_id],
                with_vectors=True
            )
            
            if not existing:
                logger.warning("Chunk %s not found for update", chunk_id)
                return False
            
            existing_point = existing[0]
            vector = existing_point.vector
            
            # Build new payload
            payload = {
                "text": encrypt_text(chunk_data.get("text", "")),
                "metadata": chunk_data.get("metadata", {})
            }
            
            # Upsert with same ID and vector, new payload
            self.client.upsert(
                collection_name=_COLLECTION,
                points=[PointStruct(id=chunk_id, vector=vector, payload=payload)]
            )
            
            # Update BM25 index
            text = chunk_data.get("text", "")
            metadata = chunk_data.get("metadata", {})
            self._chunk_texts[chunk_id] = text
            self._chunk_meta[chunk_id] = metadata
            
            # Rebuild BM25 index (inefficient but necessary for correctness)
            self._rebuild_bm25_from_memory()
            
            logger.debug("Updated chunk %s", chunk_id)
            return True
            
        except Exception as e:
            logger.error("Failed to update chunk %s: %s", chunk_id, e)
            return False

    def _rebuild_bm25_from_memory(self):
        """Rebuild BM25 index from in-memory cache."""
        self._bm25_corpus = []
        self._bm25_ids = []
        
        for pid, text in self._chunk_texts.items():
            tokens = self._tokenise(text)
            self._bm25_corpus.append(tokens)
            self._bm25_ids.append(pid)
        
        if self._bm25_corpus:
            self._bm25_index = BM25Okapi(self._bm25_corpus)

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
            for hit in results:
                all_chunks.append({
                    "text": decrypt_text(hit.payload.get("text", "")),
                    "metadata": hit.payload.get("metadata", {}),
                })
            if offset is None:
                break
        all_chunks.sort(key=lambda c: c["metadata"].get("chunk_index", 0))
        return all_chunks

    def list_unique_documents(self) -> List[Dict[str, Any]]:
        """Return a list of unique document metadata from the store."""
        unique_docs = {}
        for pid, meta in self._chunk_meta.items():
            doc_id = meta.get("doc_id")
            if doc_id and doc_id not in unique_docs:
                unique_docs[doc_id] = {
                    "doc_id": doc_id,
                    "filename": meta.get("filename", "Unknown"),
                    "category": meta.get("category", "General"),
                    "page_count": meta.get("page_count", 0),
                    "chunks": 0,
                }
            if doc_id:
                unique_docs[doc_id]["chunks"] += 1

        return list(unique_docs.values())

    def get_doc_id_by_content_hash(self, content_hash: str) -> Optional[str]:
        """
        Find a document ID by its content hash (SHA256).
        Returns the doc_id if found, None otherwise.
        """
        if not content_hash:
            return None
        for pid, meta in self._chunk_meta.items():
            if meta.get("content_hash") == content_hash:
                return meta.get("doc_id")
        return None

    def get_document_metadata(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve metadata for a specific document by doc_id.
        Returns the metadata dict or None if not found.
        """
        for pid, meta in self._chunk_meta.items():
            if meta.get("doc_id") == doc_id:
                return {
                    "doc_id": doc_id,
                    "filename": meta.get("filename", "Unknown"),
                    "pages": meta.get("page_count", 0),
                    "chunks": sum(1 for m in self._chunk_meta.values() if m.get("doc_id") == doc_id),
                    "category": meta.get("category", "General"),
                    "document_type": meta.get("document_type"),
                }
        return None

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

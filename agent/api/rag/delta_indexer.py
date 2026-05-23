"""
Module 7 — Delta Indexing
Efficient document re-indexing: only update changed chunks instead of full re-index.
Uses content hashing + similarity matching for chunk-level diff.
"""

import logging
import hashlib
import numpy as np
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass

from api.rag.vector_store import VectorStore
from api.rag import embedder

logger = logging.getLogger("agra.delta_indexer")

# Similarity threshold for detecting "moved" chunks (same content, different position)
MOVED_CHUNK_SIMILARITY = 0.95

# Max chunk size for hashing (truncate very long chunks)
MAX_CHUNK_HASH_LENGTH = 10000


@dataclass
class ChunkDiffResult:
    """Result of chunk diff computation."""
    to_add: List[Dict[str, Any]]        # New chunks to insert
    to_delete: List[str]                # Chunk IDs to remove
    to_update: List[Dict[str, Any]]     # Modified chunks to update
    unchanged: int                       # Count of unchanged chunks
    stats: Dict[str, Any]               # Detailed statistics


def compute_chunk_fingerprint(text: str) -> str:
    """
    Compute SHA256 hash of normalized chunk text for fingerprinting.
    
    Normalization:
    - Lowercase
    - Normalize whitespace
    - Truncate to MAX_CHUNK_HASH_LENGTH
    """
    # Normalize text
    normalized = text.lower()
    normalized = ' '.join(normalized.split())  # Normalize whitespace
    
    # Truncate if necessary
    if len(normalized) > MAX_CHUNK_HASH_LENGTH:
        normalized = normalized[:MAX_CHUNK_HASH_LENGTH]
    
    # Compute SHA256
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()


def compute_chunk_diff(
    old_chunks: List[Dict[str, Any]],
    new_chunks: List[Dict[str, Any]],
    use_similarity_fallback: bool = True
) -> ChunkDiffResult:
    """
    Compute diff between old and new chunk sets.
    
    Strategy:
    1. Build hash index of old chunks
    2. For each new chunk, check exact hash match
    3. If no exact match, check similarity (moved/rewritten chunk)
    4. Remaining new chunks = truly new
    5. Old chunks not matched = to delete
    
    Args:
        old_chunks: Existing chunks from vector store
        new_chunks: New chunks from re-chunking
        use_similarity_fallback: Enable similarity matching for moved chunks
    
    Returns:
        ChunkDiffResult with categorized chunks
    """
    if not old_chunks and not new_chunks:
        return ChunkDiffResult(
            to_add=[], to_delete=[], to_update=[],
            unchanged=0,
            stats={"reason": "Both chunk lists empty"}
        )
    
    if not old_chunks:
        # All new chunks
        return ChunkDiffResult(
            to_add=new_chunks,
            to_delete=[],
            to_update=[],
            unchanged=0,
            stats={
                "total_new": len(new_chunks),
                "reason": "New document (no old chunks)"
            }
        )
    
    if not new_chunks:
        # Delete all old chunks
        old_ids = [c.get("id") or c.get("chunk_id") for c in old_chunks if c.get("id") or c.get("chunk_id")]
        return ChunkDiffResult(
            to_add=[],
            to_delete=old_ids,
            to_update=[],
            unchanged=0,
            stats={
                "total_deleted": len(old_ids),
                "reason": "All chunks removed"
            }
        )
    
    # Step 1: Index old chunks by content hash
    old_by_hash: Dict[str, Dict] = {}
    old_by_id: Dict[str, Dict] = {}
    
    for chunk in old_chunks:
        chunk_id = chunk.get("id") or chunk.get("chunk_id") or chunk.get("point_id")
        if not chunk_id:
            continue
        
        chunk["_id"] = chunk_id  # Ensure consistent ID field
        old_by_id[chunk_id] = chunk
        
        # Compute hash if not already present
        content_hash = chunk.get("content_hash") or chunk.get("fingerprint")
        if not content_hash:
            content_hash = compute_chunk_fingerprint(chunk.get("text", ""))
            chunk["content_hash"] = content_hash
        
        old_by_hash[content_hash] = chunk
    
    # Step 2: Match new chunks against old
    to_add = []
    to_update = []
    matched_old_ids = set()
    unchanged_count = 0
    
    for new_chunk in new_chunks:
        new_text = new_chunk.get("text", "")
        if not new_text:
            continue
        
        new_hash = compute_chunk_fingerprint(new_text)
        new_chunk["content_hash"] = new_hash
        
        # Try exact hash match
        if new_hash in old_by_hash:
            old_chunk = old_by_hash[new_hash]
            old_id = old_chunk.get("_id")
            
            # Check if text is truly identical (not just hash collision)
            if old_chunk.get("text", "").strip() == new_text.strip():
                matched_old_ids.add(old_id)
                unchanged_count += 1
                continue  # Chunk unchanged
        
        # Step 3: Similarity fallback for moved/rewritten chunks
        if use_similarity_fallback:
            best_match = _find_similar_chunk(new_text, old_by_id, matched_old_ids)
            
            if best_match:
                old_id, similarity = best_match
                matched_old_ids.add(old_id)
                
                # If very similar, treat as update (preserve ID)
                if similarity >= MOVED_CHUNK_SIMILARITY:
                    new_chunk["id"] = old_id  # Reuse old ID
                    to_update.append(new_chunk)
                else:
                    # Similar but different enough to be new
                    to_add.append(new_chunk)
            else:
                # Truly new chunk
                to_add.append(new_chunk)
        else:
            # No similarity matching, treat as new
            to_add.append(new_chunk)
    
    # Step 4: Identify chunks to delete (old chunks not matched)
    to_delete = [
        old_id for old_id in old_by_id.keys()
        if old_id not in matched_old_ids
    ]
    
    stats = {
        "total_old": len(old_chunks),
        "total_new": len(new_chunks),
        "unchanged": unchanged_count,
        "to_add": len(to_add),
        "to_update": len(to_update),
        "to_delete": len(to_delete),
        "change_ratio": (len(to_add) + len(to_update) + len(to_delete)) / max(len(old_chunks), len(new_chunks), 1)
    }
    
    logger.info("Chunk diff computed: %d unchanged, %d add, %d update, %d delete",
               unchanged_count, len(to_add), len(to_update), len(to_delete))
    
    return ChunkDiffResult(
        to_add=to_add,
        to_delete=to_delete,
        to_update=to_update,
        unchanged=unchanged_count,
        stats=stats
    )


def _find_similar_chunk(
    new_text: str,
    old_by_id: Dict[str, Dict],
    already_matched: set,
    top_k: int = 3
) -> Optional[Tuple[str, float]]:
    """
    Find most similar unmatched old chunk using cosine similarity.
    
    Args:
        new_text: Text of new chunk
        old_by_id: Dict of old chunks by ID
        already_matched: Set of already matched old chunk IDs
        top_k: Number of candidates to consider
    
    Returns:
        (old_chunk_id, similarity) or None
    """
    if not old_by_id:
        return None
    
    # Embed new chunk
    try:
        new_embedding = embedder.embed_texts([new_text])[0]
        new_embedding = np.array(new_embedding)
        new_embedding = new_embedding / np.linalg.norm(new_embedding)  # Normalize
    except Exception as e:
        logger.warning("Failed to embed new chunk: %s", e)
        return None
    
    best_match = None
    best_sim = 0.0
    
    # Compare against unmatched old chunks
    for old_id, old_chunk in old_by_id.items():
        if old_id in already_matched:
            continue
        
        old_text = old_chunk.get("text", "")
        if not old_text:
            continue
        
        # Quick text similarity check first (cheap)
        text_sim = _quick_text_similarity(new_text, old_text)
        if text_sim < 0.7:  # Skip if clearly different
            continue
        
        # Full embedding similarity
        try:
            old_embedding = old_chunk.get("embedding")
            if old_embedding is None:
                # Need to compute embedding
                old_embedding = embedder.embed_texts([old_text])[0]
                old_chunk["embedding"] = old_embedding
            
            old_embedding = np.array(old_embedding)
            old_embedding = old_embedding / np.linalg.norm(old_embedding)
            
            sim = float(np.dot(new_embedding, old_embedding))
            
            if sim > best_sim:
                best_sim = sim
                best_match = old_id
                
        except Exception as e:
            logger.debug("Embedding comparison failed: %s", e)
            continue
    
    if best_match and best_sim >= MOVED_CHUNK_SIMILARITY:
        return (best_match, best_sim)
    
    return None


def _quick_text_similarity(text1: str, text2: str) -> float:
    """
    Fast text similarity using Jaccard index on word sets.
    Used as pre-filter before expensive embedding comparison.
    """
    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())
    
    if not words1 or not words2:
        return 0.0
    
    intersection = len(words1 & words2)
    union = len(words1 | words2)
    
    return intersection / union if union > 0 else 0.0


async def delta_index_document(
    doc_id: str,
    new_chunks: List[Dict[str, Any]],
    store: VectorStore,
    metadata: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Perform delta indexing: only update changed chunks.
    
    Args:
        doc_id: Document ID
        new_chunks: New chunks from re-chunking
        store: VectorStore instance
        metadata: Optional document metadata
    
    Returns:
        Result dict with operation counts and statistics
    """
    logger.info("[Delta Index] Starting for doc_id=%s with %d new chunks",
               doc_id, len(new_chunks))
    
    try:
        # Step 1: Retrieve existing chunks
        old_chunks = store.get_chunks_by_doc(doc_id)
        
        if not old_chunks:
            logger.info("[Delta Index] No existing chunks, falling back to full index")
            # Fall back to full indexing
            return await _full_index(doc_id, new_chunks, store, metadata)
        
        logger.info("[Delta Index] Found %d existing chunks", len(old_chunks))
        
        # Step 2: Compute diff
        diff = compute_chunk_diff(old_chunks, new_chunks, use_similarity_fallback=True)
        
        # Step 3: Decide strategy
        change_ratio = diff.stats.get("change_ratio", 1.0)
        
        # If too much changed (>80%), full re-index might be faster
        if change_ratio > 0.8:
            logger.info("[Delta Index] Change ratio %.2f too high, using full re-index", change_ratio)
            # Delete all old first, then full index
            store.delete_document(doc_id)
            return await _full_index(doc_id, new_chunks, store, metadata)
        
        # Step 4: Apply delta operations
        operations = {"deleted": 0, "added": 0, "updated": 0}
        
        # 4a: Delete removed chunks
        if diff.to_delete:
            for chunk_id in diff.to_delete:
                try:
                    store.delete_chunk(chunk_id)
                    operations["deleted"] += 1
                except Exception as e:
                    logger.warning("Failed to delete chunk %s: %s", chunk_id, e)
        
        # 4b: Prepare upsert batch (new + updated chunks)
        chunks_to_upsert = []
        
        # Updated chunks (preserve IDs)
        for chunk in diff.to_update:
            chunks_to_upsert.append(chunk)
            operations["updated"] += 1
        
        # New chunks (need embeddings)
        if diff.to_add:
            texts = [c["text"] for c in diff.to_add]
            embeddings = embedder.embed_texts(texts)
            
            for chunk, embedding in zip(diff.to_add, embeddings):
                chunk["embedding"] = embedding
                chunks_to_upsert.append(chunk)
                operations["added"] += 1
        
        # 4c: Batch upsert
        if chunks_to_upsert:
            embeddings = [c["embedding"] for c in chunks_to_upsert if "embedding" in c]
            
            # Embed any missing
            for i, chunk in enumerate(chunks_to_upsert):
                if "embedding" not in chunk:
                    chunk["embedding"] = embedder.embed_texts([chunk["text"]])[0]
            
            store.upsert_chunks(chunks_to_upsert, [c["embedding"] for c in chunks_to_upsert])
        
        logger.info("[Delta Index] Completed: %s", operations)
        
        return {
            "success": True,
            "method": "delta",
            "doc_id": doc_id,
            "operations": operations,
            "stats": diff.stats,
            "unchanged": diff.unchanged
        }
        
    except Exception as e:
        logger.error("[Delta Index] Failed for doc_id=%s: %s", doc_id, e, exc_info=True)
        
        # Fall back to full index on any error
        logger.info("[Delta Index] Falling back to full index due to error")
        try:
            store.delete_document(doc_id)
            return await _full_index(doc_id, new_chunks, store, metadata)
        except Exception as fallback_e:
            logger.error("[Delta Index] Full index fallback also failed: %s", fallback_e)
            return {
                "success": False,
                "method": "failed",
                "doc_id": doc_id,
                "error": str(e),
                "fallback_error": str(fallback_e)
            }


async def _full_index(
    doc_id: str,
    chunks: List[Dict[str, Any]],
    store: VectorStore,
    metadata: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Perform full document indexing (fallback method).
    """
    if not chunks:
        return {
            "success": True,
            "method": "full",
            "doc_id": doc_id,
            "operations": {"added": 0, "deleted": 0, "updated": 0},
            "stats": {"reason": "No chunks to index"}
        }
    
    # Embed all chunks
    texts = [c["text"] for c in chunks]
    embeddings = embedder.embed_texts(texts)
    
    # Store
    count = store.upsert_chunks(chunks, embeddings)
    
    return {
        "success": True,
        "method": "full",
        "doc_id": doc_id,
        "operations": {"added": len(chunks), "deleted": 0, "updated": 0},
        "stats": {"total_indexed": count}
    }

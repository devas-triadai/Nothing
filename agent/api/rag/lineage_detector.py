"""
Module 7 — Semantic Similarity Lineage Detection
Detects document relationships via cosine similarity ≥ 0.85 threshold.
Uses multi-factor scoring: embedding similarity + metadata overlap.
"""

import logging
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
import difflib
import re

from api.rag.vector_store import VectorStore
from api.rag import embedder

logger = logging.getLogger("agra.lineage_detector")

# Similarity thresholds
SIMILARITY_THRESHOLD = 0.85       # Minimum to flag as candidate
HIGH_CONFIDENCE_THRESHOLD = 0.92  # Auto-accept range
REVIEW_THRESHOLD = 0.85           # Manual review range

# Sampling strategy for centroid computation
CENTROID_SAMPLE_CHUNKS = 3  # First, middle, last chunks


class LineageDetector:
    """
    Detects document lineage relationships via semantic similarity.
    
    Uses a multi-factor scoring approach:
    1. Embedding cosine similarity (primary, 70% weight)
    2. Filename similarity (15% weight)
    3. Metadata overlap - version patterns, dates (15% weight)
    """
    
    def __init__(self, store: VectorStore):
        self.store = store
        self._embedding_cache: Dict[str, np.ndarray] = {}
    
    async def find_lineage_candidates(
        self,
        new_doc_id: str,
        new_doc_chunks: List[Dict[str, Any]],
        new_doc_filename: str,
        new_doc_metadata: Optional[Dict] = None
    ) -> List[Dict[str, Any]]:
        """
        Find potential lineage candidates for a new document.
        
        Args:
            new_doc_id: ID of the new document
            new_doc_chunks: Chunks of the new document
            new_doc_filename: Filename of the new document
            new_doc_metadata: Optional metadata dict (version, date, etc.)
        
        Returns:
            List of candidate dicts with similarity scores and suggested relationships:
            [
                {
                    "doc_id": str,
                    "filename": str,
                    "similarity": float,  # 0.0-1.0
                    "embedding_similarity": float,
                    "filename_similarity": float,
                    "metadata_score": float,
                    "suggested_relationship": str,  # "version", "amendment", "related"
                    "confidence": float,
                    "reasoning": str
                }
            ]
        """
        if not new_doc_chunks:
            logger.warning("No chunks provided for lineage detection: %s", new_doc_id)
            return []
        
        # Compute new document centroid embedding
        new_centroid = self._compute_document_centroid(new_doc_chunks)
        if new_centroid is None:
            logger.warning("Failed to compute centroid for %s", new_doc_id)
            return []
        
        # Get all existing documents from vector store
        existing_docs = self._get_existing_document_centroids()
        
        if not existing_docs:
            logger.info("No existing documents for lineage comparison")
            return []
        
        candidates = []
        
        # Compare against each existing document
        for existing_doc_id, existing_data in existing_docs.items():
            # Skip self-comparison
            if existing_doc_id == new_doc_id:
                continue
            
            try:
                # Compute multi-factor score
                result = self._score_relationship(
                    new_doc_id,
                    new_centroid,
                    new_doc_filename,
                    new_doc_metadata or {},
                    existing_doc_id,
                    existing_data
                )
                
                if result["similarity"] >= SIMILARITY_THRESHOLD:
                    candidates.append(result)
                    
            except Exception as e:
                logger.warning("Error comparing %s vs %s: %s", 
                             new_doc_id, existing_doc_id, e)
                continue
        
        # Sort by similarity descending
        candidates.sort(key=lambda x: x["similarity"], reverse=True)
        
        logger.info("Found %d lineage candidates for %s (top score: %.3f)",
                   len(candidates), new_doc_id, 
                   candidates[0]["similarity"] if candidates else 0.0)
        
        return candidates
    
    def _compute_document_centroid(self, chunks: List[Dict[str, Any]]) -> Optional[np.ndarray]:
        """
        Compute centroid embedding for a document.
        Samples first, middle, and last chunks for efficiency.
        """
        if not chunks:
            return None
        
        # Select representative chunks
        n = len(chunks)
        if n <= CENTROID_SAMPLE_CHUNKS:
            sample_indices = list(range(n))
        else:
            # First, middle, last
            sample_indices = [0, n // 2, n - 1]
        
        # Get embeddings for sample chunks
        sample_embeddings = []
        for idx in sample_indices:
            chunk_text = chunks[idx].get("text", "")
            if chunk_text:
                emb = embedder.embed_texts([chunk_text])[0]
                sample_embeddings.append(emb)
        
        if not sample_embeddings:
            return None
        
        # Compute centroid (mean of sample embeddings)
        centroid = np.mean(sample_embeddings, axis=0)
        
        # Normalize to unit vector
        norm = np.linalg.norm(centroid)
        if norm > 0:
            centroid = centroid / norm
        
        return centroid
    
    def _get_existing_document_centroids(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all existing documents with their centroid embeddings.
        Returns: {doc_id: {"centroid": np.array, "filename": str, "metadata": dict}}
        """
        existing_docs = {}
        
        try:
            # Get all unique documents from vector store
            doc_list = self.store.list_unique_documents()
            
            for doc_info in doc_list:
                doc_id = doc_info.get("doc_id")
                if not doc_id:
                    continue
                
                # Get chunks for this document
                chunks = self.store.get_chunks_by_doc(doc_id)
                if not chunks:
                    continue
                
                # Compute centroid
                centroid = self._compute_document_centroid(chunks)
                if centroid is None:
                    continue
                
                existing_docs[doc_id] = {
                    "centroid": centroid,
                    "filename": doc_info.get("filename", "Unknown"),
                    "metadata": doc_info
                }
                
        except Exception as e:
            logger.error("Error fetching existing documents: %s", e)
        
        return existing_docs
    
    def _score_relationship(
        self,
        new_doc_id: str,
        new_centroid: np.ndarray,
        new_filename: str,
        new_metadata: Dict[str, Any],
        existing_doc_id: str,
        existing_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Compute multi-factor relationship score between two documents.
        
        Weights:
        - Embedding similarity: 70%
        - Filename similarity: 15%
        - Metadata overlap: 15%
        """
        existing_centroid = existing_data["centroid"]
        existing_filename = existing_data["filename"]
        existing_metadata = existing_data.get("metadata", {})
        
        # 1. Embedding cosine similarity (primary signal)
        embedding_sim = float(np.dot(new_centroid, existing_centroid))
        embedding_sim = max(0.0, min(1.0, embedding_sim))  # Clamp to [0,1]
        
        # 2. Filename similarity (Levenshtein-based)
        filename_sim = self._compute_filename_similarity(new_filename, existing_filename)
        
        # 3. Metadata overlap score
        metadata_score = self._compute_metadata_similarity(new_metadata, existing_metadata)
        
        # Weighted combination
        combined_score = (
            0.70 * embedding_sim +
            0.15 * filename_sim +
            0.15 * metadata_score
        )
        
        # Determine relationship type and confidence
        relationship, confidence, reasoning = self._classify_relationship(
            embedding_sim,
            filename_sim,
            metadata_score,
            new_metadata,
            existing_metadata
        )
        
        return {
            "doc_id": existing_doc_id,
            "filename": existing_filename,
            "similarity": round(combined_score, 3),
            "embedding_similarity": round(embedding_sim, 3),
            "filename_similarity": round(filename_sim, 3),
            "metadata_score": round(metadata_score, 3),
            "suggested_relationship": relationship,
            "confidence": round(confidence, 3),
            "reasoning": reasoning
        }
    
    def _compute_filename_similarity(self, filename1: str, filename2: str) -> float:
        """
        Compute similarity between two filenames.
        Uses SequenceMatcher for fuzzy matching.
        """
        # Normalize: lowercase, remove extension
        def normalize(fn):
            fn = fn.lower()
            fn = re.sub(r'\.[^.]+$', '', fn)  # Remove extension
            fn = re.sub(r'[^\w]', '', fn)     # Remove non-alphanumeric
            return fn
        
        norm1 = normalize(filename1)
        norm2 = normalize(filename2)
        
        if not norm1 or not norm2:
            return 0.0
        
        # Sequence similarity
        seq_sim = difflib.SequenceMatcher(None, norm1, norm2).ratio()
        
        # Check for version patterns (e.g., v1, v2, rev1, rev2)
        version_pattern = r'(v|rev|version|update)[\s.-]*(\d+)'
        v1_matches = re.findall(version_pattern, filename1, re.IGNORECASE)
        v2_matches = re.findall(version_pattern, filename2, re.IGNORECASE)
        
        # If both have version patterns and base name matches, boost score
        if v1_matches and v2_matches:
            base1 = re.sub(version_pattern, '', filename1, flags=re.IGNORECASE)
            base2 = re.sub(version_pattern, '', filename2, flags=re.IGNORECASE)
            base_sim = difflib.SequenceMatcher(None, 
                re.sub(r'[^\w]', '', base1.lower()),
                re.sub(r'[^\w]', '', base2.lower())
            ).ratio()
            
            if base_sim > 0.8:
                # Strong version pattern match
                seq_sim = max(seq_sim, 0.9)
        
        return seq_sim
    
    def _compute_metadata_similarity(
        self,
        new_metadata: Dict[str, Any],
        existing_metadata: Dict[str, Any]
    ) -> float:
        """
        Compute similarity based on extracted metadata overlap.
        """
        scores = []
        
        # Compare equipment types
        new_equip = set(new_metadata.get("equipment_types", []))
        existing_equip = set(existing_metadata.get("equipment_types", []))
        if new_equip and existing_equip:
            if new_equip & existing_equip:  # Intersection
                scores.append(1.0)
            else:
                scores.append(0.0)
        
        # Compare ship types
        new_ships = set(new_metadata.get("ship_types", []))
        existing_ships = set(existing_metadata.get("ship_types", []))
        if new_ships and existing_ships:
            overlap = len(new_ships & existing_ships) / max(len(new_ships), len(existing_ships))
            scores.append(overlap)
        
        # Compare regulation categories
        new_cats = set(new_metadata.get("regulation_categories", []))
        existing_cats = set(existing_metadata.get("regulation_categories", []))
        if new_cats and existing_cats:
            overlap = len(new_cats & existing_cats) / max(len(new_cats), len(existing_cats))
            scores.append(overlap)
        
        # Compare version patterns
        new_versions = new_metadata.get("version_refs", [])
        existing_versions = existing_metadata.get("version_refs", [])
        if new_versions and existing_versions:
            # If one is clearly newer version (v2 vs v1), high score
            if self._is_version_sequence(new_versions, existing_versions):
                scores.append(0.9)
        
        if not scores:
            return 0.5  # Neutral if no metadata to compare
        
        return sum(scores) / len(scores)
    
    def _is_version_sequence(self, versions1: List[str], versions2: List[str]) -> bool:
        """
        Check if two version lists suggest a sequential relationship.
        """
        def extract_number(v):
            nums = re.findall(r'\d+', str(v))
            return int(nums[-1]) if nums else 0
        
        nums1 = [extract_number(v) for v in versions1]
        nums2 = [extract_number(v) for v in versions2]
        
        max1 = max(nums1) if nums1 else 0
        max2 = max(nums2) if nums2 else 0
        
        # If versions are sequential (e.g., 1 and 2)
        return abs(max1 - max2) == 1
    
    def _classify_relationship(
        self,
        embedding_sim: float,
        filename_sim: float,
        metadata_score: float,
        new_metadata: Dict[str, Any],
        existing_metadata: Dict[str, Any]
    ) -> Tuple[str, float, str]:
        """
        Classify the relationship type and compute confidence.
        
        Returns: (relationship_type, confidence, reasoning)
        """
        # High embedding similarity + version pattern = likely version
        if embedding_sim >= 0.90 and filename_sim >= 0.8:
            return (
                "version",
                embedding_sim,
                f"High semantic similarity ({embedding_sim:.2f}) with matching filename pattern"
            )
        
        # High embedding but different filename = amendment or related
        if embedding_sim >= 0.85:
            if metadata_score >= 0.8:
                return (
                    "amendment",
                    embedding_sim * 0.9,
                    f"Strong content match ({embedding_sim:.2f}) with metadata overlap"
                )
            else:
                return (
                    "related",
                    embedding_sim * 0.8,
                    f"Content similarity ({embedding_sim:.2f}) but different context"
                )
        
        # Moderate similarity
        if embedding_sim >= 0.80:
            return (
                "potentially_related",
                embedding_sim * 0.7,
                f"Moderate content similarity ({embedding_sim:.2f}), review recommended"
            )
        
        # Below threshold shouldn't reach here, but handle gracefully
        return (
            "unclear",
            embedding_sim * 0.5,
            f"Low similarity ({embedding_sim:.2f}), relationship unclear"
        )
    
    def get_recommendation(
        self,
        candidates: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Generate a recommendation based on top candidates.
        
        Returns:
        {
            "action": "auto_accept" | "review" | "none",
            "primary_candidate": Dict or None,
            "all_candidates": List,
            "reasoning": str
        }
        """
        if not candidates:
            return {
                "action": "none",
                "primary_candidate": None,
                "all_candidates": [],
                "reasoning": "No lineage candidates detected"
            }
        
        top_candidate = candidates[0]
        top_score = top_candidate["similarity"]
        
        if top_score >= HIGH_CONFIDENCE_THRESHOLD:
            return {
                "action": "auto_accept",
                "primary_candidate": top_candidate,
                "all_candidates": candidates,
                "reasoning": f"High confidence match ({top_score:.2f}) with {top_candidate['filename']}"
            }
        elif top_score >= REVIEW_THRESHOLD:
            return {
                "action": "review",
                "primary_candidate": top_candidate,
                "all_candidates": candidates,
                "reasoning": f"Candidate detected ({top_score:.2f}) requiring manual review"
            }
        else:
            return {
                "action": "none",
                "primary_candidate": None,
                "all_candidates": candidates,
                "reasoning": "No significant lineage detected"
            }


async def detect_document_lineage(
    doc_id: str,
    chunks: List[Dict[str, Any]],
    filename: str,
    metadata: Optional[Dict[str, Any]] = None,
    store: Optional[VectorStore] = None
) -> Dict[str, Any]:
    """
    Convenience function for lineage detection.
    
    Args:
        doc_id: Document ID
        chunks: Document chunks
        filename: Document filename
        metadata: Optional extracted metadata
        store: VectorStore instance (creates new if not provided)
    
    Returns:
        Detection result with candidates and recommendation
    """
    if store is None:
        from api.rag.vector_store import get_store
        store = get_store()
    
    detector = LineageDetector(store)
    
    candidates = await detector.find_lineage_candidates(
        doc_id, chunks, filename, metadata
    )
    
    recommendation = detector.get_recommendation(candidates)
    
    return {
        "doc_id": doc_id,
        "filename": filename,
        "candidates_found": len(candidates),
        "candidates": candidates,
        "recommendation": recommendation
    }

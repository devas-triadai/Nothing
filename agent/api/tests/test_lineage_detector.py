"""
Module 7 Phase 2 — Unit Tests for Semantic Similarity Lineage Detection
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import numpy as np
from api.rag.lineage_detector import (
    LineageDetector,
    SIMILARITY_THRESHOLD,
    HIGH_CONFIDENCE_THRESHOLD,
    _compute_filename_similarity,
    _is_version_sequence
)


def test_compute_filename_similarity_exact_match():
    """Test exact filename match."""
    sim = _compute_filename_similarity("SOP_v1.pdf", "SOP_v1.pdf")
    assert sim == 1.0, f"Expected 1.0, got {sim}"


def test_compute_filename_similarity_version_pattern():
    """Test version pattern detection."""
    sim = _compute_filename_similarity("SOP_v1.pdf", "SOP_v2.pdf")
    assert sim >= 0.9, f"Expected high similarity for version pair, got {sim}"


def test_compute_filename_similarity_different_files():
    """Test unrelated files have low similarity."""
    sim = _compute_filename_similarity("fire_safety.pdf", "navigation_rules.pdf")
    assert sim < 0.5, f"Expected low similarity, got {sim}"


def test_compute_filename_similarity_case_insensitive():
    """Test case insensitivity."""
    sim = _compute_filename_similarity("SOP.PDF", "sop.pdf")
    assert sim > 0.9, f"Expected high similarity, got {sim}"


def test_is_version_sequence_consecutive():
    """Test consecutive version detection."""
    assert _is_version_sequence(["v1.0"], ["v2.0"]) == True
    assert _is_version_sequence(["rev1"], ["rev2"]) == True


def test_is_version_sequence_non_consecutive():
    """Test non-consecutive versions."""
    assert _is_version_sequence(["v1.0"], ["v3.0"]) == False
    assert _is_version_sequence(["v1"], ["v5"]) == False


def test_is_version_sequence_same():
    """Test same version."""
    assert _is_version_sequence(["v1.0"], ["v1.0"]) == False  # Same, not sequential


def test_lineage_detector_centroid_computation():
    """Test document centroid computation."""
    # Mock chunks with sample text
    chunks = [
        {"text": "This is the first chunk of the document about fire safety."},
        {"text": "Middle section discussing equipment requirements."},
        {"text": "Final chunk with conclusions and references."}
    ]
    
    detector = LineageDetector(None)  # Store not needed for centroid test
    centroid = detector._compute_document_centroid(chunks)
    
    assert centroid is not None, "Centroid should not be None"
    assert isinstance(centroid, np.ndarray), "Centroid should be numpy array"
    assert len(centroid) > 0, "Centroid should have dimensions"
    
    # Check normalization (should be unit vector)
    norm = np.linalg.norm(centroid)
    assert abs(norm - 1.0) < 0.01, f"Centroid should be unit vector, norm={norm}"


def test_lineage_detector_centroid_empty_chunks():
    """Test centroid with empty chunks."""
    detector = LineageDetector(None)
    centroid = detector._compute_document_centroid([])
    assert centroid is None, "Should return None for empty chunks"


def test_lineage_detector_classification_high_similarity():
    """Test relationship classification for high similarity."""
    detector = LineageDetector(None)
    
    relationship, confidence, reasoning = detector._classify_relationship(
        embedding_sim=0.95,
        filename_sim=0.9,
        metadata_score=0.8,
        new_metadata={},
        existing_metadata={}
    )
    
    assert relationship == "version", f"Expected 'version', got {relationship}"
    assert confidence >= 0.9, f"Expected high confidence, got {confidence}"
    assert "High semantic similarity" in reasoning


def test_lineage_detector_classification_amendment():
    """Test relationship classification for amendment."""
    detector = LineageDetector(None)
    
    relationship, confidence, reasoning = detector._classify_relationship(
        embedding_sim=0.88,
        filename_sim=0.6,
        metadata_score=0.85,
        new_metadata={},
        existing_metadata={}
    )
    
    assert relationship == "amendment", f"Expected 'amendment', got {relationship}"


def test_lineage_detector_classification_related():
    """Test relationship classification for related documents."""
    detector = LineageDetector(None)
    
    relationship, confidence, reasoning = detector._classify_relationship(
        embedding_sim=0.87,
        filename_sim=0.4,
        metadata_score=0.5,
        new_metadata={},
        existing_metadata={}
    )
    
    assert relationship == "related", f"Expected 'related', got {relationship}"


def test_recommendation_auto_accept():
    """Test recommendation for auto-accept threshold."""
    detector = LineageDetector(None)
    
    candidates = [
        {
            "doc_id": "doc1",
            "filename": "SOP_v1.pdf",
            "similarity": HIGH_CONFIDENCE_THRESHOLD + 0.01,
            "confidence": 0.95
        }
    ]
    
    rec = detector.get_recommendation(candidates)
    
    assert rec["action"] == "auto_accept", f"Expected auto_accept, got {rec['action']}"
    assert rec["primary_candidate"] is not None


def test_recommendation_review():
    """Test recommendation for review threshold."""
    detector = LineageDetector(None)
    
    candidates = [
        {
            "doc_id": "doc1",
            "filename": "SOP_v1.pdf",
            "similarity": SIMILARITY_THRESHOLD + 0.01,
            "confidence": 0.87
        }
    ]
    
    rec = detector.get_recommendation(candidates)
    
    assert rec["action"] == "review", f"Expected review, got {rec['action']}"
    assert rec["primary_candidate"] is not None


def test_recommendation_none():
    """Test recommendation when no candidates."""
    detector = LineageDetector(None)
    
    rec = detector.get_recommendation([])
    
    assert rec["action"] == "none", f"Expected none, got {rec['action']}"
    assert rec["primary_candidate"] is None


def test_thresholds_defined():
    """Test that thresholds are properly defined."""
    assert SIMILARITY_THRESHOLD == 0.85, f"Expected 0.85, got {SIMILARITY_THRESHOLD}"
    assert HIGH_CONFIDENCE_THRESHOLD == 0.92, f"Expected 0.92, got {HIGH_CONFIDENCE_THRESHOLD}"


if __name__ == "__main__":
    print("Running Module 7 Phase 2 — Lineage Detector Tests...")
    
    tests = [
        test_compute_filename_similarity_exact_match,
        test_compute_filename_similarity_version_pattern,
        test_compute_filename_similarity_different_files,
        test_compute_filename_similarity_case_insensitive,
        test_is_version_sequence_consecutive,
        test_is_version_sequence_non_consecutive,
        test_is_version_sequence_same,
        test_lineage_detector_centroid_computation,
        test_lineage_detector_centroid_empty_chunks,
        test_lineage_detector_classification_high_similarity,
        test_lineage_detector_classification_amendment,
        test_lineage_detector_classification_related,
        test_recommendation_auto_accept,
        test_recommendation_review,
        test_recommendation_none,
        test_thresholds_defined,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            print(f"  ✓ {test.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  ✗ {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ✗ {test.__name__}: Unexpected error: {e}")
            failed += 1
    
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)

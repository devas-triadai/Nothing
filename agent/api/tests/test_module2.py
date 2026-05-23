"""
Module 2 — Unit Tests for Evaluation Metrics, Citation Validation, Hallucination Detection
Run with: pytest agent/api/tests/test_module2.py -v
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from api.rag.metrics import (
    precision_at_k,
    recall_at_k,
    dcg_at_k,
    ndcg_at_k,
    mean_reciprocal_rank,
    calculate_citation_accuracy,
    calculate_hallucination_rate,
)
from api.rag.citation_validator import extract_citations, validate_citations_against_sources
from api.rag.hallucination_detector import extract_claims, detect_hallucinations


def test_precision_at_k():
    """Test Precision@k calculation."""
    relevant = {"A", "B", "C"}
    retrieved = ["A", "D", "B", "E", "C"]
    
    assert precision_at_k(relevant, retrieved, 1) == 1.0  # First is relevant
    assert precision_at_k(relevant, retrieved, 2) == 0.5  # 1 relevant in top 2
    assert precision_at_k(relevant, retrieved, 3) == 2/3  # 2 relevant in top 3
    assert precision_at_k(relevant, retrieved, 5) == 3/5  # 3 relevant in top 5
    
    # Edge cases
    assert precision_at_k(set(), retrieved, 5) == 0.0  # No relevant items
    assert precision_at_k(relevant, [], 5) == 0.0  # No retrieved items


def test_recall_at_k():
    """Test Recall@k calculation."""
    relevant = {"A", "B", "C", "D"}
    retrieved = ["A", "E", "B", "F", "C"]
    
    assert recall_at_k(relevant, retrieved, 1) == 0.25  # 1/4
    assert recall_at_k(relevant, retrieved, 3) == 0.5   # 2/4
    assert recall_at_k(relevant, retrieved, 5) == 0.75  # 3/4
    
    # Edge cases
    assert recall_at_k(set(), retrieved, 5) == 0.0  # No relevant items


def test_dcg_at_k():
    """Test DCG calculation."""
    # Example from Wikipedia: rel = [3, 2, 3, 0, 1, 2]
    relevance = [3, 2, 3, 0, 1, 2]
    
    dcg = dcg_at_k(relevance, 6)
    # DCG = 3/log2(2) + 2/log2(3) + 3/log2(4) + 0 + 1/log2(6) + 2/log2(7)
    # = 3/1 + 2/1.585 + 3/2 + 0 + 1/2.585 + 2/2.807
    # = 3 + 1.26 + 1.5 + 0 + 0.39 + 0.71
    # ≈ 6.86
    
    assert dcg > 6.0 and dcg < 7.0


def test_ndcg_at_k():
    """Test NDCG calculation."""
    # Perfect ranking
    relevance = [2, 2, 1, 1, 0]
    assert ndcg_at_k(relevance, 5) == 1.0
    
    # Worst ranking
    relevance = [0, 0, 1, 1, 2]
    assert ndcg_at_k(relevance, 5) < 1.0
    
    # Empty
    assert ndcg_at_k([], 5) == 0.0


def test_mean_reciprocal_rank():
    """Test MRR calculation."""
    # First relevant at rank 2, 1, 3
    ranks = [2, 1, 3]
    mrr = mean_reciprocal_rank(ranks)
    expected = (1/2 + 1/1 + 1/3) / 3
    assert abs(mrr - expected) < 0.001
    
    # Empty
    assert mean_reciprocal_rank([]) == 0.0


def test_citation_accuracy():
    """Test citation accuracy calculation."""
    assert calculate_citation_accuracy(10, 10) == 100.0
    assert calculate_citation_accuracy(10, 8) == 80.0
    assert calculate_citation_accuracy(0, 0) == 100.0  # Vacuous case
    assert calculate_citation_accuracy(10, 0) == 0.0


def test_hallucination_rate():
    """Test hallucination rate calculation."""
    assert calculate_hallucination_rate(10, 0) == 0.0
    assert calculate_hallucination_rate(10, 2) == 20.0
    assert calculate_hallucination_rate(0, 0) == 0.0


def test_extract_citations():
    """Test citation extraction from text."""
    text = "The requirement is specified in [1] and [2]. See also [3]."
    
    citations = extract_citations(text)
    
    assert len(citations) == 3
    assert citations[0]["citation_num"] == 1
    assert citations[1]["citation_num"] == 2
    assert citations[2]["citation_num"] == 3


def test_validate_citations_against_sources():
    """Test citation validation."""
    text = "Requirement A is in [1] and requirement B is in [2]."
    
    sources = [
        {"index": 1, "document": "Doc A", "page": 5},
        {"index": 2, "document": "Doc B", "page": 10},
    ]
    
    result = validate_citations_against_sources(text, sources)
    
    assert result["total_citations"] == 2
    assert result["valid_citations"] == 2
    assert result["invalid_citations"] == 0
    assert result["citation_accuracy"] == 100.0


def test_validate_citations_with_invalid():
    """Test validation with invalid citations."""
    text = "See [1], [2], and [99]."
    
    sources = [
        {"index": 1, "document": "Doc A"},
        {"index": 2, "document": "Doc B"},
    ]
    
    result = validate_citations_against_sources(text, sources)
    
    assert result["total_citations"] == 3
    assert result["valid_citations"] == 2
    assert result["invalid_citations"] == 1
    assert result["citation_accuracy"] == 200/3  # 66.67%


def test_extract_claims():
    """Test claim extraction."""
    text = "The system requires Type A detectors. This is important."
    
    claims = extract_claims(text)
    
    assert len(claims) > 0
    # First claim should be about Type A detectors
    assert "Type A detectors" in claims[0]["claim_text"]


def test_detect_hallucinations():
    """Test hallucination detection."""
    text = "The requirement is Type A per [1]. Type B is also acceptable [2]."
    
    sources = [
        {"index": 1, "excerpt": "The requirement is Type A."},
        {"index": 2, "excerpt": "Type B is acceptable for legacy systems."},
    ]
    
    result = detect_hallucinations(text, sources)
    
    assert result["total_claims"] > 0
    assert result["hallucination_rate"] < 50.0  # Most claims should be supported


if __name__ == "__main__":
    print("Running Module 2 unit tests...")
    
    tests = [
        test_precision_at_k,
        test_recall_at_k,
        test_dcg_at_k,
        test_ndcg_at_k,
        test_mean_reciprocal_rank,
        test_citation_accuracy,
        test_hallucination_rate,
        test_extract_citations,
        test_validate_citations_against_sources,
        test_validate_citations_with_invalid,
        test_extract_claims,
        test_detect_hallucinations,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            print(f"  ✓ {test.__name__}")
            passed += 1
        except Exception as e:
            print(f"  ✗ {test.__name__}: {e}")
            failed += 1
    
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)

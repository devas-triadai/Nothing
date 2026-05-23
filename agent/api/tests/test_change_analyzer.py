"""
Module 7 Phase 6 — Unit Tests for Change Analyzer
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from api.rag.change_analyzer import (
    _compute_cache_key,
    _build_structured_diff,
    format_change_summary_for_storage,
    ChangeSummary
)
from datetime import datetime


def test_compute_cache_key_consistency():
    """Test cache key is consistent regardless of order."""
    key1 = _compute_cache_key("doc1", "doc2")
    key2 = _compute_cache_key("doc2", "doc1")
    assert key1 == key2, f"Cache keys should match: {key1} vs {key2}"


def test_compute_cache_key_different():
    """Test different pairs produce different keys."""
    key1 = _compute_cache_key("doc1", "doc2")
    key2 = _compute_cache_key("doc1", "doc3")
    assert key1 != key2, "Different pairs should produce different keys"


def test_build_structured_diff_empty():
    """Test structured diff with empty chunks."""
    diff = _build_structured_diff([], [])
    
    assert diff["stats"]["total_old_chunks"] == 0
    assert diff["stats"]["total_new_chunks"] == 0
    assert diff["stats"]["change_ratio"] == 0.0


def test_build_structured_diff_unchanged():
    """Test structured diff with identical chunks."""
    old_chunks = [{"text": "This is chunk 1"}, {"text": "This is chunk 2"}]
    new_chunks = [{"text": "This is chunk 1"}, {"text": "This is chunk 2"}]
    
    diff = _build_structured_diff(old_chunks, new_chunks)
    
    assert diff["stats"]["unchanged"] == 2
    assert diff["stats"]["added"] == 0
    assert diff["stats"]["removed"] == 0


def test_build_structured_diff_added():
    """Test structured diff with added chunks."""
    old_chunks = [{"text": "Chunk 1"}]
    new_chunks = [{"text": "Chunk 1"}, {"text": "Chunk 2"}]
    
    diff = _build_structured_diff(old_chunks, new_chunks)
    
    assert diff["stats"]["added"] >= 1
    assert len(diff["added_sections"]) > 0


def test_format_change_summary():
    """Test formatting for storage."""
    summary = ChangeSummary(
        summary_text="Test summary",
        major_changes=["Change 1", "Change 2"],
        minor_changes=["Typo fix"],
        impact_assessment="Medium",
        action_required="Review changes",
        confidence=0.85,
        generated_at=datetime.now()
    )
    
    storage_data = format_change_summary_for_storage(summary)
    
    assert storage_data["summary_text"] == "Test summary"
    assert storage_data["impact_assessment"] == "Medium"
    assert storage_data["confidence"] == 0.85
    assert len(storage_data["major_changes"]) == 2


def test_change_summary_structure():
    """Test ChangeSummary dataclass."""
    summary = ChangeSummary(
        summary_text="Test",
        major_changes=[],
        minor_changes=[],
        impact_assessment="Low",
        action_required="None",
        confidence=0.9,
        generated_at=datetime.now()
    )
    
    assert summary.impact_assessment in ["High", "Medium", "Low", "None"]
    assert 0.0 <= summary.confidence <= 1.0


if __name__ == "__main__":
    print("Running Module 7 Phase 6 — Change Analyzer Tests...")
    
    tests = [
        test_compute_cache_key_consistency,
        test_compute_cache_key_different,
        test_build_structured_diff_empty,
        test_build_structured_diff_unchanged,
        test_build_structured_diff_added,
        test_format_change_summary,
        test_change_summary_structure,
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

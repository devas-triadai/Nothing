"""
Module 7 Phase 3 — Unit Tests for Delta Indexing
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from api.rag.delta_indexer import (
    compute_chunk_fingerprint,
    compute_chunk_diff,
    ChunkDiffResult,
    _quick_text_similarity
)


def test_compute_chunk_fingerprint_consistency():
    """Test that same text produces same fingerprint."""
    text1 = "This is a test chunk about fire safety."
    text2 = "This is a test chunk about fire safety."
    
    fp1 = compute_chunk_fingerprint(text1)
    fp2 = compute_chunk_fingerprint(text2)
    
    assert fp1 == fp2, f"Same text should produce same fingerprint: {fp1} vs {fp2}"
    assert len(fp1) == 64, "SHA256 should be 64 hex characters"


def test_compute_chunk_fingerprint_case_insensitive():
    """Test case normalization."""
    text1 = "FIRE SAFETY"
    text2 = "fire safety"
    
    fp1 = compute_chunk_fingerprint(text1)
    fp2 = compute_chunk_fingerprint(text2)
    
    assert fp1 == fp2, "Case should be normalized"


def test_compute_chunk_fingerprint_whitespace_normalization():
    """Test whitespace normalization."""
    text1 = "Fire   safety    rules"
    text2 = "Fire safety rules"
    
    fp1 = compute_chunk_fingerprint(text1)
    fp2 = compute_chunk_fingerprint(text2)
    
    assert fp1 == fp2, "Whitespace should be normalized"


def test_compute_chunk_fingerprint_different_content():
    """Test different content produces different fingerprints."""
    text1 = "Fire safety rules"
    text2 = "Navigation safety rules"
    
    fp1 = compute_chunk_fingerprint(text1)
    fp2 = compute_chunk_fingerprint(text2)
    
    assert fp1 != fp2, "Different content should produce different fingerprints"


def test_compute_chunk_diff_empty_both():
    """Test diff with empty lists."""
    result = compute_chunk_diff([], [])
    
    assert result.to_add == []
    assert result.to_delete == []
    assert result.to_update == []
    assert result.unchanged == 0


def test_compute_chunk_diff_new_document():
    """Test diff when no old chunks (new document)."""
    new_chunks = [
        {"text": "Chunk 1"},
        {"text": "Chunk 2"}
    ]
    
    result = compute_chunk_diff([], new_chunks)
    
    assert len(result.to_add) == 2
    assert result.to_delete == []
    assert result.to_update == []
    assert result.unchanged == 0


def test_compute_chunk_diff_all_deleted():
    """Test diff when all chunks deleted."""
    old_chunks = [
        {"id": "c1", "text": "Chunk 1"},
        {"id": "c2", "text": "Chunk 2"}
    ]
    
    result = compute_chunk_diff(old_chunks, [])
    
    assert result.to_add == []
    assert len(result.to_delete) == 2
    assert result.to_update == []
    assert result.unchanged == 0


def test_compute_chunk_diff_unchanged():
    """Test diff when all chunks unchanged."""
    old_chunks = [
        {"id": "c1", "text": "Chunk 1"},
        {"id": "c2", "text": "Chunk 2"}
    ]
    new_chunks = [
        {"text": "Chunk 1"},
        {"text": "Chunk 2"}
    ]
    
    result = compute_chunk_diff(old_chunks, new_chunks)
    
    assert result.to_add == []
    assert result.to_delete == []
    assert result.to_update == []
    assert result.unchanged == 2


def test_compute_chunk_diff_one_changed():
    """Test diff when one chunk changed."""
    old_chunks = [
        {"id": "c1", "text": "Original chunk 1"},
        {"id": "c2", "text": "Chunk 2 unchanged"}
    ]
    new_chunks = [
        {"text": "Modified chunk 1"},
        {"text": "Chunk 2 unchanged"}
    ]
    
    result = compute_chunk_diff(old_chunks, new_chunks, use_similarity_fallback=False)
    
    assert len(result.to_add) == 1  # New modified chunk
    assert len(result.to_delete) == 1  # Old chunk deleted
    assert result.unchanged == 1  # Second chunk unchanged


def test_quick_text_similarity_identical():
    """Test Jaccard similarity for identical text."""
    text = "fire safety equipment"
    sim = _quick_text_similarity(text, text)
    
    assert sim == 1.0, f"Identical text should have similarity 1.0, got {sim}"


def test_quick_text_similarity_completely_different():
    """Test Jaccard similarity for completely different text."""
    text1 = "fire safety"
    text2 = "navigation rules"
    sim = _quick_text_similarity(text1, text2)
    
    assert sim == 0.0, f"Different text should have similarity 0.0, got {sim}"


def test_quick_text_similarity_partial_overlap():
    """Test Jaccard similarity for partial overlap."""
    text1 = "fire safety equipment"
    text2 = "fire equipment maintenance"
    sim = _quick_text_similarity(text1, text2)
    
    assert 0 < sim < 1, f"Partial overlap should have similarity between 0 and 1, got {sim}"


def test_chunk_diff_stats():
    """Test that stats are correctly calculated."""
    old_chunks = [
        {"id": "c1", "text": "Chunk 1"},
        {"id": "c2", "text": "Chunk 2"},
        {"id": "c3", "text": "Chunk 3"}
    ]
    new_chunks = [
        {"text": "Chunk 1"},
        {"text": "Modified chunk 2"},
        {"text": "New chunk 4"}
    ]
    
    result = compute_chunk_diff(old_chunks, new_chunks, use_similarity_fallback=False)
    
    stats = result.stats
    assert stats["total_old"] == 3
    assert stats["total_new"] == 3
    assert stats["unchanged"] == 1  # Chunk 1
    assert stats["change_ratio"] > 0


def test_chunk_diff_with_existing_hashes():
    """Test diff when old chunks already have content_hash."""
    old_chunks = [
        {"id": "c1", "text": "Chunk 1", "content_hash": compute_chunk_fingerprint("Chunk 1")}
    ]
    new_chunks = [
        {"text": "Chunk 1"}
    ]
    
    result = compute_chunk_diff(old_chunks, new_chunks)
    
    assert result.unchanged == 1


if __name__ == "__main__":
    print("Running Module 7 Phase 3 — Delta Indexer Tests...")
    
    tests = [
        test_compute_chunk_fingerprint_consistency,
        test_compute_chunk_fingerprint_case_insensitive,
        test_compute_chunk_fingerprint_whitespace_normalization,
        test_compute_chunk_fingerprint_different_content,
        test_compute_chunk_diff_empty_both,
        test_compute_chunk_diff_new_document,
        test_compute_chunk_diff_all_deleted,
        test_compute_chunk_diff_unchanged,
        test_compute_chunk_diff_one_changed,
        test_quick_text_similarity_identical,
        test_quick_text_similarity_completely_different,
        test_quick_text_similarity_partial_overlap,
        test_chunk_diff_stats,
        test_chunk_diff_with_existing_hashes,
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

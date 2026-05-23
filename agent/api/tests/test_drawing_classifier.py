"""
AGRA Phase 1 Tests — Drawing Type Classifier
Verify Tier 1 classification accuracy.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from api.models.drawing_models import DrawingType, DrawingFeature
from api.rag.drawing_classifier import (
    classify_tier1,
    _get_recommended_analysis,
    quick_classify,
)


def test_ga_filename_classification():
    """Test General Arrangement detection from filename."""
    result = classify_tier1("GA-001-REV-A.pdf", "")
    assert result["drawing_type"] == DrawingType.GENERAL_ARRANGEMENT
    assert result["confidence"] >= 0.85
    assert DrawingFeature.HULL_PROFILE in result["detected_features"]
    print("✓ GA filename classification passed")


def test_piping_filename_classification():
    """Test Piping Diagram detection from filename."""
    result = classify_tier1("Piping_Diagram_Fire_Main.pdf", "")
    assert result["drawing_type"] == DrawingType.PIPING_DIAGRAM
    assert result["confidence"] >= 0.80
    assert DrawingFeature.PIPING_RUNS in result["detected_features"]
    print("✓ Piping filename classification passed")


def test_electrical_filename_classification():
    """Test Electrical Schematic detection from filename."""
    result = classify_tier1("Electrical_Wiring_Diagram.pdf", "")
    assert result["drawing_type"] == DrawingType.ELECTRICAL_SCHEMATIC
    assert result["confidence"] >= 0.80
    assert DrawingFeature.WIRING_CIRCUITS in result["detected_features"]
    print("✓ Electrical filename classification passed")


def test_structural_filename_classification():
    """Test Structural Drawing detection from filename."""
    result = classify_tier1("Hull_Structure_Section_50.pdf", "")
    assert result["drawing_type"] == DrawingType.STRUCTURAL_DRAWING
    assert result["confidence"] >= 0.80
    assert DrawingFeature.WELD_SYMBOLS in result["detected_features"]
    print("✓ Structural filename classification passed")


def test_content_classification():
    """Test classification from OCR content."""
    ocr = "General Arrangement of Offshore Patrol Vessel. Overall Length 105.5m"
    result = classify_tier1("drawing.pdf", ocr)
    assert result["drawing_type"] == DrawingType.GENERAL_ARRANGEMENT
    assert result["match_source"] == "content"
    assert result["confidence"] >= 0.90
    print("✓ Content-based classification passed")


def test_combined_classification():
    """Test when both filename and content match."""
    result = classify_tier1("GA-001.pdf", "General Arrangement Overall Length")
    assert result["drawing_type"] == DrawingType.GENERAL_ARRANGEMENT
    assert result["match_source"] == "both"
    assert result["confidence"] >= 0.90
    print("✓ Combined classification passed")


def test_unknown_classification():
    """Test unknown document handling."""
    result = classify_tier1("random.pdf", "Some random text")
    assert result["drawing_type"] == DrawingType.UNKNOWN
    assert result["confidence"] < 0.70
    print("✓ Unknown classification passed")


def test_recommended_analysis():
    """Test recommended analysis logic."""
    # High confidence GA
    rec = _get_recommended_analysis(
        DrawingType.GENERAL_ARRANGEMENT,
        [DrawingFeature.DIMENSION_LINES],
        0.90
    )
    assert rec == "full_extraction"
    
    # Low confidence
    rec = _get_recommended_analysis(DrawingType.UNKNOWN, [], 0.40)
    assert rec == "manual_review"
    
    # Title block only
    rec = _get_recommended_analysis(DrawingType.TITLE_BLOCK_ONLY, [], 0.80)
    assert rec == "metadata_only"
    
    print("✓ Recommended analysis logic passed")


def test_quick_classify():
    """Test quick classify helper."""
    dtype = quick_classify("GA-001.pdf")
    assert dtype == DrawingType.GENERAL_ARRANGEMENT
    
    dtype = quick_classify("Piping_Diagram.pdf")
    assert dtype == DrawingType.PIPING_DIAGRAM
    
    print("✓ Quick classify passed")


def run_all_tests():
    """Run all classifier tests."""
    print("=" * 60)
    print("Drawing Type Classifier Tests")
    print("=" * 60)
    
    tests = [
        test_ga_filename_classification,
        test_piping_filename_classification,
        test_electrical_filename_classification,
        test_structural_filename_classification,
        test_content_classification,
        test_combined_classification,
        test_unknown_classification,
        test_recommended_analysis,
        test_quick_classify,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"✗ {test.__name__}: Assertion failed - {e}")
            failed += 1
        except Exception as e:
            print(f"✗ {test.__name__}: Error - {e}")
            failed += 1
    
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)

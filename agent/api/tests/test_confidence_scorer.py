"""
AGRA Phase 6 Tests — Confidence Scoring & Quality Metrics
Verify confidence calculation algorithms.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from api.models.drawing_models import (
    DrawingType, MeasurementUnit, Dimension, TitleBlock,
    AnalysisConfidence, StageConfidence
)
from api.rag.confidence_scorer import (
    calculate_ocr_confidence,
    calculate_vlm_confidence,
    calculate_validation_score,
    calculate_measurement_consistency,
    calculate_title_block_completeness,
    calculate_overall_confidence,
    calculate_all_confidence_scores,
    assess_result_quality,
    calculate_legacy_confidence,
    ConfidenceWeights,
)


def test_ocr_confidence_high():
    """Test OCR confidence with good results."""
    ocr_meta = {
        "printed_confidence": 88.0,
        "printed_text": "Overall Length 105.5 m Beam 14.2 m",
        "handwritten_text": "Approved"
    }
    conf = calculate_ocr_confidence(ocr_meta)
    assert conf >= 0.80
    assert conf <= 0.98
    print("✓ OCR confidence (high) passed")


def test_ocr_confidence_low():
    """Test OCR confidence with poor results."""
    ocr_meta = {
        "printed_confidence": 45.0,
        "printed_text": "",
        "handwritten_text": ""
    }
    conf = calculate_ocr_confidence(ocr_meta)
    assert conf < 0.60
    print("✓ OCR confidence (low) passed")


def test_ocr_confidence_no_metadata():
    """Test OCR confidence fallback."""
    conf = calculate_ocr_confidence({})
    assert conf == 0.30
    print("✓ OCR confidence (no metadata) passed")


def test_vlm_confidence_ga_complete():
    """Test VLM confidence for complete GA drawing."""
    vlm_res = {
        "title_block": {
            "project_name": "OPV",
            "vessel_name": "ICGS Sarthi",
            "drawing_number": "GA-001",
            "scale": "1:100"
        },
        "dimensions": [
            {"name": "LOA", "value": 105.5},
            {"name": "Beam", "value": 14.2},
            {"name": "Depth", "value": 8.5},
            {"name": "Draft", "value": 4.2}
        ],
        "equipment_tags": [
            {"tag_id": "P-1"}, {"tag_id": "P-2"}, {"tag_id": "P-3"},
            {"tag_id": "P-4"}, {"tag_id": "P-5"}
        ],
        "compliance_notes": [{"standard": "SOLAS"}]
    }
    conf = calculate_vlm_confidence(vlm_res, DrawingType.GENERAL_ARRANGEMENT)
    assert conf >= 0.70
    assert conf <= 0.95
    print("✓ VLM confidence (GA complete) passed")


def test_vlm_confidence_sparse():
    """Test VLM confidence for sparse data."""
    vlm_res = {
        "title_block": {},
        "dimensions": [],
        "equipment_tags": [],
        "compliance_notes": []
    }
    conf = calculate_vlm_confidence(vlm_res, DrawingType.UNKNOWN)
    assert conf < 0.50
    print("✓ VLM confidence (sparse) passed")


def test_vlm_confidence_title_block_only():
    """Test VLM confidence for title-block-only drawings."""
    vlm_res = {
        "title_block": {
            "drawing_number": "TB-001",
            "project_name": "Project X",
            "vessel_name": "Vessel Y",
            "scale": "1:50"
        },
        "dimensions": [],
        "equipment_tags": [],
        "compliance_notes": []
    }
    conf = calculate_vlm_confidence(vlm_res, DrawingType.TITLE_BLOCK_ONLY)
    # Title block only drawings get higher weight on title block
    assert conf >= 0.40
    print("✓ VLM confidence (title block only) passed")


def test_validation_score_no_issues():
    """Test validation score with no issues."""
    dims = [
        Dimension(name="Length", value=100, unit=MeasurementUnit.METER, raw_text="100 m", location="test", confidence=0.90),
        Dimension(name="Beam", value=15, unit=MeasurementUnit.METER, raw_text="15 m", location="test", confidence=0.90),
    ]
    issues = []
    score = calculate_validation_score(dims, issues)
    assert score >= 0.85
    print("✓ Validation score (no issues) passed")


def test_validation_score_with_errors():
    """Test validation score with errors."""
    dims = [
        Dimension(name="Length", value=100, unit=MeasurementUnit.METER, raw_text="100 m", location="test", confidence=0.90),
    ]
    issues = [
        {"severity": "error"},
        {"severity": "warning"}
    ]
    score = calculate_validation_score(dims, issues)
    assert score < 0.80
    print("✓ Validation score (with errors) passed")


def test_validation_score_empty():
    """Test validation score with no dimensions."""
    score = calculate_validation_score([], [])
    assert score == 0.40
    print("✓ Validation score (empty) passed")


def test_measurement_consistency_valid():
    """Test measurement consistency with valid L > B > D."""
    dims = [
        Dimension(name="Overall Length", value=105, unit=MeasurementUnit.METER, raw_text="105 m", location="test", confidence=0.90),
        Dimension(name="Beam", value=14, unit=MeasurementUnit.METER, raw_text="14 m", location="test", confidence=0.90),
        Dimension(name="Depth", value=8, unit=MeasurementUnit.METER, raw_text="8 m", location="test", confidence=0.90),
    ]
    score = calculate_measurement_consistency(dims)
    assert score >= 0.85
    print("✓ Measurement consistency (valid) passed")


def test_measurement_consistency_invalid():
    """Test measurement consistency with invalid L < B."""
    dims = [
        Dimension(name="Overall Length", value=50, unit=MeasurementUnit.METER, raw_text="50 m", location="test", confidence=0.90),
        Dimension(name="Beam", value=60, unit=MeasurementUnit.METER, raw_text="60 m", location="test", confidence=0.90),
    ]
    score = calculate_measurement_consistency(dims)
    assert score < 0.70
    print("✓ Measurement consistency (invalid) passed")


def test_title_block_completeness_full():
    """Test title block completeness with all fields."""
    tb = TitleBlock(
        project_name="Project",
        vessel_name="Vessel",
        drawing_number="GA-001",
        drawing_title="GA",
        revision="A",
        scale="1:100",
        date="2024-01-01",
        drawn_by="Engineer",
        company="Shipyard"
    )
    score = calculate_title_block_completeness(tb)
    assert score >= 0.90
    print("✓ Title block completeness (full) passed")


def test_title_block_completeness_partial():
    """Test title block completeness with partial fields."""
    tb = TitleBlock(
        drawing_number="GA-001",
        vessel_name="Vessel"
    )
    score = calculate_title_block_completeness(tb)
    assert score < 0.70
    assert score >= 0.30
    print("✓ Title block completeness (partial) passed")


def test_overall_confidence_calculation():
    """Test weighted overall confidence calculation."""
    overall = calculate_overall_confidence(
        ocr_confidence=0.85,
        vlm_confidence=0.80,
        validation_score=0.75,
        classification_confidence=0.90
    )
    
    # Expected: 0.85*0.25 + 0.80*0.30 + 0.75*0.25 + 0.90*0.20
    # = 0.2125 + 0.24 + 0.1875 + 0.18 = 0.82
    expected = 0.85 * 0.25 + 0.80 * 0.30 + 0.75 * 0.25 + 0.90 * 0.20
    assert abs(overall - round(expected, 2)) < 0.01
    print("✓ Overall confidence calculation passed")


def test_confidence_weights():
    """Test that default weights sum to 1."""
    total = ConfidenceWeights.OCR + ConfidenceWeights.VLM + ConfidenceWeights.VALIDATION + ConfidenceWeights.CLASSIFICATION
    assert abs(total - 1.0) < 0.001
    print("✓ Confidence weights sum to 1.0 passed")


def test_legacy_confidence():
    """Test legacy confidence calculation."""
    ocr_result = {"printed_confidence": 80.0}
    extracted = {"dimensions": ["L=100m"], "equipment_tags": ["P-1"]}
    conf = calculate_legacy_confidence(ocr_result, extracted)
    assert conf > 0.60
    assert conf <= 0.95
    print("✓ Legacy confidence passed")


def run_all_tests():
    """Run all confidence scorer tests."""
    print("=" * 60)
    print("Confidence Scorer Tests (Phase 6)")
    print("=" * 60)
    
    tests = [
        test_ocr_confidence_high,
        test_ocr_confidence_low,
        test_ocr_confidence_no_metadata,
        test_vlm_confidence_ga_complete,
        test_vlm_confidence_sparse,
        test_vlm_confidence_title_block_only,
        test_validation_score_no_issues,
        test_validation_score_with_errors,
        test_validation_score_empty,
        test_measurement_consistency_valid,
        test_measurement_consistency_invalid,
        test_title_block_completeness_full,
        test_title_block_completeness_partial,
        test_overall_confidence_calculation,
        test_confidence_weights,
        test_legacy_confidence,
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

"""
AGRA Phase 3 Tests — Enhanced Drawing Pipeline
Verify stage-wise processing and structured output.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from api.models.drawing_models import (
    DrawingType, DrawingFeature, MeasurementUnit,
    StageConfidence, AnalysisConfidence, DrawingAnalysisResult
)
from api.routers.drawing_enhanced import (
    PipelineStage,
    stage_ingest,
    stage_classify,
    stage_preprocess,
    _calculate_extraction_confidence,
)


def test_pipeline_stage():
    """Test PipelineStage lifecycle."""
    stage = PipelineStage("test", 0.25)
    assert stage.status == "pending"
    
    stage.start()
    assert stage.status == "running"
    assert stage.start_time is not None
    
    stage.complete(0.85, "Test completed")
    assert stage.status == "success"
    assert stage.confidence == 0.85
    assert stage.end_time is not None
    
    model = stage.to_model()
    assert model.stage_name == "test"
    assert model.confidence == 0.85
    print("✓ PipelineStage lifecycle passed")


def test_pipeline_stage_failure():
    """Test PipelineStage failure handling."""
    stage = PipelineStage("test", 0.25)
    stage.start()
    stage.fail("Test error")
    
    assert stage.status == "failed"
    assert "Test error" in stage.details
    print("✓ PipelineStage failure handling passed")


def test_stage_ingest_image():
    """Test Stage 1 with image input."""
    # Create a minimal valid PNG header
    png_header = b'\x89PNG\r\n\x1a\n'
    
    data_uri, image_bytes, confidence = stage_ingest(
        png_header,
        "image/png",
        "test.png"
    )
    
    assert data_uri.startswith("data:image/png;base64,")
    assert confidence == 0.98
    print("✓ Stage 1 (Ingest) image passed")


def test_stage_classify_tier1():
    """Test Stage 2 classification with Tier 1 only."""
    # Use a small dummy image
    dummy_bytes = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
    
    drawing_type, confidence, features, recommended = stage_classify(
        filename="GA-001-General-Arrangement.pdf",
        ocr_preview="General Arrangement Drawing Overall Length",
        image_bytes=dummy_bytes,
        content_type="application/pdf"
    )
    
    assert drawing_type == DrawingType.GENERAL_ARRANGEMENT
    assert confidence >= 0.80
    assert DrawingFeature.HULL_PROFILE in features
    assert DrawingFeature.DIMENSION_LINES in features
    print("✓ Stage 2 (Classify) Tier 1 passed")


def test_stage_classify_piping():
    """Test piping diagram classification."""
    dummy_bytes = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
    
    drawing_type, confidence, features, recommended = stage_classify(
        filename="Piping_Diagram_Fire_Main.pdf",
        ocr_preview="Fire Main System Pipe Size 100mm",
        image_bytes=dummy_bytes,
        content_type="application/pdf"
    )
    
    assert drawing_type == DrawingType.PIPING_DIAGRAM
    assert DrawingFeature.PIPING_RUNS in features
    print("✓ Stage 2 (Classify) piping passed")


def test_stage_classify_electrical():
    """Test electrical schematic classification."""
    dummy_bytes = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
    
    drawing_type, confidence, features, recommended = stage_classify(
        filename="Electrical_Power_Distribution.pdf",
        ocr_preview="Power Distribution 440V",
        image_bytes=dummy_bytes,
        content_type="application/pdf"
    )
    
    assert drawing_type == DrawingType.ELECTRICAL_SCHEMATIC
    assert DrawingFeature.WIRING_CIRCUITS in features
    print("✓ Stage 2 (Classify) electrical passed")


def test_stage_classify_structural():
    """Test structural drawing classification."""
    dummy_bytes = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
    
    drawing_type, confidence, features, recommended = stage_classify(
        filename="Hull_Structure_Section_50.pdf",
        ocr_preview="Steel Grade AH36 Plate Thickness 12mm",
        image_bytes=dummy_bytes,
        content_type="application/pdf"
    )
    
    assert drawing_type == DrawingType.STRUCTURAL_DRAWING
    assert DrawingFeature.WELD_SYMBOLS in features
    print("✓ Stage 2 (Classify) structural passed")


def test_calculate_extraction_confidence_complete():
    """Test extraction confidence with complete data."""
    result = {
        "title_block": {
            "project_name": "OPV",
            "vessel_name": "Test",
            "drawing_number": "GA-001",
            "scale": "1:100"
        },
        "dimensions": [
            {"name": "Length", "value": 100},
            {"name": "Beam", "value": 15},
            {"name": "Depth", "value": 8}
        ],
        "equipment_tags": [
            {"tag_id": "P-1"},
            {"tag_id": "P-2"},
            {"tag_id": "P-3"},
            {"tag_id": "P-4"},
            {"tag_id": "P-5"}
        ],
        "compliance_notes": [{"standard": "SOLAS"}]
    }
    
    confidence = _calculate_extraction_confidence(result, DrawingType.GENERAL_ARRANGEMENT)
    assert confidence > 0.70
    assert confidence <= 0.95
    print("✓ Extraction confidence (complete) passed")


def test_calculate_extraction_confidence_sparse():
    """Test extraction confidence with sparse data."""
    result = {
        "title_block": {},
        "dimensions": [],
        "equipment_tags": [],
        "compliance_notes": []
    }
    
    confidence = _calculate_extraction_confidence(result, DrawingType.UNKNOWN)
    assert confidence < 0.50
    print("✓ Extraction confidence (sparse) passed")


def test_analysis_confidence_model():
    """Test AnalysisConfidence UI helpers."""
    # High confidence
    high = AnalysisConfidence(
        overall_confidence=0.95,
        drawing_type_confidence=0.94,
        ocr_confidence=0.93,
        vlm_confidence=0.96,
        validation_score=0.92,
        title_block_completeness=0.90,
        stage_scores=[]
    )
    assert high.get_quality_label() == "High Confidence"
    assert high.get_color_code() == "#22c55e"
    
    # Medium confidence
    med = AnalysisConfidence(
        overall_confidence=0.80,
        drawing_type_confidence=0.82,
        ocr_confidence=0.78,
        vlm_confidence=0.81,
        validation_score=0.79,
        title_block_completeness=0.80,
        stage_scores=[]
    )
    assert med.get_quality_label() == "Good Confidence"
    assert med.get_color_code() == "#eab308"
    
    # Low confidence
    low = AnalysisConfidence(
        overall_confidence=0.50,
        drawing_type_confidence=0.55,
        ocr_confidence=0.45,
        vlm_confidence=0.52,
        validation_score=0.48,
        title_block_completeness=0.50,
        stage_scores=[]
    )
    assert "Low Confidence" in low.get_quality_label()
    assert low.get_color_code() == "#ef4444"
    
    print("✓ AnalysisConfidence UI helpers passed")


def test_stage_weights_sum_to_one():
    """Verify pipeline stage weights sum to approximately 1.0."""
    stages = {
        "ingest": PipelineStage("ingest", 0.10),
        "classify": PipelineStage("classify", 0.15),
        "preprocess": PipelineStage("preprocess", 0.05),
        "ocr": PipelineStage("ocr", 0.20),
        "extract": PipelineStage("extract", 0.25),
        "validate": PipelineStage("validate", 0.15),
        "index": PipelineStage("index", 0.10),
    }
    
    total_weight = sum(s.weight for s in stages.values())
    assert abs(total_weight - 1.0) < 0.001, f"Weights sum to {total_weight}"
    print("✓ Stage weights sum to 1.0 passed")


def run_all_tests():
    """Run all drawing pipeline tests."""
    print("=" * 60)
    print("Enhanced Drawing Pipeline Tests (Phase 3)")
    print("=" * 60)
    
    tests = [
        test_pipeline_stage,
        test_pipeline_stage_failure,
        test_stage_ingest_image,
        test_stage_classify_tier1,
        test_stage_classify_piping,
        test_stage_classify_electrical,
        test_stage_classify_structural,
        test_calculate_extraction_confidence_complete,
        test_calculate_extraction_confidence_sparse,
        test_analysis_confidence_model,
        test_stage_weights_sum_to_one,
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

"""
AGRA Phase 5 Tests — Chat Drawing Integration
Verify chat endpoints for drawing analysis.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from api.models.drawing_models import (
    DrawingType, MeasurementUnit, Dimension, TitleBlock,
    EquipmentTag, AnalysisConfidence, DrawingAnalysisResult
)
from api.routers.chat import _format_drawing_for_chat, ChatDrawingAnalysis


def test_format_drawing_for_chat_ga():
    """Test formatting GA drawing for chat display."""
    result = DrawingAnalysisResult(
        analysis_id="test-123",
        filename="GA-001.pdf",
        drawing_type=DrawingType.GENERAL_ARRANGEMENT,
        drawing_type_confidence=0.94,
        title_block=TitleBlock(
            project_name="OPV Construction",
            vessel_name="ICGS Sarthi",
            drawing_number="GA-001-REV-A",
            scale="1:100",
            completeness_score=0.85
        ),
        dimensions=[
            Dimension(name="Overall Length", value=105.5, unit=MeasurementUnit.METER,
                     raw_text="105.5 m", location="title block", confidence=0.98),
            Dimension(name="Beam", value=14.2, unit=MeasurementUnit.METER,
                     raw_text="14.2 m", location="title block", confidence=0.95),
            Dimension(name="Moulded Depth", value=8.5, unit=MeasurementUnit.METER,
                     raw_text="8.5 m", location="title block", confidence=0.92),
        ],
        equipment_tags=[
            EquipmentTag(tag_id="P-101", description="Main Fire Pump", location="Engine Room", confidence=0.90),
            EquipmentTag(tag_id="P-102", description="Bilge Pump", location="Engine Room", confidence=0.88),
        ],
        compliance_notes=[],
        confidence=AnalysisConfidence(
            overall_confidence=0.91,
            drawing_type_confidence=0.94,
            ocr_confidence=0.88,
            vlm_confidence=0.93,
            validation_score=0.90,
            title_block_completeness=0.85,
            stage_scores=[]
        ),
        processing_time_ms=25000,
        ocr_metadata={},
        recommended_analysis="full_extraction",
    )
    
    chat_format = _format_drawing_for_chat(result)
    
    assert chat_format.drawing_type == "general_arrangement"
    assert chat_format.type_confidence == 0.94
    assert chat_format.vessel_name == "ICGS Sarthi"
    assert chat_format.drawing_number == "GA-001-REV-A"
    assert chat_format.equipment_count == 2
    assert chat_format.overall_confidence == 0.91
    assert chat_format.quality_label == "High Confidence"
    assert len(chat_format.key_dimensions) == 3
    assert "105.5" in chat_format.summary_text
    assert "ICGS Sarthi" in chat_format.summary_text
    print("✓ Format GA drawing for chat passed")


def test_format_drawing_for_chat_piping():
    """Test formatting piping diagram for chat display."""
    result = DrawingAnalysisResult(
        analysis_id="test-456",
        filename="Piping.pdf",
        drawing_type=DrawingType.PIPING_DIAGRAM,
        drawing_type_confidence=0.88,
        title_block=TitleBlock(
            drawing_number="P-101",
            vessel_name="Test Vessel",
            completeness_score=0.60
        ),
        dimensions=[
            Dimension(name="Pipe Size", value=100, unit=MeasurementUnit.MILLIMETER,
                     raw_text="100 mm", location="diagram", confidence=0.85),
        ],
        equipment_tags=[
            EquipmentTag(tag_id="V-1", description="Valve", confidence=0.80),
            EquipmentTag(tag_id="V-2", description="Valve", confidence=0.80),
            EquipmentTag(tag_id="V-3", description="Valve", confidence=0.80),
        ],
        compliance_notes=[],
        confidence=AnalysisConfidence(
            overall_confidence=0.75,
            drawing_type_confidence=0.88,
            ocr_confidence=0.70,
            vlm_confidence=0.78,
            validation_score=0.72,
            title_block_completeness=0.60,
            stage_scores=[]
        ),
        processing_time_ms=22000,
        ocr_metadata={},
        recommended_analysis="equipment_and_routing",
    )
    
    chat_format = _format_drawing_for_chat(result)
    
    assert chat_format.drawing_type == "piping_diagram"
    assert chat_format.quality_label == "Good Confidence"
    assert chat_format.equipment_count == 3
    assert "piping" in chat_format.summary_text.lower()
    print("✓ Format piping diagram for chat passed")


def test_format_drawing_for_chat_low_confidence():
    """Test formatting low confidence result with warning."""
    result = DrawingAnalysisResult(
        analysis_id="test-789",
        filename="Unknown.pdf",
        drawing_type=DrawingType.UNKNOWN,
        drawing_type_confidence=0.45,
        title_block=TitleBlock(
            completeness_score=0.20
        ),
        dimensions=[],
        equipment_tags=[],
        compliance_notes=[],
        confidence=AnalysisConfidence(
            overall_confidence=0.55,
            drawing_type_confidence=0.45,
            ocr_confidence=0.40,
            vlm_confidence=0.50,
            validation_score=0.45,
            title_block_completeness=0.20,
            stage_scores=[]
        ),
        processing_time_ms=18000,
        ocr_metadata={},
        recommended_analysis="manual_review",
    )
    
    chat_format = _format_drawing_for_chat(result)
    
    assert chat_format.quality_label == "Low Confidence — Manual Review Recommended"
    assert "⚠️" in chat_format.summary_text  # Warning emoji present
    assert "Manual review recommended" in chat_format.summary_text
    print("✓ Format low confidence drawing for chat passed")


def test_chat_drawing_response_structure():
    """Test ChatDrawingResponse model structure."""
    from api.routers.chat import ChatDrawingResponse
    
    response = ChatDrawingResponse(
        job_id="550e8400-e29b-41d4-a716-446655440000",
        status="pending",
        message="Analyzing drawing.pdf...",
        preview=None
    )
    
    assert response.job_id
    assert response.status == "pending"
    assert "Analyzing" in response.message
    print("✓ Chat drawing response structure passed")


def test_chat_drawing_response_with_preview():
    """Test ChatDrawingResponse with preview data."""
    from api.routers.chat import ChatDrawingResponse
    
    preview = ChatDrawingAnalysis(
        drawing_type="general_arrangement",
        type_confidence=0.94,
        vessel_name="Test Vessel",
        drawing_number="GA-001",
        key_dimensions=[{"name": "Length", "value": 100, "unit": "m", "confidence": 0.95}],
        equipment_count=5,
        overall_confidence=0.90,
        quality_label="High Confidence",
        summary_text="📐 **Drawing Analysis: GA-001**"
    )
    
    response = ChatDrawingResponse(
        job_id="test-123",
        status="completed",
        message="Analysis complete",
        preview=preview
    )
    
    assert response.status == "completed"
    assert response.preview is not None
    assert response.preview.drawing_type == "general_arrangement"
    assert response.preview.overall_confidence == 0.90
    print("✓ Chat drawing response with preview passed")


def test_format_limits_dimensions():
    """Test that formatting limits dimensions to 5 max."""
    result = DrawingAnalysisResult(
        analysis_id="test-limits",
        filename="test.pdf",
        drawing_type=DrawingType.GENERAL_ARRANGEMENT,
        drawing_type_confidence=0.90,
        title_block=TitleBlock(completeness_score=0.80),
        dimensions=[
            Dimension(name=f"Dim{i}", value=i, unit=MeasurementUnit.METER,
                     raw_text=f"{i} m", location="test", confidence=0.90)
            for i in range(10)  # Create 10 dimensions
        ],
        equipment_tags=[],
        compliance_notes=[],
        confidence=AnalysisConfidence(
            overall_confidence=0.85,
            drawing_type_confidence=0.90,
            ocr_confidence=0.80,
            vlm_confidence=0.85,
            validation_score=0.82,
            title_block_completeness=0.80,
            stage_scores=[]
        ),
        processing_time_ms=20000,
        ocr_metadata={},
        recommended_analysis="full_extraction",
    )
    
    chat_format = _format_drawing_for_chat(result)
    
    # Should only include first 5 dimensions
    assert len(chat_format.key_dimensions) == 5
    print("✓ Format limits dimensions to 5 passed")


def run_all_tests():
    """Run all chat drawing integration tests."""
    print("=" * 60)
    print("Chat Drawing Integration Tests (Phase 5)")
    print("=" * 60)
    
    tests = [
        test_format_drawing_for_chat_ga,
        test_format_drawing_for_chat_piping,
        test_format_drawing_for_chat_low_confidence,
        test_chat_drawing_response_structure,
        test_chat_drawing_response_with_preview,
        test_format_limits_dimensions,
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

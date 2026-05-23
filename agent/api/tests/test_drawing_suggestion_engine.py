"""
AGRA Chat Enhancement Phase 4 Tests — Drawing Suggestion Engine
Verify suggestion generation for vessels, upgrades, advancement, quality, and compliance.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from api.rag.drawing_suggestion_engine import (
    SuggestionType,
    Suggestion,
    SuggestionSet,
    generate_vessel_match_suggestions,
    generate_upgrade_suggestions,
    generate_advancement_suggestions,
    generate_quality_suggestions,
    generate_standardization_suggestions,
    generate_compliance_suggestions,
    quick_quality_suggestion,
    quick_vessel_suggestion,
    generate_suggestions
)
from api.rag.drawing_context_search import ContextAssembly, SearchResult


def test_suggestion_type_enum():
    """Test SuggestionType enum values."""
    assert SuggestionType.VESSEL_MATCH.value == "vessel_match"
    assert SuggestionType.UPGRADE.value == "upgrade"
    assert SuggestionType.ADVANCEMENT.value == "advancement"
    assert SuggestionType.GAP_ANALYSIS.value == "gap_analysis"
    assert SuggestionType.STANDARDIZATION.value == "standardization"
    assert SuggestionType.COMPLIANCE.value == "compliance"
    print("✓ SuggestionType enum passed")


def test_suggestion_model():
    """Test Suggestion model validation."""
    sug = Suggestion(
        type=SuggestionType.VESSEL_MATCH,
        title="Test Vessel Match",
        description="This is a test suggestion",
        confidence=0.85,
        priority=2,
        action="view_vessel",
        metadata={"vessel_id": "123"}
    )
    
    assert sug.type == SuggestionType.VESSEL_MATCH
    assert sug.confidence == 0.85
    assert sug.priority == 2
    assert sug.action == "view_vessel"
    print("✓ Suggestion model passed")


def test_suggestion_set_model():
    """Test SuggestionSet model."""
    sset = SuggestionSet(
        suggestions=[],
        summary="Test summary",
        overall_confidence=0.75,
        total_suggestions=0,
        high_priority_count=0,
        critical_actions=[]
    )
    
    assert sset.overall_confidence == 0.75
    assert sset.summary == "Test summary"
    print("✓ SuggestionSet model passed")


def test_vessel_match_high_confidence():
    """Test vessel match suggestion for high confidence match."""
    drawing_data = {
        "title_block": {"vessel_name": "ICGS Sarthi"},
        "drawing_type": "structural_drawing"
    }
    
    context = ContextAssembly(
        vessel_matches=[
            SearchResult(
                document_id="1",
                document_name="Sarthi_Specs.pdf",
                document_type="vessel_specification",
                relevance_score=0.92,
                excerpt="Specs",
                vessel_name="ICGS Sarthi"
            )
        ],
        similar_drawings=[],
        matching_parts=[],
        related_sotrs=[],
        raw_context_text="",
        total_sources=1,
        highest_relevance=0.92
    )
    
    suggestions = generate_vessel_match_suggestions(drawing_data, context)
    
    assert len(suggestions) >= 1
    assert any(s.type == SuggestionType.VESSEL_MATCH for s in suggestions)
    assert all(s.confidence >= 0.70 for s in suggestions)
    print("✓ Vessel match high confidence passed")


def test_vessel_match_no_match():
    """Test vessel match when no vessel in drawing."""
    drawing_data = {
        "title_block": {},
        "drawing_type": "unknown"
    }
    
    context = ContextAssembly(
        vessel_matches=[],
        similar_drawings=[],
        matching_parts=[],
        related_sotrs=[],
        raw_context_text="",
        total_sources=0,
        highest_relevance=0.0
    )
    
    suggestions = generate_vessel_match_suggestions(drawing_data, context)
    
    assert len(suggestions) == 0
    print("✓ Vessel match no match passed")


def test_upgrade_suggestion_material():
    """Test upgrade suggestion for mild steel material."""
    drawing_data = {
        "title_block": {},
        "ocr_metadata": {
            "printed_text": "Constructed with mild steel plate MS grade"
        }
    }
    
    context = ContextAssembly(
        vessel_matches=[],
        similar_drawings=[],
        matching_parts=[],
        related_sotrs=[],
        raw_context_text="",
        total_sources=0,
        highest_relevance=0.0
    )
    
    suggestions = generate_upgrade_suggestions(drawing_data, context)
    
    # Should detect mild steel and suggest Grade-A
    upgrade_sugs = [s for s in suggestions if s.type == SuggestionType.UPGRADE]
    assert len(upgrade_sugs) >= 1
    assert any("Grade-A" in s.title for s in upgrade_sugs)
    print("✓ Upgrade suggestion material passed")


def test_quality_suggestion_high_confidence():
    """Test quality suggestion for high confidence."""
    drawing_data = {
        "title_block": {"vessel_name": "Test", "drawing_number": "001"},
        "confidence": {"overall_confidence": 0.90}
    }
    
    suggestions = generate_quality_suggestions(drawing_data, 0.90)
    
    # Should generate high quality praise
    quality_sugs = [s for s in suggestions if s.type == SuggestionType.QUALITY_ALERT]
    assert any(s.confidence >= 0.85 for s in quality_sugs)
    print("✓ Quality suggestion high confidence passed")


def test_quality_suggestion_low_confidence():
    """Test quality suggestion for low confidence."""
    drawing_data = {
        "title_block": {},
        "confidence": {"overall_confidence": 0.45}
    }
    
    suggestions = generate_quality_suggestions(drawing_data, 0.45)
    
    # Should generate critical warning
    gap_sugs = [s for s in suggestions if s.type == SuggestionType.GAP_ANALYSIS]
    assert len(gap_sugs) >= 1
    assert all(s.priority <= 2 for s in gap_sugs)  # High priority
    print("✓ Quality suggestion low confidence passed")


def test_quality_suggestion_missing_fields():
    """Test quality suggestion for missing title block fields."""
    drawing_data = {
        "title_block": {"vessel_name": "ICGS Sarthi"},  # Missing drawing_number, project_name
        "confidence": {"overall_confidence": 0.80}
    }
    
    suggestions = generate_quality_suggestions(drawing_data, 0.80)
    
    # Should detect missing fields
    gap_sugs = [s for s in suggestions if s.type == SuggestionType.GAP_ANALYSIS]
    assert len(gap_sugs) >= 1
    print("✓ Quality suggestion missing fields passed")


def test_standardization_many_drawings():
    """Test standardization suggestion when many similar drawings exist."""
    drawing_data = {
        "title_block": {},
        "equipment_tags": []
    }
    
    context = ContextAssembly(
        vessel_matches=[],
        similar_drawings=[
            SearchResult(document_id="1", document_name="D1.pdf", document_type="blueprint", relevance_score=0.8, excerpt="D1"),
            SearchResult(document_id="2", document_name="D2.pdf", document_type="blueprint", relevance_score=0.75, excerpt="D2"),
            SearchResult(document_id="3", document_name="D3.pdf", document_type="blueprint", relevance_score=0.7, excerpt="D3"),
        ],
        matching_parts=[],
        related_sotrs=[],
        raw_context_text="",
        total_sources=3,
        highest_relevance=0.8
    )
    
    suggestions = generate_standardization_suggestions(drawing_data, context)
    
    std_sugs = [s for s in suggestions if s.type == SuggestionType.STANDARDIZATION]
    assert len(std_sugs) >= 1
    print("✓ Standardization many drawings passed")


def test_compliance_no_sotr():
    """Test compliance suggestion when no SOTR found."""
    drawing_data = {
        "title_block": {}
    }
    
    context = ContextAssembly(
        vessel_matches=[],
        similar_drawings=[],
        matching_parts=[],
        related_sotrs=[],  # No SOTR
        raw_context_text="",
        total_sources=0,
        highest_relevance=0.0
    )
    
    suggestions = generate_compliance_suggestions(drawing_data, context)
    
    comp_sugs = [s for s in suggestions if s.type == SuggestionType.COMPLIANCE]
    assert len(comp_sugs) >= 1
    assert any("No SOTR" in s.title for s in comp_sugs)
    print("✓ Compliance no SOTR passed")


def test_compliance_with_sotr():
    """Test compliance suggestion when SOTR found."""
    drawing_data = {
        "title_block": {}
    }
    
    context = ContextAssembly(
        vessel_matches=[],
        similar_drawings=[],
        matching_parts=[],
        related_sotrs=[
            SearchResult(
                document_id="1",
                document_name="OPV_SOTR_v2.3.pdf",
                document_type="sotr_requirements",
                relevance_score=0.75,
                excerpt="SOTR requirements"
            )
        ],
        raw_context_text="",
        total_sources=1,
        highest_relevance=0.75
    )
    
    suggestions = generate_compliance_suggestions(drawing_data, context)
    
    comp_sugs = [s for s in suggestions if s.type == SuggestionType.COMPLIANCE]
    assert len(comp_sugs) >= 1
    assert any("Aligned" in s.title or "SOTR" in s.title for s in comp_sugs)
    print("✓ Compliance with SOTR passed")


def test_quick_quality_suggestion():
    """Test quick quality suggestion utility."""
    high_sug = quick_quality_suggestion(0.90)
    assert high_sug is not None
    assert high_sug.type == SuggestionType.QUALITY_ALERT
    
    low_sug = quick_quality_suggestion(0.50)
    assert low_sug is not None
    assert low_sug.type == SuggestionType.GAP_ANALYSIS
    assert low_sug.priority == 1  # Critical
    
    mid_sug = quick_quality_suggestion(0.70)
    assert mid_sug is None  # No suggestion for medium confidence
    print("✓ Quick quality suggestion passed")


def test_quick_vessel_suggestion():
    """Test quick vessel suggestion utility."""
    sug = quick_vessel_suggestion("ICGS Sarthi", 0.85)
    assert sug is not None
    assert sug.type == SuggestionType.VESSEL_MATCH
    assert "Sarthi" in sug.title
    assert sug.priority == 2
    
    no_sug = quick_vessel_suggestion("ICGS Sarthi", 0.60)
    assert no_sug is None  # Below threshold
    print("✓ Quick vessel suggestion passed")


def test_generate_suggestions_full():
    """Test full suggestion generation pipeline."""
    drawing_data = {
        "title_block": {
            "vessel_name": "ICGS Sarthi",
            "drawing_number": "OPV-001"
        },
        "drawing_type": "structural_drawing",
        "equipment_tags": [{"tag_number": "ENG-001"}],
        "ocr_metadata": {"printed_text": "Grade-A Steel construction"},
        "confidence": {"overall_confidence": 0.85}
    }
    
    context = ContextAssembly(
        vessel_matches=[
            SearchResult(
                document_id="1",
                document_name="Sarthi_Specs.pdf",
                document_type="vessel_specification",
                relevance_score=0.88,
                excerpt="Specs",
                vessel_name="ICGS Sarthi"
            )
        ],
        similar_drawings=[],
        matching_parts=[],
        related_sotrs=[
            SearchResult(
                document_id="2",
                document_name="SOTR_OPV.pdf",
                document_type="sotr",
                relevance_score=0.72,
                excerpt="SOTR"
            )
        ],
        raw_context_text="",
        total_sources=2,
        highest_relevance=0.88
    )
    
    result = generate_suggestions(
        drawing_data=drawing_data,
        context=context,
        query="analyze this drawing",
        analysis_confidence=0.85,
        use_llm_enhancement=False
    )
    
    assert isinstance(result, SuggestionSet)
    assert result.total_suggestions > 0
    assert result.overall_confidence > 0
    assert len(result.summary) > 0
    print(f"✓ Full suggestion generation passed ({result.total_suggestions} suggestions)")


def test_advancement_suggestion_with_sotr():
    """Test advancement suggestion when SOTR match exists."""
    drawing_data = {
        "title_block": {"vessel_name": "ICGS Sarthi"},
        "equipment_tags": [{"tag_number": "E1"}, {"tag_number": "E2"}, {"tag_number": "E3"}, {"tag_number": "E4"}],
        "drawing_type": "general_arrangement"
    }
    
    context = ContextAssembly(
        vessel_matches=[],
        similar_drawings=[],
        matching_parts=[],
        related_sotrs=[
            SearchResult(
                document_id="1",
                document_name="OPV_SOTR.pdf",
                document_type="sotr",
                relevance_score=0.75,
                excerpt="Requirements"
            )
        ],
        raw_context_text="",
        total_sources=1,
        highest_relevance=0.75
    )
    
    suggestions = generate_advancement_suggestions(drawing_data, context, "is this useful?")
    
    adv_sugs = [s for s in suggestions if s.type == SuggestionType.ADVANCEMENT]
    assert len(adv_sugs) >= 1
    print("✓ Advancement suggestion with SOTR passed")


def run_all_tests():
    """Run all drawing suggestion engine tests."""
    print("=" * 60)
    print("Drawing Suggestion Engine Phase 4 Tests")
    print("=" * 60)
    
    tests = [
        test_suggestion_type_enum,
        test_suggestion_model,
        test_suggestion_set_model,
        test_vessel_match_high_confidence,
        test_vessel_match_no_match,
        test_upgrade_suggestion_material,
        test_quality_suggestion_high_confidence,
        test_quality_suggestion_low_confidence,
        test_quality_suggestion_missing_fields,
        test_standardization_many_drawings,
        test_compliance_no_sotr,
        test_compliance_with_sotr,
        test_quick_quality_suggestion,
        test_quick_vessel_suggestion,
        test_generate_suggestions_full,
        test_advancement_suggestion_with_sotr,
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

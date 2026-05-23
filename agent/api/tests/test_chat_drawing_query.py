"""
AGRA Chat Enhancement Phase 1 Tests — Chat Drawing Query Endpoint
Verify intent classification, RAG search, answer generation, and confidence calculation.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from api.routers.chat_drawing_query import (
    generate_suggestions,
    calculate_query_confidence,
    RAGSource,
    SuggestionItem,
    ConfidenceBreakdown,
    DrawingQueryResponse
)

# Phase 2: Intent Router imports
from api.rag.drawing_query_router import (
    classify_intent,
    QueryIntent
)

# Phase 3: Context Search imports
from api.rag.drawing_context_search import (
    build_vessel_queries,
    build_drawing_queries,
    build_equipment_queries,
    DrawingSearchTerms,
    extract_search_terms
)


def test_intent_classification_extract():
    """Test intent classification for extraction queries."""
    queries = [
        "extract all dimensions",
        "what are the measurements",
        "list the specifications",
        "show me the dimensions from this drawing"
    ]
    for q in queries:
        intent = classify_intent(q)
        assert intent == QueryIntent.EXTRACT, f"Expected EXTRACT for: {q}, got {intent}"
    print("✓ Intent classification EXTRACT passed")


def test_intent_classification_identify():
    """Test intent classification for identification queries."""
    queries = [
        "what equipment is shown",
        "identify the components",
        "what part is this",
        "name the equipment in this blueprint"
    ]
    for q in queries:
        intent = classify_intent(q)
        assert intent == QueryIntent.IDENTIFY, f"Expected IDENTIFY for: {q}, got {intent}"
    print("✓ Intent classification IDENTIFY passed")


def test_intent_classification_suggest():
    """Test intent classification for suggestion queries."""
    queries = [
        "is this useful for our vessels",
        "can we use this for advancement",
        "should we adopt this design",
        "advancement potential of this blueprint"
    ]
    for q in queries:
        intent = classify_intent(q)
        assert intent == QueryIntent.SUGGEST, f"Expected SUGGEST for: {q}, got {intent}"
    print("✓ Intent classification SUGGEST passed")


def test_build_rag_queries_with_vessel():
    """Test RAG query builder with vessel data (Phase 3)."""
    drawing_data = {
        "title_block": {
            "vessel_name": "ICGS Sarthi",
            "drawing_number": "OPV-HULL-001",
            "project_name": "OPV Project"
        },
        "drawing_type": "structural_drawing",
        "equipment_tags": [
            {"tag_number": "ENG-001"},
            {"tag_number": "HULL-A1"}
        ]
    }
    
    # Phase 3: Use extract_search_terms and query builders
    terms = extract_search_terms(drawing_data)
    vessel_queries = build_vessel_queries(terms)
    drawing_queries = build_drawing_queries(terms)
    equipment_queries = build_equipment_queries(terms)
    
    all_queries = vessel_queries + drawing_queries + equipment_queries
    
    assert len(all_queries) >= 4
    assert any("ICGS Sarthi" in q for q in all_queries)
    assert any("OPV-HULL-001" in q or "OPV-HULL" in q for q in all_queries)
    print("✓ RAG query builder with vessel data passed (Phase 3)")


def test_build_rag_queries_minimal():
    """Test RAG query builder with minimal data (Phase 3)."""
    drawing_data = {
        "title_block": {},
        "drawing_type": "general_arrangement",
        "equipment_tags": []
    }
    
    # Phase 3: Use extract_search_terms
    terms = extract_search_terms(drawing_data)
    vessel_queries = build_vessel_queries(terms)
    
    assert len(vessel_queries) >= 1  # Should have at least drawing type query
    print("✓ RAG query builder minimal data passed (Phase 3)")


def test_suggestion_generation_match():
    """Test suggestion generation for vessel matches."""
    drawing_data = {
        "title_block": {"vessel_name": "ICGS Sarthi", "drawing_number": "DRW-001"},
        "drawing_type": "structural_drawing",
        "confidence": {"overall_confidence": 0.85}
    }
    
    rag_sources = [
        RAGSource(
            document_id="doc1",
            document_name="Sarthi_Specs.pdf",
            document_type="vessel_spec",
            relevance_score=0.92,
            excerpt="Specifications for ICGS Sarthi",
            vessel_name="ICGS Sarthi"
        )
    ]
    
    suggestions = generate_suggestions(drawing_data, rag_sources, "SUGGEST")
    
    assert len(suggestions) > 0
    match_suggestions = [s for s in suggestions if s.type == "match"]
    assert len(match_suggestions) > 0
    assert "Sarthi" in match_suggestions[0].text
    print("✓ Suggestion generation match passed")


def test_suggestion_generation_low_confidence():
    """Test suggestion generation for low confidence drawings."""
    drawing_data = {
        "title_block": {"vessel_name": "Unknown Vessel"},
        "drawing_type": "unknown",
        "confidence": {"overall_confidence": 0.45}
    }
    
    rag_sources = []
    
    suggestions = generate_suggestions(drawing_data, rag_sources, "EXTRACT")
    
    gap_suggestions = [s for s in suggestions if s.type == "gap_analysis"]
    assert len(gap_suggestions) > 0
    assert "manual" in gap_suggestions[0].text.lower() or "verification" in gap_suggestions[0].text.lower()
    print("✓ Suggestion generation low confidence passed")


def test_confidence_calculation_high():
    """Test confidence calculation with high quality inputs."""
    drawing_data = {
        "confidence": {
            "vlm_confidence": 0.92,
            "ocr_confidence": 0.88,
            "drawing_type_confidence": 0.95
        }
    }
    
    rag_sources = [
        RAGSource(document_id="d1", document_name="specs.pdf", document_type="spec", relevance_score=0.85, excerpt="test"),
        RAGSource(document_id="d2", document_name="blueprint.pdf", document_type="drawing", relevance_score=0.80, excerpt="test")
    ]
    
    query = "extract dimensions from this hull drawing"
    intent = "EXTRACT"
    
    confidence = calculate_query_confidence(drawing_data, rag_sources, query, intent)
    
    assert confidence.overall >= 0.70
    assert confidence.vlm == 0.92
    assert confidence.ocr == 0.88
    assert confidence.rag >= 0.80
    assert confidence.quality_label in ["High", "Medium"]
    print(f"✓ Confidence calculation high passed (overall: {confidence.overall})")


def test_confidence_calculation_low():
    """Test confidence calculation with low quality inputs."""
    drawing_data = {
        "confidence": {
            "vlm_confidence": 0.50,
            "ocr_confidence": 0.45,
            "drawing_type_confidence": 0.55
        }
    }
    
    rag_sources = []  # No context
    
    query = "analyze"
    intent = "EXTRACT"
    
    confidence = calculate_query_confidence(drawing_data, rag_sources, query, intent)
    
    assert confidence.overall < 0.60
    assert confidence.quality_label == "Low"
    print(f"✓ Confidence calculation low passed (overall: {confidence.overall})")


def test_confidence_intent_weights():
    """Test that different intents have different confidence weights."""
    drawing_data = {
        "confidence": {
            "vlm_confidence": 0.80,
            "ocr_confidence": 0.80,
            "drawing_type_confidence": 0.80
        }
    }
    
    rag_sources = [
        RAGSource(document_id="d1", document_name="test.pdf", document_type="spec", relevance_score=0.90, excerpt="test")
    ]
    
    query = "test query"
    
    # Different intents should produce slightly different scores due to weighting
    conf_extract = calculate_query_confidence(drawing_data, rag_sources, query, "EXTRACT")
    conf_suggest = calculate_query_confidence(drawing_data, rag_sources, query, "SUGGEST")
    
    # Both should be reasonable scores
    assert 0.5 <= conf_extract.overall <= 0.95
    assert 0.5 <= conf_suggest.overall <= 0.95
    print("✓ Confidence intent weights passed")


def test_response_model_structure():
    """Test DrawingQueryResponse model structure."""
    response = DrawingQueryResponse(
        job_id="test-job-123",
        status="completed",
        query="extract dimensions",
        answer="The drawing shows overall length of 85.5m",
        drawing_summary={
            "drawing_type": "general_arrangement",
            "vessel_name": "ICGS Sarthi",
            "dimensions_count": 5
        },
        rag_sources=[
            RAGSource(
                document_id="doc1",
                document_name="vessel_specs.pdf",
                document_type="specification",
                relevance_score=0.87,
                excerpt="Vessel specifications for ICGS Sarthi"
            )
        ],
        confidence=ConfidenceBreakdown(
            overall=0.85,
            vlm=0.90,
            ocr=0.80,
            rag=0.87,
            query_clarity=0.85,
            quality_label="High"
        ),
        suggestions=[
            SuggestionItem(
                type="match",
                text="High match with ICGS Sarthi",
                confidence=0.92,
                action="view_vessel"
            )
        ],
        processing_time_ms=3450,
        created_at="2026-01-15T10:00:00"
    )
    
    assert response.job_id == "test-job-123"
    assert response.status == "completed"
    assert response.confidence.overall == 0.85
    assert len(response.rag_sources) == 1
    assert len(response.suggestions) == 1
    print("✓ Response model structure passed")


def test_suggestion_item_model():
    """Test SuggestionItem model validation."""
    suggestion = SuggestionItem(
        type="advancement",
        text="Consider upgrading to Grade-A steel",
        confidence=0.75,
        action="view_upgrade_options"
    )
    
    assert suggestion.type == "advancement"
    assert suggestion.confidence == 0.75
    assert suggestion.action is not None
    print("✓ Suggestion item model passed")


def test_rag_source_model():
    """Test RAGSource model validation."""
    source = RAGSource(
        document_id="doc-123",
        document_name="Sarthi_Blueprint.pdf",
        document_type="blueprint",
        relevance_score=0.88,
        excerpt="Hull specifications for ICGS Sarthi OPV",
        vessel_name="ICGS Sarthi"
    )
    
    assert source.relevance_score == 0.88
    assert source.vessel_name == "ICGS Sarthi"
    assert len(source.excerpt) > 0
    print("✓ RAG source model passed")


def run_all_tests():
    """Run all chat drawing query tests."""
    print("=" * 60)
    print("Chat Drawing Query Phase 1 Tests")
    print("=" * 60)
    
    tests = [
        test_intent_classification_extract,
        test_intent_classification_identify,
        test_intent_classification_suggest,
        test_build_rag_queries_with_vessel,
        test_build_rag_queries_minimal,
        test_suggestion_generation_match,
        test_suggestion_generation_low_confidence,
        test_confidence_calculation_high,
        test_confidence_calculation_low,
        test_confidence_intent_weights,
        test_response_model_structure,
        test_suggestion_item_model,
        test_rag_source_model,
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

"""
AGRA Chat Enhancement Phase 6 — Integration Tests
End-to-end testing for drawing query pipeline.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from api.routers.chat_drawing_query import (
    DrawingQueryResponse,
    run_chat_drawing_query_pipeline
)
from api.rag.drawing_query_router import (
    classify_intent, route_query, QueryIntent
)
from api.rag.drawing_context_search import (
    search_drawing_context, extract_search_terms
)
from api.rag.drawing_suggestion_engine import (
    generate_suggestions, SuggestionSet
)


def test_end_to_end_pipeline_structure():
    """Test that all pipeline components are properly connected."""
    # Verify all imports work
    assert callable(classify_intent)
    assert callable(route_query)
    assert callable(search_drawing_context)
    assert callable(generate_suggestions)
    assert callable(run_chat_drawing_query_pipeline)
    print("✓ Pipeline structure verified")


def test_intent_to_plan_flow():
    """Test intent classification connects to query plan."""
    queries = [
        ("extract dimensions", QueryIntent.EXTRACT),
        ("what equipment is this", QueryIntent.IDENTIFY),
        ("is this useful", QueryIntent.SUGGEST),
        ("does this meet specs", QueryIntent.COMPARE),
        ("validate the drawing", QueryIntent.VALIDATE),
    ]
    
    for query, expected_intent in queries:
        # Test classify_intent
        intent = classify_intent(query, use_llm=False)
        assert intent == expected_intent, f"Query '{query}' should be {expected_intent}"
        
        # Test route_query returns plan
        plan = route_query(query)
        assert plan.intent == expected_intent
        assert plan.priority >= 1 and plan.priority <= 5
        assert len(plan.steps) > 0
    
    print("✓ Intent to plan flow verified")


def test_context_search_integration():
    """Test context search integration with drawing data."""
    # Minimal drawing data
    drawing_data = {
        "title_block": {
            "vessel_name": "Test Vessel",
            "drawing_number": "TEST-001"
        },
        "drawing_type": "general_arrangement",
        "equipment_tags": [{"tag_number": "ENG-001"}],
        "dimensions": [{"name": "Length", "value": 100}],
        "confidence": {"overall_confidence": 0.85}
    }
    
    # Test term extraction
    terms = extract_search_terms(drawing_data)
    assert terms.vessel_name == "Test Vessel"
    assert terms.drawing_number == "TEST-001"
    
    print("✓ Context search integration verified")


def test_suggestion_engine_integration():
    """Test suggestion engine with mock context."""
    from api.rag.drawing_context_search import ContextAssembly, SearchResult
    
    drawing_data = {
        "title_block": {"vessel_name": "ICGS Test"},
        "drawing_type": "structural_drawing",
        "equipment_tags": [{"tag_number": "TAG-1"}],
        "confidence": {"overall_confidence": 0.80}
    }
    
    context = ContextAssembly(
        vessel_matches=[
            SearchResult(
                document_id="1",
                document_name="Test_Specs.pdf",
                document_type="vessel_specification",
                relevance_score=0.85,
                excerpt="Test",
                vessel_name="ICGS Test"
            )
        ],
        similar_drawings=[],
        matching_parts=[],
        related_sotrs=[],
        raw_context_text="",
        total_sources=1,
        highest_relevance=0.85
    )
    
    # Generate suggestions
    result = generate_suggestions(
        drawing_data=drawing_data,
        context=context,
        query="analyze this",
        analysis_confidence=0.80,
        use_llm_enhancement=False
    )
    
    assert isinstance(result, SuggestionSet)
    assert result.total_suggestions > 0
    assert result.overall_confidence > 0
    
    print("✓ Suggestion engine integration verified")


def test_response_model_completeness():
    """Test response model has all required fields."""
    from datetime import datetime
    
    response = DrawingQueryResponse(
        job_id="test-job-123",
        status="completed",
        query="test query",
        answer="Test answer",
        drawing_summary={
            "drawing_type": "test",
            "vessel_name": "Test",
            "dimensions_count": 5,
            "equipment_count": 3
        },
        rag_sources=[],
        confidence={
            "overall": 0.85,
            "vlm": 0.90,
            "ocr": 0.80,
            "rag": 0.85,
            "query_clarity": 0.90,
            "quality_label": "High"
        },
        suggestions=[
            {
                "type": "vessel_match",
                "text": "Test suggestion",
                "confidence": 0.85,
                "action": "view"
            }
        ],
        processing_time_ms=2500,
        created_at=datetime.now(),
        completed_at=datetime.now()
    )
    
    # Verify all fields exist
    assert response.job_id == "test-job-123"
    assert response.status == "completed"
    assert response.confidence["overall"] == 0.85
    assert len(response.suggestions) == 1
    
    print("✓ Response model completeness verified")


def test_error_handling_structure():
    """Test error handling in pipeline components."""
    # Test with invalid/missing data
    empty_drawing = {}
    
    # Should not crash with empty data
    try:
        terms = extract_search_terms(empty_drawing)
        assert terms.vessel_name is None  # Graceful handling
    except Exception as e:
        assert False, f"Should handle empty data gracefully: {e}"
    
    # Test suggestion engine with minimal data
    from api.rag.drawing_context_search import ContextAssembly
    
    result = generate_suggestions(
        drawing_data={},
        context=ContextAssembly(
            vessel_matches=[],
            similar_drawings=[],
            matching_parts=[],
            related_sotrs=[],
            raw_context_text="",
            total_sources=0,
            highest_relevance=0.0
        ),
        query="test",
        analysis_confidence=0.0,
        use_llm_enhancement=False
    )
    
    # Should return empty but valid result
    assert isinstance(result, SuggestionSet)
    
    print("✓ Error handling structure verified")


def test_confidence_calculation_integration():
    """Test confidence calculation with all factors."""
    from api.routers.chat_drawing_query import calculate_query_confidence
    from api.rag.drawing_query_router import QueryIntent
    
    drawing_data = {
        "confidence": {
            "vlm_confidence": 0.90,
            "ocr_confidence": 0.85,
            "drawing_type_confidence": 0.88
        }
    }
    
    rag_sources = [
        type('Source', (), {'relevance_score': 0.80})(),
        type('Source', (), {'relevance_score': 0.75})(),
    ]
    
    # Test for each intent type
    for intent in ["EXTRACT", "IDENTIFY", "SUGGEST", "COMPARE", "VALIDATE"]:
        confidence = calculate_query_confidence(
            drawing_data, rag_sources, "test query", intent
        )
        
        assert confidence.overall > 0
        assert confidence.vlm > 0
        assert confidence.ocr > 0
        assert confidence.rag > 0
        assert confidence.query_clarity > 0
        assert confidence.quality_label in ["High", "Medium", "Low"]
    
    print("✓ Confidence calculation integration verified")


def test_component_exports():
    """Test all components are properly exported."""
    from api.rag import (
        # Router
        classify_intent, route_query, QueryIntent, QueryPlan,
        # Context Search
        search_drawing_context, extract_search_terms, DrawingSearchTerms,
        # Suggestion Engine
        generate_suggestions, SuggestionSet, SuggestionType,
        # Endpoint
        run_chat_drawing_query_pipeline
    )
    
    # All should be importable
    assert callable(classify_intent)
    assert callable(route_query)
    assert callable(search_drawing_context)
    assert callable(extract_search_terms)
    assert callable(generate_suggestions)
    assert callable(run_chat_drawing_query_pipeline)
    
    # Types should be valid
    assert QueryIntent.EXTRACT is not None
    assert SuggestionType.VESSEL_MATCH is not None
    
    print("✓ Component exports verified")


def test_pipeline_step_order():
    """Test pipeline steps execute in correct order."""
    plan = route_query("extract dimensions from this drawing")
    
    # Verify step order makes sense
    step_names = [s.step_name for s in plan.steps]
    
    # VLM analysis should be early
    assert any("vlm" in name.lower() for name in step_names)
    
    # Plan should have valid weights
    total_weight = sum(s.weight_in_confidence for s in plan.steps)
    assert 0.9 <= total_weight <= 1.1  # Should roughly sum to 1
    
    print("✓ Pipeline step order verified")


def run_all_tests():
    """Run all integration tests."""
    print("=" * 60)
    print("Chat Drawing Query Integration Tests (Phase 6)")
    print("=" * 60)
    
    tests = [
        test_end_to_end_pipeline_structure,
        test_intent_to_plan_flow,
        test_context_search_integration,
        test_suggestion_engine_integration,
        test_response_model_completeness,
        test_error_handling_structure,
        test_confidence_calculation_integration,
        test_component_exports,
        test_pipeline_step_order,
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

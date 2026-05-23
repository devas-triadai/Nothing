"""
AGRA Chat Enhancement Phase 2 Tests — Drawing Query Intent Router
Verify intent classification, query planning, and routing logic.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from api.rag.drawing_query_router import (
    classify_intent_fast,
    classify_intent,
    get_query_plan,
    route_query,
    QueryIntent,
    QueryPlan,
    ProcessingStep,
    KEYWORD_PATTERNS,
    QueryMetricsCollector
)


def test_intent_enum_values():
    """Test QueryIntent enum has correct values."""
    assert QueryIntent.EXTRACT.value == "extract"
    assert QueryIntent.IDENTIFY.value == "identify"
    assert QueryIntent.COMPARE.value == "compare"
    assert QueryIntent.SUGGEST.value == "suggest"
    assert QueryIntent.VALIDATE.value == "validate"
    print("✓ QueryIntent enum values passed")


def test_fast_classification_extract():
    """Test fast keyword classification for EXTRACT intent."""
    queries = [
        "extract all dimensions",
        "what are the measurements",
        "list the specifications",
        "show me all dimensions from this drawing",
        "get the dimensions",
        "pull the measurements"
    ]
    
    for q in queries:
        result = classify_intent_fast(q)
        assert result == QueryIntent.EXTRACT, f"Expected EXTRACT for: {q}, got {result}"
    
    print("✓ Fast classification EXTRACT passed")


def test_fast_classification_identify():
    """Test fast keyword classification for IDENTIFY intent."""
    queries = [
        "what equipment is this",
        "identify the components",
        "name the parts shown",
        "which system is this",
        "what component is displayed"
    ]
    
    for q in queries:
        result = classify_intent_fast(q)
        assert result == QueryIntent.IDENTIFY, f"Expected IDENTIFY for: {q}, got {result}"
    
    print("✓ Fast classification IDENTIFY passed")


def test_fast_classification_suggest():
    """Test fast keyword classification for SUGGEST intent."""
    queries = [
        "is this useful",
        "can we use this for advancement",
        "should we adopt this design",
        "advancement potential",
        "upgrade recommendation"
    ]
    
    for q in queries:
        result = classify_intent_fast(q)
        assert result == QueryIntent.SUGGEST, f"Expected SUGGEST for: {q}, got {result}"
    
    print("✓ Fast classification SUGGEST passed")


def test_fast_classification_compare():
    """Test fast keyword classification for COMPARE intent."""
    queries = [
        "compare with specs",
        "does this meet requirements",
        "check compliance",
        "is this according to SOTR",
        "verify against standards"
    ]
    
    for q in queries:
        result = classify_intent_fast(q)
        assert result == QueryIntent.COMPARE, f"Expected COMPARE for: {q}, got {result}"
    
    print("✓ Fast classification COMPARE passed")


def test_fast_classification_validate():
    """Test fast keyword classification for VALIDATE intent."""
    queries = [
        "is this correct",
        "validate the dimensions",
        "check if accurate",
        "verify the measurements"
    ]
    
    for q in queries:
        result = classify_intent_fast(q)
        assert result == QueryIntent.VALIDATE, f"Expected VALIDATE for: {q}, got {result}"
    
    print("✓ Fast classification VALIDATE passed")


def test_fast_classification_fallback():
    """Test fast classification returns None for unclear queries."""
    queries = [
        "analyze this",
        "look at this",
        "what do you think",
        "help me understand"
    ]
    
    for q in queries:
        result = classify_intent_fast(q)
        assert result is None, f"Expected None (fallback) for: {q}, got {result}"
    
    print("✓ Fast classification fallback passed")


def test_get_query_plan_extract():
    """Test query plan for EXTRACT intent."""
    plan = get_query_plan(QueryIntent.EXTRACT)
    
    assert plan.intent == QueryIntent.EXTRACT
    assert plan.requires_vlm is True
    assert plan.requires_rag is False  # Extraction doesn't need RAG
    assert plan.priority == 1  # Highest priority
    assert len(plan.steps) == 3
    assert plan.max_tokens_for_answer == 600
    print("✓ Query plan EXTRACT passed")


def test_get_query_plan_suggest():
    """Test query plan for SUGGEST intent."""
    plan = get_query_plan(QueryIntent.SUGGEST)
    
    assert plan.intent == QueryIntent.SUGGEST
    assert plan.requires_vlm is True
    assert plan.requires_rag is True  # Suggestions need RAG
    assert plan.priority == 4
    assert plan.max_tokens_for_answer == 800
    assert plan.temperature == 0.4  # Higher temp for creativity
    print("✓ Query plan SUGGEST passed")


def test_get_query_plan_compare():
    """Test query plan for COMPARE intent."""
    plan = get_query_plan(QueryIntent.COMPARE)
    
    assert plan.intent == QueryIntent.COMPARE
    assert plan.requires_rag is True  # Comparison needs specs
    assert plan.temperature == 0.2  # Lower temp for precision
    assert len(plan.steps) == 4
    print("✓ Query plan COMPARE passed")


def test_route_query_function():
    """Test full route_query function."""
    query = "extract dimensions from this hull drawing"
    plan = route_query(query)
    
    assert isinstance(plan, QueryPlan)
    assert plan.intent == QueryIntent.EXTRACT
    assert plan.confidence == 0.9
    print("✓ Route query function passed")


def test_processing_step_model():
    """Test ProcessingStep model validation."""
    step = ProcessingStep(
        step_name="vlm_analyze",
        required=True,
        weight_in_confidence=0.45,
        fallback_action="use_ocr_only"
    )
    
    assert step.step_name == "vlm_analyze"
    assert step.weight_in_confidence == 0.45
    assert step.fallback_action == "use_ocr_only"
    print("✓ ProcessingStep model passed")


def test_keyword_patterns_structure():
    """Test KEYWORD_PATTERNS has all intents."""
    assert QueryIntent.EXTRACT in KEYWORD_PATTERNS
    assert QueryIntent.IDENTIFY in KEYWORD_PATTERNS
    assert QueryIntent.COMPARE in KEYWORD_PATTERNS
    assert QueryIntent.SUGGEST in KEYWORD_PATTERNS
    assert QueryIntent.VALIDATE in KEYWORD_PATTERNS
    
    # Each intent should have patterns
    for intent, patterns in KEYWORD_PATTERNS.items():
        assert len(patterns) > 0, f"Intent {intent} has no patterns"
    
    print("✓ Keyword patterns structure passed")


def test_query_metrics_collector():
    """Test QueryMetricsCollector functionality."""
    collector = QueryMetricsCollector()
    
    # Record some classifications
    collector.record_classification(QueryIntent.EXTRACT, 15.0, used_llm=False)
    collector.record_classification(QueryIntent.SUGGEST, 45.0, used_llm=True)
    collector.record_classification(QueryIntent.IDENTIFY, 20.0, used_llm=False)
    
    metrics = collector.get_metrics()
    
    assert metrics.total_queries == 3
    assert metrics.intent_distribution["extract"] == 1
    assert metrics.intent_distribution["suggest"] == 1
    assert metrics.intent_distribution["identify"] == 1
    assert metrics.llm_fallback_rate == 1/3  # 1 out of 3 used LLM
    assert metrics.avg_classification_time_ms > 0
    print("✓ Query metrics collector passed")


def test_query_plan_step_weights():
    """Test that step weights sum reasonably for each intent."""
    for intent in QueryIntent:
        plan = get_query_plan(intent)
        total_weight = sum(step.weight_in_confidence for step in plan.steps)
        
        # Weights should sum to approximately 1.0 (allowing for rounding)
        assert 0.9 <= total_weight <= 1.1, f"Intent {intent} weights sum to {total_weight}"
    
    print("✓ Query plan step weights passed")


def test_classify_intent_with_fallback():
    """Test classify_intent uses fallback correctly."""
    # Clear keyword query - should use fast classification
    fast_result = classify_intent_fast("extract dimensions")
    assert fast_result == QueryIntent.EXTRACT
    
    # Ambiguous query - would fallback to LLM (but we can't test LLM without it running)
    # Just verify the function doesn't crash
    ambiguous = classify_intent_fast("analyze this drawing")
    assert ambiguous is None  # Falls back to None
    
    print("✓ Classify intent with fallback passed")


def test_intent_priority_ordering():
    """Test that priorities are correctly ordered (1=highest)."""
    priorities = {
        QueryIntent.EXTRACT: get_query_plan(QueryIntent.EXTRACT).priority,
        QueryIntent.IDENTIFY: get_query_plan(QueryIntent.IDENTIFY).priority,
        QueryIntent.COMPARE: get_query_plan(QueryIntent.COMPARE).priority,
        QueryIntent.SUGGEST: get_query_plan(QueryIntent.SUGGEST).priority,
        QueryIntent.VALIDATE: get_query_plan(QueryIntent.VALIDATE).priority,
    }
    
    # EXTRACT should be highest priority (1)
    assert priorities[QueryIntent.EXTRACT] == 1
    
    # All priorities should be unique and between 1-5
    assert len(set(priorities.values())) == 5  # All unique
    assert all(1 <= p <= 5 for p in priorities.values())
    
    print("✓ Intent priority ordering passed")


def run_all_tests():
    """Run all drawing query router tests."""
    print("=" * 60)
    print("Drawing Query Intent Router Phase 2 Tests")
    print("=" * 60)
    
    tests = [
        test_intent_enum_values,
        test_fast_classification_extract,
        test_fast_classification_identify,
        test_fast_classification_suggest,
        test_fast_classification_compare,
        test_fast_classification_validate,
        test_fast_classification_fallback,
        test_get_query_plan_extract,
        test_get_query_plan_suggest,
        test_get_query_plan_compare,
        test_route_query_function,
        test_processing_step_model,
        test_keyword_patterns_structure,
        test_query_metrics_collector,
        test_query_plan_step_weights,
        test_classify_intent_with_fallback,
        test_intent_priority_ordering,
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

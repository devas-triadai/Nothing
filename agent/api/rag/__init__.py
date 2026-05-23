"""AGRA Phase 2 — RAG pipeline package."""

# Drawing Analyzer exports
from .drawing_classifier import (
    classify_drawing,
    classify_tier1,
    classify_tier2_vlm,
    quick_classify,
    _get_recommended_analysis,
)

# Measurement Parser exports
from .measurement_parser import (
    parse_measurements,
    extract_dimensions,
    validate_dimensions,
    calculate_derived_dimensions,
    parse_unit,
    convert_to_meters,
    normalize_unit,
    parse_tolerance,
    format_tolerance,
)

# Phase 6: Confidence Scorer exports
from .confidence_scorer import (
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

# Compliance Module Phase 2: SOTR Parser exports
from .sotr_parser import (
    is_sotr_document,
    detect_sotr_in_text,
    extract_clauses,
    parse_sotr_document,
    parsed_clause_to_base_model,
    extract_clauses_to_models,
    ParsedClause,
)

# Compliance Module Phase 3: Clause Scorer exports
from .clause_scorer import (
    find_relevant_vendor_text,
    find_all_vendor_text,
    score_single_clause,
    score_clauses_batch,
    score_clause_against_vendor,
    score_all_clauses,
    generate_evaluation_summary,
    ScoringResult,
)

# Chat Enhancement Phase 2: Drawing Query Router exports
from .drawing_query_router import (
    classify_intent_fast,
    classify_intent,
    classify_intent_llm,
    get_query_plan,
    route_query,
    QueryIntent,
    QueryPlan,
    ProcessingStep,
    QueryMetricsCollector,
)

# Chat Enhancement Phase 3: Drawing Context Search exports
from .drawing_context_search import (
    DrawingSearchTerms,
    SearchResult,
    ContextAssembly,
    SearchMetrics,
    extract_search_terms,
    build_vessel_queries,
    build_drawing_queries,
    build_equipment_queries,
    build_compliance_queries,
    calculate_relevance_boost,
    search_drawing_context,
    quick_vessel_search,
    quick_drawing_search,
    quick_equipment_search,
)

# Chat Enhancement Phase 4: Drawing Suggestion Engine exports
from .drawing_suggestion_engine import (
    SuggestionType,
    Suggestion,
    SuggestionSet,
    SuggestionMetrics,
    generate_suggestions,
    generate_vessel_match_suggestions,
    generate_upgrade_suggestions,
    generate_advancement_suggestions,
    generate_quality_suggestions,
    generate_standardization_suggestions,
    generate_compliance_suggestions,
    quick_quality_suggestion,
    quick_vessel_suggestion,
)

__all__ = [
    # Drawing Classifier
    "classify_drawing",
    "classify_tier1",
    "classify_tier2_vlm",
    "quick_classify",
    "_get_recommended_analysis",
    # Measurement Parser
    "parse_measurements",
    "extract_dimensions",
    "validate_dimensions",
    "calculate_derived_dimensions",
    "parse_unit",
    "convert_to_meters",
    "normalize_unit",
    "parse_tolerance",
    "format_tolerance",
    # Confidence Scorer
    "calculate_ocr_confidence",
    "calculate_vlm_confidence",
    "calculate_validation_score",
    "calculate_measurement_consistency",
    "calculate_title_block_completeness",
    "calculate_overall_confidence",
    "calculate_all_confidence_scores",
    "assess_result_quality",
    "calculate_legacy_confidence",
    "ConfidenceWeights",
    # SOTR Parser
    "is_sotr_document",
    "detect_sotr_in_text",
    "extract_clauses",
    "parse_sotr_document",
    "parsed_clause_to_base_model",
    "extract_clauses_to_models",
    "ParsedClause",
    # Clause Scorer
    "find_relevant_vendor_text",
    "find_all_vendor_text",
    "score_single_clause",
    "score_clauses_batch",
    "score_clause_against_vendor",
    "score_all_clauses",
    "generate_evaluation_summary",
    "ScoringResult",
    # Chat Drawing Query Router (Phase 2)
    "classify_intent_fast",
    "classify_intent",
    "classify_intent_llm",
    "get_query_plan",
    "route_query",
    "QueryIntent",
    "QueryPlan",
    "ProcessingStep",
    "QueryMetricsCollector",
    # Chat Drawing Context Search (Phase 3)
    "DrawingSearchTerms",
    "SearchResult",
    "ContextAssembly",
    "SearchMetrics",
    "extract_search_terms",
    "build_vessel_queries",
    "build_drawing_queries",
    "build_equipment_queries",
    "build_compliance_queries",
    "calculate_relevance_boost",
    "search_drawing_context",
    "quick_vessel_search",
    "quick_drawing_search",
    "quick_equipment_search",
    # Chat Drawing Suggestion Engine (Phase 4)
    "SuggestionType",
    "Suggestion",
    "SuggestionSet",
    "SuggestionMetrics",
    "generate_suggestions",
    "generate_vessel_match_suggestions",
    "generate_upgrade_suggestions",
    "generate_advancement_suggestions",
    "generate_quality_suggestions",
    "generate_standardization_suggestions",
    "generate_compliance_suggestions",
    "quick_quality_suggestion",
    "quick_vessel_suggestion",
]

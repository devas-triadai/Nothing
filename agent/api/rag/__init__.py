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
]

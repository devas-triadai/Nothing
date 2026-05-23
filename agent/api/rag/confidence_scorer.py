"""
AGRA Phase 6 — Confidence Scoring & Quality Metrics
Calculates comprehensive confidence scores for drawing analysis results.

Factors:
1. OCR confidence (25%)
2. VLM extraction confidence (30%)
3. Validation pass rate (25%)
4. Drawing type classification confidence (20%)

Additional metrics:
- Title block completeness
- Measurement consistency
- Cross-reference validation
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum

from api.models.drawing_models import (
    DrawingAnalysisResult, AnalysisConfidence, StageConfidence,
    Dimension, TitleBlock, DrawingType, MeasurementUnit
)

logger = logging.getLogger("agra.confidence_scorer")


# ═══════════════════════════════════════════════════════════════
#  WEIGHT CONFIGURATION
# ═══════════════════════════════════════════════════════════════

class ConfidenceWeights:
    """Default weights for overall confidence calculation."""
    OCR = 0.25
    VLM = 0.30
    VALIDATION = 0.25
    CLASSIFICATION = 0.20


# ═══════════════════════════════════════════════════════════════
#  SCORING FACTORS
# ═══════════════════════════════════════════════════════════════

@dataclass
class ScoringFactors:
    """Raw scoring factors before weighting."""
    ocr_confidence: float = 0.0
    vlm_confidence: float = 0.0
    validation_score: float = 0.0
    classification_confidence: float = 0.0
    title_block_completeness: float = 0.0
    measurement_consistency: float = 0.0


# ═══════════════════════════════════════════════════════════════
#  OCR CONFIDENCE CALCULATION
# ═══════════════════════════════════════════════════════════════

def calculate_ocr_confidence(ocr_metadata: Dict[str, Any]) -> float:
    """
    Calculate OCR confidence from tesseract_ocr output.
    
    Factors:
    - Printed text confidence (primary)
    - Presence of handwritten text (bonus)
    - Text coverage ratio
    """
    if not ocr_metadata:
        return 0.30  # Low confidence if no metadata
    
    # Base confidence from tesseract
    printed_conf = ocr_metadata.get("printed_confidence", 0.0)
    
    # Convert percentage to 0-1 scale
    if printed_conf > 100:
        printed_conf = printed_conf / 100.0
    
    # Normalize to 0-1
    base_score = min(printed_conf / 100.0, 1.0)
    
    # Boost for having text
    printed_text = ocr_metadata.get("printed_text", "")
    handwritten_text = ocr_metadata.get("handwritten_text", "")
    
    if len(printed_text) > 100:
        base_score += 0.05
    if len(handwritten_text) > 20:
        base_score += 0.03  # Bonus for handwriting detection
    
    # Penalty for very short text (likely failed OCR)
    if len(printed_text) < 50:
        base_score *= 0.7
    
    return min(base_score, 0.98)


# ═══════════════════════════════════════════════════════════════
#  VLM CONFIDENCE CALCULATION
# ═══════════════════════════════════════════════════════════════

def calculate_vlm_confidence(
    vlm_result: Dict[str, Any],
    drawing_type: DrawingType
) -> float:
    """
    Calculate VLM extraction confidence.
    
    Factors:
    - Title block completeness
    - Number of dimensions extracted
    - Equipment tags found
    - Compliance notes presence
    """
    scores = []
    
    # Title block completeness (max 0.30)
    tb = vlm_result.get("title_block", {})
    critical_fields = ["drawing_number", "vessel_name", "project_name", "scale"]
    tb_score = sum(1 for f in critical_fields if tb.get(f)) / len(critical_fields)
    scores.append(tb_score * 0.30)
    
    # Dimensions (max 0.25)
    dims = vlm_result.get("dimensions", [])
    if len(dims) >= 5:
        scores.append(0.25)
    elif len(dims) >= 3:
        scores.append(0.20)
    elif len(dims) >= 1:
        scores.append(0.12)
    else:
        scores.append(0.05)
    
    # Equipment tags (max 0.25)
    tags = vlm_result.get("equipment_tags", [])
    if len(tags) >= 10:
        scores.append(0.25)
    elif len(tags) >= 5:
        scores.append(0.20)
    elif len(tags) >= 1:
        scores.append(0.12)
    else:
        scores.append(0.05)
    
    # Compliance notes (max 0.20)
    notes = vlm_result.get("compliance_notes", [])
    if len(notes) >= 3:
        scores.append(0.20)
    elif len(notes) >= 1:
        scores.append(0.15)
    else:
        scores.append(0.08)
    
    # Type-specific adjustments
    total = sum(scores)
    
    if drawing_type == DrawingType.TITLE_BLOCK_ONLY:
        # For title block only, weight title block higher
        total = tb_score * 0.70 + total * 0.30
    
    return min(total, 0.95)


# ═══════════════════════════════════════════════════════════════
#  VALIDATION SCORE CALCULATION
# ═══════════════════════════════════════════════════════════════

def calculate_validation_score(
    dimensions: List[Dimension],
    validation_issues: List[Dict[str, Any]]
) -> float:
    """
    Calculate validation pass rate score.
    
    Factors:
    - Number of issues found
    - Severity of issues
    - Cross-dimension consistency
    """
    if not dimensions:
        return 0.40  # Neutral if no dimensions to validate
    
    # Base score
    base_score = 0.90
    
    # Deduct for issues
    for issue in validation_issues:
        severity = issue.get("severity", "info")
        if severity == "error":
            base_score -= 0.15
        elif severity == "warning":
            base_score -= 0.08
        else:
            base_score -= 0.03
    
    # Boost for high-confidence dimensions
    high_conf_dims = sum(1 for d in dimensions if d.confidence >= 0.85)
    if high_conf_dims >= len(dimensions) * 0.7:
        base_score += 0.05
    
    # Boost for dimensions with tolerances
    tol_dims = sum(1 for d in dimensions if d.tolerance)
    if tol_dims >= len(dimensions) * 0.3:
        base_score += 0.03
    
    return max(min(base_score, 0.95), 0.20)


# ═══════════════════════════════════════════════════════════════
#  MEASUREMENT CONSISTENCY SCORE
# ═══════════════════════════════════════════════════════════════

def calculate_measurement_consistency(dimensions: List[Dimension]) -> float:
    """
    Check internal consistency of measurements.
    
    For GA drawings: L > B > D should hold
    """
    if len(dimensions) < 2:
        return 0.50  # Not enough data
    
    # Find key dimensions
    length_val = None
    beam_val = None
    depth_val = None
    
    for dim in dimensions:
        name_lower = dim.name.lower()
        # Convert to meters for comparison
        value_m = dim.value
        if dim.unit == MeasurementUnit.MILLIMETER:
            value_m = dim.value / 1000.0
        elif dim.unit == MeasurementUnit.CENTIMETER:
            value_m = dim.value / 100.0
        
        if any(x in name_lower for x in ["length", "loa", "lbp"]):
            length_val = value_m
        elif any(x in name_lower for x in ["beam", "breadth", "width"]):
            beam_val = value_m
        elif any(x in name_lower for x in ["depth", "moulded depth"]):
            depth_val = value_m
    
    # Check L > B > D
    checks_passed = 0
    checks_total = 0
    
    if length_val and beam_val:
        checks_total += 1
        if length_val > beam_val:
            checks_passed += 1
    
    if beam_val and depth_val:
        checks_total += 1
        if beam_val > depth_val:
            checks_passed += 1
    
    if length_val and depth_val:
        checks_total += 1
        if length_val > depth_val:
            checks_passed += 1
    
    if checks_total == 0:
        return 0.60  # Neutral
    
    consistency = checks_passed / checks_total
    return 0.50 + (consistency * 0.45)  # Scale to 0.50-0.95


# ═══════════════════════════════════════════════════════════════
#  TITLE BLOCK COMPLETENESS
# ═══════════════════════════════════════════════════════════════

def calculate_title_block_completeness(title_block: TitleBlock) -> float:
    """
    Calculate title block completeness score.
    
    Critical fields: drawing_number, vessel_name, project_name, scale
    Important fields: revision, date, drawn_by, company
    """
    critical_fields = [
        title_block.drawing_number,
        title_block.vessel_name,
        title_block.project_name,
        title_block.scale,
    ]
    important_fields = [
        title_block.revision,
        title_block.date,
        title_block.drawn_by,
        title_block.company,
    ]
    
    critical_score = sum(1 for f in critical_fields if f) / len(critical_fields)
    important_score = sum(1 for f in important_fields if f) / len(important_fields)
    
    # Weight critical higher
    total_score = (critical_score * 0.70) + (important_score * 0.30)
    
    return min(total_score, 0.98)


# ═══════════════════════════════════════════════════════════════
#  MAIN CONFIDENCE CALCULATION
# ═══════════════════════════════════════════════════════════════

def calculate_overall_confidence(
    ocr_confidence: float,
    vlm_confidence: float,
    validation_score: float,
    classification_confidence: float,
    weights: Optional[Dict[str, float]] = None
) -> float:
    """
    Calculate weighted overall confidence.
    
    Default weights:
    - OCR: 25%
    - VLM: 30%
    - Validation: 25%
    - Classification: 20%
    """
    if weights is None:
        weights = {
            "ocr": ConfidenceWeights.OCR,
            "vlm": ConfidenceWeights.VLM,
            "validation": ConfidenceWeights.VALIDATION,
            "classification": ConfidenceWeights.CLASSIFICATION,
        }
    
    overall = (
        ocr_confidence * weights["ocr"] +
        vlm_confidence * weights["vlm"] +
        validation_score * weights["validation"] +
        classification_confidence * weights["classification"]
    )
    
    return round(min(overall, 0.98), 2)


def calculate_all_confidence_scores(
    ocr_metadata: Dict[str, Any],
    vlm_result: Dict[str, Any],
    dimensions: List[Dimension],
    title_block: TitleBlock,
    drawing_type: DrawingType,
    classification_confidence: float,
    validation_issues: List[Dict[str, Any]],
    stage_scores: List[StageConfidence]
) -> AnalysisConfidence:
    """
    Calculate all confidence scores and return AnalysisConfidence model.
    """
    # Calculate individual scores
    ocr_conf = calculate_ocr_confidence(ocr_metadata)
    vlm_conf = calculate_vlm_confidence(vlm_result, drawing_type)
    val_score = calculate_validation_score(dimensions, validation_issues)
    tb_completeness = calculate_title_block_completeness(title_block)
    meas_consistency = calculate_measurement_consistency(dimensions)
    
    # Weight validation score with measurement consistency
    combined_validation = (val_score * 0.70) + (meas_consistency * 0.30)
    
    # Calculate overall
    overall = calculate_overall_confidence(
        ocr_confidence=ocr_conf,
        vlm_confidence=vlm_conf,
        validation_score=combined_validation,
        classification_confidence=classification_confidence
    )
    
    return AnalysisConfidence(
        overall_confidence=overall,
        drawing_type_confidence=classification_confidence,
        ocr_confidence=ocr_conf,
        vlm_confidence=vlm_conf,
        validation_score=combined_validation,
        title_block_completeness=tb_completeness,
        stage_scores=stage_scores
    )


# ═══════════════════════════════════════════════════════════════
#  QUALITY ASSESSMENT
# ═══════════════════════════════════════════════════════════════

def assess_result_quality(result: DrawingAnalysisResult) -> Dict[str, Any]:
    """
    Provide detailed quality assessment of analysis result.
    
    Returns dict with:
    - quality_level: "excellent" | "good" | "acceptable" | "poor"
    - recommendations: List of improvement suggestions
    - warnings: List of issues found
    """
    conf = result.confidence
    quality_level = "poor"
    
    if conf.overall_confidence >= 0.90:
        quality_level = "excellent"
    elif conf.overall_confidence >= 0.75:
        quality_level = "good"
    elif conf.overall_confidence >= 0.60:
        quality_level = "acceptable"
    
    recommendations = []
    warnings = []
    
    # OCR recommendations
    if conf.ocr_confidence < 0.60:
        recommendations.append("OCR confidence is low. Consider rescanning at higher resolution or improving image quality.")
        warnings.append("Text extraction may be incomplete.")
    elif conf.ocr_confidence < 0.75:
        recommendations.append("Some text may not be fully captured. Review handwritten annotations manually.")
    
    # VLM recommendations
    if conf.vlm_confidence < 0.60:
        recommendations.append("VLM extraction confidence is low. Manual review of all extracted values recommended.")
    elif conf.vlm_confidence < 0.75:
        recommendations.append("Some parameters may be missing. Verify all critical dimensions are captured.")
    
    # Validation recommendations
    if conf.validation_score < 0.60:
        recommendations.append("Validation found significant issues. Cross-check measurements against vessel class norms.")
    
    # Title block recommendations
    if conf.title_block_completeness < 0.50:
        recommendations.append("Title block is incomplete. Verify drawing identification metadata.")
    
    # Dimension recommendations
    dim_count = len(result.dimensions)
    if dim_count == 0:
        warnings.append("No dimensions were extracted from the drawing.")
    elif dim_count < 3:
        recommendations.append("Few dimensions found. Check if drawing contains additional measurement callouts.")
    
    return {
        "quality_level": quality_level,
        "overall_confidence": conf.overall_confidence,
        "recommendations": recommendations,
        "warnings": warnings,
        "confidence_breakdown": {
            "ocr": conf.ocr_confidence,
            "vlm": conf.vlm_confidence,
            "validation": conf.validation_score,
            "classification": conf.drawing_type_confidence,
            "title_block": conf.title_block_completeness,
        }
    }


# ═══════════════════════════════════════════════════════════════
#  LEGACY COMPATIBILITY
# ═══════════════════════════════════════════════════════════════

def calculate_legacy_confidence(
    ocr_result: Dict[str, Any],
    extracted_data: Dict[str, Any]
) -> float:
    """
    Calculate simple confidence for legacy drawing.py output format.
    """
    ocr_conf = ocr_result.get("printed_confidence", 0.0)
    
    # Normalize
    if ocr_conf > 100:
        ocr_conf = ocr_conf / 100.0
    
    # Boost for data presence
    has_dims = bool(extracted_data.get("dimensions"))
    has_tags = bool(extracted_data.get("equipment_tags"))
    
    score = ocr_conf * 0.6
    if has_dims:
        score += 0.20
    if has_tags:
        score += 0.20
    
    return min(score, 0.95)


# ═══════════════════════════════════════════════════════════════
#  TESTING
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Test cases
    print("Confidence Scorer Tests")
    print("=" * 60)
    
    # Test 1: OCR confidence
    ocr_meta = {"printed_confidence": 85.5, "printed_text": "Length 100m", "handwritten_text": ""}
    print(f"OCR confidence (85.5%): {calculate_ocr_confidence(ocr_meta):.2f}")
    
    # Test 2: VLM confidence
    vlm_res = {
        "title_block": {"drawing_number": "GA-001", "vessel_name": "Test"},
        "dimensions": [{"name": "L", "value": 100}, {"name": "B", "value": 15}],
        "equipment_tags": [{"tag_id": "P-1"}],
        "compliance_notes": []
    }
    print(f"VLM confidence (GA): {calculate_vlm_confidence(vlm_res, DrawingType.GENERAL_ARRANGEMENT):.2f}")
    
    # Test 3: Overall confidence
    overall = calculate_overall_confidence(0.85, 0.80, 0.75, 0.90)
    print(f"Overall confidence: {overall:.2f}")
    
    print("=" * 60)

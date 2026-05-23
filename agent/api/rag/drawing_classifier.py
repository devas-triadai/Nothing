"""
AGRA Phase 1 — Drawing Type Classifier
Two-tier classification engine for engineering drawings:
  Tier 1: Fast heuristic (filename + OCR content patterns) — ~50ms
  Tier 2: VLM vision classification — ~500ms

Maps to DrawingType enum from drawing_models.
"""

import base64
import logging
import re
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path

from api.models.drawing_models import DrawingType, DrawingFeature

logger = logging.getLogger("agra.drawing_classifier")


# ═══════════════════════════════════════════════════════════════
#  TIER 1 — FAST HEURISTIC CLASSIFICATION
# ═══════════════════════════════════════════════════════════════

# Filename patterns for drawing type detection
_FILENAME_PATTERNS: List[Tuple[str, DrawingType, List[DrawingFeature], float]] = [
    # General Arrangement
    (r"(?i)\b(GA|general\.arrangement|generalarrangement|overall)\b", 
     DrawingType.GENERAL_ARRANGEMENT, 
     [DrawingFeature.HULL_PROFILE, DrawingFeature.DIMENSION_LINES, DrawingFeature.TITLE_BLOCK], 
     0.90),
    
    # Piping / Fluid systems
    (r"(?i)\b(piping|pipe|line|diagram|flow|hydraulic|pneumatic|bilge|ballast|fire\.main)\b",
     DrawingType.PIPING_DIAGRAM,
     [DrawingFeature.PIPING_RUNS, DrawingFeature.VALVE_SYMBOLS, DrawingFeature.EQUIPMENT_SYMBOLS],
     0.85),
    
    # Electrical / Wiring
    (r"(?i)\b(electrical|wiring|circuit|schematic|power|distribution|lighting|cable)\b",
     DrawingType.ELECTRICAL_SCHEMATIC,
     [DrawingFeature.WIRING_CIRCUITS, DrawingFeature.EQUIPMENT_SYMBOLS],
     0.85),
    
    # Structural / Steel
    (r"(?i)\b(structural|steel|hull|frame|longitudinal|transverse|section|welding|plate)\b",
     DrawingType.STRUCTURAL_DRAWING,
     [DrawingFeature.SECTION_VIEWS, DrawingFeature.WELD_SYMBOLS],
     0.85),
    
    # Equipment / Machinery layout
    (r"(?i)\b(equipment|layout|machinery|engine|propulsion|generator|arrangement)\b",
     DrawingType.EQUIPMENT_LAYOUT,
     [DrawingFeature.EQUIPMENT_SYMBOLS, DrawingFeature.DIMENSION_LINES],
     0.80),
    
    # Blueprint / Drawing generic
    (r"(?i)\b(blueprint|drawing|plan|view|elevation|profile)\b",
     DrawingType.UNKNOWN,
     [DrawingFeature.TITLE_BLOCK],
     0.60),
]

# Content patterns from OCR text
_CONTENT_PATTERNS: List[Tuple[str, DrawingType, List[DrawingFeature], float]] = [
    # General Arrangement specific
    (r"(?i)(general\s+arrangement|overall\s+length|moulded\s+breadth|moulded\s+depth)",
     DrawingType.GENERAL_ARRANGEMENT,
     [DrawingFeature.HULL_PROFILE, DrawingFeature.DIMENSION_LINES],
     0.95),
    
    # Title block indicators
    (r"(?i)(title\s*block|drawn\s*by|checked\s*by|approved\s*by|scale\s*[:=]|revision)",
     DrawingType.TITLE_BLOCK_ONLY,
     [DrawingFeature.TITLE_BLOCK],
     0.70),
    
    # Piping indicators
    (r"(?i)(pipe\s+size|nominal\s+bore|valve|pump|tank|pressure|flow\s+rate)",
     DrawingType.PIPING_DIAGRAM,
     [DrawingFeature.PIPING_RUNS, DrawingFeature.VALVE_SYMBOLS],
     0.90),
    
    # Electrical indicators
    (r"(?i)(voltage|current|power|kw|cable|circuit\s*breaker|panel|distribution)",
     DrawingType.ELECTRICAL_SCHEMATIC,
     [DrawingFeature.WIRING_CIRCUITS],
     0.90),
    
    # Structural indicators
    (r"(?i)(steel\s+grade|plate\s+thickness|welding\s*symbol|section\s+modulus|frame\s+spacing)",
     DrawingType.STRUCTURAL_DRAWING,
     [DrawingFeature.WELD_SYMBOLS, DrawingFeature.SECTION_VIEWS],
     0.90),
    
    # Equipment tags
    (r"(?i)(equipment\s*list|tag\s*no|item\s*no|description|manufacturer|model)",
     DrawingType.EQUIPMENT_LAYOUT,
     [DrawingFeature.EQUIPMENT_SYMBOLS],
     0.80),
]

# Drawing type characteristics for validation
_DRAWING_TYPE_HINTS = {
    DrawingType.GENERAL_ARRANGEMENT: {
        "expected_features": [DrawingFeature.HULL_PROFILE, DrawingFeature.DIMENSION_LINES],
        "typical_scales": ["1:50", "1:100", "1:200", "1:500"],
        "key_words": ["length", "beam", "depth", "draft", "displacement"],
    },
    DrawingType.PIPING_DIAGRAM: {
        "expected_features": [DrawingFeature.PIPING_RUNS, DrawingFeature.VALVE_SYMBOLS],
        "typical_scales": ["1:20", "1:50", "not to scale", "schematic"],
        "key_words": ["pipe", "valve", "pump", "flow", "pressure"],
    },
    DrawingType.ELECTRICAL_SCHEMATIC: {
        "expected_features": [DrawingFeature.WIRING_CIRCUITS],
        "typical_scales": ["not to scale", "schematic", "diagram"],
        "key_words": ["voltage", "current", "power", "cable", "circuit"],
    },
    DrawingType.STRUCTURAL_DRAWING: {
        "expected_features": [DrawingFeature.WELD_SYMBOLS, DrawingFeature.SECTION_VIEWS],
        "typical_scales": ["1:5", "1:10", "1:20", "1:50"],
        "key_words": ["steel", "welding", "plate", "section", "frame"],
    },
    DrawingType.EQUIPMENT_LAYOUT: {
        "expected_features": [DrawingFeature.EQUIPMENT_SYMBOLS],
        "typical_scales": ["1:20", "1:50", "1:100"],
        "key_words": ["equipment", "machinery", "arrangement", "layout"],
    },
}


# ═══════════════════════════════════════════════════════════════
#  TIER 1 IMPLEMENTATION
# ═══════════════════════════════════════════════════════════════

def classify_tier1(filename: str, ocr_text: str = "") -> Dict[str, Any]:
    """
    Fast heuristic classification using filename and OCR content.
    
    Returns:
        {
            "drawing_type": DrawingType,
            "confidence": float (0-1),
            "detected_features": List[DrawingFeature],
            "tier": 1,
            "match_source": "filename" | "content" | "both",
        }
    """
    best_type = DrawingType.UNKNOWN
    best_confidence = 0.0
    best_features: List[DrawingFeature] = []
    match_source = "none"
    
    # --- Pass 1: Filename patterns ---
    filename_matches = []
    for pattern, dtype, features, confidence in _FILENAME_PATTERNS:
        if re.search(pattern, filename):
            filename_matches.append((dtype, features, confidence))
            if confidence > best_confidence:
                best_type = dtype
                best_features = features
                best_confidence = confidence
                match_source = "filename"
    
    # --- Pass 2: Content patterns (higher priority if found) ---
    content_matches = []
    if ocr_text:
        for pattern, dtype, features, confidence in _CONTENT_PATTERNS:
            matches = re.findall(pattern, ocr_text[:5000])
            if matches:
                content_matches.append((dtype, features, confidence))
                # Content matches have higher priority than filename
                adjusted_confidence = min(confidence + 0.05, 0.98)
                if adjusted_confidence > best_confidence:
                    best_type = dtype
                    best_features = features
                    best_confidence = adjusted_confidence
                    match_source = "content" if match_source == "none" else "both"
    
    # --- Boost confidence if both match ---
    if match_source == "both" and best_confidence < 0.95:
        best_confidence = min(best_confidence + 0.10, 0.95)
    
    # --- Default case ---
    if best_type == DrawingType.UNKNOWN and not best_features:
        # Try to detect if it's at least a technical drawing
        if any(kw in filename.lower() for kw in ["dwg", "drw", "plan", "sheet"]):
            best_type = DrawingType.UNKNOWN
            best_features = [DrawingFeature.TITLE_BLOCK]
            best_confidence = 0.50
            match_source = "filename"
    
    return {
        "drawing_type": best_type,
        "confidence": round(best_confidence, 2),
        "detected_features": list(set(best_features)),  # Deduplicate
        "tier": 1,
        "match_source": match_source,
        "filename_matches": len(filename_matches),
        "content_matches": len(content_matches),
    }


# ═══════════════════════════════════════════════════════════════
#  TIER 2 — VLM VISION CLASSIFICATION
# ═══════════════════════════════════════════════════════════════

_VLM_CLASSIFY_PROMPT = """You are an expert naval architect and engineering document classifier.
Analyze this engineering drawing image and classify its type.

Look for these specific drawing types:
1. GENERAL ARRANGEMENT (GA) - Shows vessel profile, overall dimensions, hull lines
2. PIPING DIAGRAM - Fluid systems, pipes, valves, pumps, flow directions
3. ELECTRICAL SCHEMATIC - Wiring, circuits, power distribution, cable runs
4. STRUCTURAL DRAWING - Steel details, welds, sections, frames, plates
5. EQUIPMENT LAYOUT - Machinery arrangement, equipment positions
6. TITLE BLOCK ONLY - Just the title/metadata area, no technical content visible

Also identify visible features:
- hull_profile: Side view of vessel hull
- dimension_lines: Measurement lines with values
- title_block: Project info box with drawing number
- equipment_symbols: Machinery/equipment icons
- piping_runs: Pipe lines and routes
- valve_symbols: Valve control symbols
- wiring_circuits: Electrical connections
- weld_symbols: Welding specification marks
- section_views: Cross-sectional views
- stamp_annotations: Handwritten stamps or notes

Return ONLY valid JSON in this exact format:
{{
  "drawing_type": "general_arrangement|piping_diagram|electrical_schematic|structural_drawing|equipment_layout|title_block_only|unknown",
  "confidence": 0.0-1.0,
  "detected_features": ["feature1", "feature2"],
  "visible_elements": ["brief description of what you see"],
  "scale_detected": "scale if visible, else null",
  "has_title_block": true/false
}}"""


def classify_tier2_vlm(
    image_bytes: bytes,
    image_content_type: str = "image/png"
) -> Optional[Dict[str, Any]]:
    """
    VLM-based vision classification for drawings.
    
    Args:
        image_bytes: Raw image bytes
        image_content_type: MIME type of image
        
    Returns:
        Classification result dict or None if VLM unavailable
    """
    try:
        from api.rag import llm as llm_engine
        import json
        
        # Convert to base64
        base64_image = base64.b64encode(image_bytes).decode("utf-8")
        data_uri = f"data:{image_content_type};base64,{base64_image}"
        
        messages = [
            {
                "role": "system",
                "content": "You are a military engineering drawing classifier. Return only valid JSON."
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _VLM_CLASSIFY_PROMPT},
                    {"type": "image_url", "image_url": {"url": data_uri}}
                ]
            }
        ]
        
        # Use non-streaming generate for classification (faster)
        raw = llm_engine.generate(messages, max_tokens=400, temperature=0.1)
        
        # Clean and parse JSON
        cleaned = re.sub(r'^```(?:json)?\s*', '', raw.strip(), flags=re.MULTILINE)
        cleaned = re.sub(r'```\s*$', '', cleaned.strip(), flags=re.MULTILINE)
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        if start == -1 or end == 0:
            logger.warning("VLM classification: No JSON found in response")
            return None
        
        result = json.loads(cleaned[start:end])
        
        # Parse drawing type
        type_str = result.get("drawing_type", "unknown").lower()
        try:
            drawing_type = DrawingType(type_str)
        except ValueError:
            # Map common variations
            type_mapping = {
                "ga": DrawingType.GENERAL_ARRANGEMENT,
                "general": DrawingType.GENERAL_ARRANGEMENT,
                "arrangement": DrawingType.GENERAL_ARRANGEMENT,
                "piping": DrawingType.PIPING_DIAGRAM,
                "pipe": DrawingType.PIPING_DIAGRAM,
                "electrical": DrawingType.ELECTRICAL_SCHEMATIC,
                "wiring": DrawingType.ELECTRICAL_SCHEMATIC,
                "structural": DrawingType.STRUCTURAL_DRAWING,
                "steel": DrawingType.STRUCTURAL_DRAWING,
                "equipment": DrawingType.EQUIPMENT_LAYOUT,
                "machinery": DrawingType.EQUIPMENT_LAYOUT,
                "title": DrawingType.TITLE_BLOCK_ONLY,
                "unknown": DrawingType.UNKNOWN,
            }
            drawing_type = type_mapping.get(type_str, DrawingType.UNKNOWN)
        
        # Parse features
        feature_strs = result.get("detected_features", [])
        detected_features = []
        for fs in feature_strs:
            try:
                # Handle both enum values and raw strings
                if isinstance(fs, str):
                    fs_clean = fs.lower().replace(" ", "_").replace("-", "_")
                    detected_features.append(DrawingFeature(fs_clean))
            except ValueError:
                # Feature not in enum, skip
                pass
        
        vlm_confidence = float(result.get("confidence", 0.8))
        
        return {
            "drawing_type": drawing_type,
            "confidence": round(min(vlm_confidence, 0.98), 2),
            "detected_features": detected_features,
            "visible_elements": result.get("visible_elements", []),
            "scale_detected": result.get("scale_detected"),
            "has_title_block": result.get("has_title_block", False),
            "tier": 2,
            "raw_vlm_response": result,
        }
        
    except Exception as e:
        logger.warning("VLM classification failed: %s", e)
        return None


# ═══════════════════════════════════════════════════════════════
#  MAIN CLASSIFICATION ENTRY POINT
# ═══════════════════════════════════════════════════════════════

def classify_drawing(
    filename: str,
    ocr_text: str = "",
    image_bytes: Optional[bytes] = None,
    image_content_type: str = "image/png",
    force_vlm: bool = False,
    confidence_threshold: float = 0.75,
) -> Dict[str, Any]:
    """
    Main drawing classification entry point.
    
    Strategy:
      1. Always run Tier 1 (fast)
      2. Escalate to Tier 2 if Tier 1 confidence < threshold or force_vlm=True
      3. Combine results if both run
    
    Args:
        filename: Original filename
        ocr_text: OCR-extracted text (optional)
        image_bytes: Raw image bytes for VLM classification (optional)
        image_content_type: MIME type
        force_vlm: Force VLM classification even if Tier 1 is confident
        confidence_threshold: Minimum Tier 1 confidence before escalating
        
    Returns:
        {
            "drawing_type": DrawingType,
            "confidence": float,
            "detected_features": List[DrawingFeature],
            "classification_method": "tier1" | "tier2" | "combined",
            "tier1_result": {...} | None,
            "tier2_result": {...} | None,
            "recommended_analysis": str,
        }
    """
    # --- Step 1: Tier 1 Classification ---
    tier1_result = classify_tier1(filename, ocr_text)
    
    # --- Step 2: Decide on Tier 2 ---
    need_tier2 = (
        force_vlm or
        tier1_result["confidence"] < confidence_threshold or
        tier1_result["drawing_type"] == DrawingType.UNKNOWN
    )
    
    tier2_result = None
    if need_tier2 and image_bytes:
        tier2_result = classify_tier2_vlm(image_bytes, image_content_type)
    
    # --- Step 3: Combine Results ---
    if tier2_result:
        # Both ran - use confidence-weighted selection
        if tier2_result["confidence"] > tier1_result["confidence"]:
            final_type = tier2_result["drawing_type"]
            final_confidence = tier2_result["confidence"]
            final_features = list(set(
                tier1_result["detected_features"] + tier2_result["detected_features"]
            ))
            method = "tier2" if tier2_result["confidence"] > tier1_result["confidence"] + 0.15 else "combined"
        else:
            final_type = tier1_result["drawing_type"]
            final_confidence = tier1_result["confidence"]
            final_features = tier1_result["detected_features"]
            method = "tier1"
    else:
        # Only Tier 1 ran
        final_type = tier1_result["drawing_type"]
        final_confidence = tier1_result["confidence"]
        final_features = tier1_result["detected_features"]
        method = "tier1"
    
    # --- Step 4: Determine Recommended Analysis ---
    recommended = _get_recommended_analysis(final_type, final_features, final_confidence)
    
    return {
        "drawing_type": final_type,
        "confidence": round(final_confidence, 2),
        "detected_features": final_features,
        "classification_method": method,
        "tier1_result": tier1_result,
        "tier2_result": tier2_result,
        "recommended_analysis": recommended,
    }


def _get_recommended_analysis(
    drawing_type: DrawingType,
    features: List[DrawingFeature],
    confidence: float
) -> str:
    """Determine recommended analysis depth based on classification."""
    
    if confidence < 0.50:
        return "manual_review"  # Too uncertain
    
    if drawing_type == DrawingType.TITLE_BLOCK_ONLY:
        return "metadata_only"  # Just extract title block
    
    if drawing_type == DrawingType.GENERAL_ARRANGEMENT:
        if DrawingFeature.DIMENSION_LINES in features:
            return "full_extraction"  # GA with dimensions - extract all
        return "title_block_and_profile"
    
    if drawing_type in (DrawingType.PIPING_DIAGRAM, DrawingType.ELECTRICAL_SCHEMATIC):
        return "equipment_and_routing"
    
    if drawing_type == DrawingType.STRUCTURAL_DRAWING:
        return "details_and_welds"
    
    if drawing_type == DrawingType.EQUIPMENT_LAYOUT:
        return "equipment_positions"
    
    return "standard_extraction"  # Default


def quick_classify(filename: str, ocr_preview: str = "") -> DrawingType:
    """
    Ultra-fast classification for UI hints.
    Returns just the DrawingType without full analysis.
    """
    result = classify_tier1(filename, ocr_preview)
    return result["drawing_type"]


# ═══════════════════════════════════════════════════════════════
#  TESTING & VALIDATION
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Test cases
    test_cases = [
        ("GA-001-REV-A.pdf", "General Arrangement Drawing"),
        ("Piping_Diagram_Bilge.pdf", "Bilge and Ballast System"),
        ("Electrical_Power_Distribution.dwg", "Main Power Distribution"),
        ("Hull_Structure_Section_A.pdf", "Transverse Section at Frame 50"),
        ("Equipment_Layout_Engine_Room.dwg", "Main Engine and Generators"),
        ("random.pdf", ""),
    ]
    
    print("Drawing Classifier Test Results:")
    print("=" * 60)
    
    for filename, ocr_preview in test_cases:
        result = classify_tier1(filename, ocr_preview)
        print(f"\nFile: {filename}")
        print(f"  Type: {result['drawing_type'].value}")
        print(f"  Confidence: {result['confidence']}")
        print(f"  Features: {[f.value for f in result['detected_features']]}")
        print(f"  Source: {result['match_source']}")
        print(f"  Recommended: {_get_recommended_analysis(result['drawing_type'], result['detected_features'], result['confidence'])}")

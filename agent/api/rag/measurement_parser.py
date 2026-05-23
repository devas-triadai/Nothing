"""
AGRA Phase 4 — Measurement Parser & Validator
Extracts and validates engineering measurements from drawing text.

Features:
- Regex patterns for formats: 105.5 m, ±0.5 mm, 42'6"
- Unit normalization (all to metric)
- Tolerance parsing: 100 ± 2 mm
- Cross-dimension validation (L > B > D)
- Outlier detection against vessel class norms
"""

import re
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum

from api.models.drawing_models import Dimension, MeasurementUnit, ToleranceSpec

logger = logging.getLogger("agra.measurement_parser")


# ═══════════════════════════════════════════════════════════════
#  MEASUREMENT REGEX PATTERNS
# ═══════════════════════════════════════════════════════════════

# Primary dimension patterns
_DIMENSION_PATTERNS = [
    # Pattern: Name + Value + Unit (with optional tolerance)
    # "Overall Length 105.5 m" or "LBP = 98.5 m"
    (
        re.compile(
            r'(?i)(overall\s+length|length|lbp|loa|beam|breadth|depth|draft|height|diameter|radius)'
            r'\s*[=:]?\s*'
            r'(\d+(?:\.\d+)?)'
            r'\s*'
            r'(m|mm|cm|meters?|millimetres?|metres?)',
            re.IGNORECASE
        ),
        "metric_with_name"
    ),
    
    # Pattern: Dimension with tolerance "100 ± 2 mm" or "50 +1/-0.5 mm"
    (
        re.compile(
            r'(?i)(\d+(?:\.\d+)?)\s*'
            r'([±+-]\d+(?:\.\d+)?)?\s*'
            r'(mm|cm|m|meters?|millimetres?|metres?)',
            re.IGNORECASE
        ),
        "with_tolerance"
    ),
    
    # Pattern: Imperial dimensions "42'6"" or "140 ft"
    (
        re.compile(
            r'(?i)(\d+)[\'′]\s*(\d+(?:\.\d+)?)?[\"″]?',
            re.IGNORECASE
        ),
        "imperial_ft_in"
    ),
    
    # Pattern: Range format "100 - 150 mm" or "100 to 150 m"
    (
        re.compile(
            r'(?i)(\d+(?:\.\d+)?)\s*(?:-|to|~)\s*(\d+(?:\.\d+)?)\s*'
            r'(mm|cm|m|meters?|millimetres?|metres?)',
            re.IGNORECASE
        ),
        "range"
    ),
    
    # Pattern: Standalone with unit "105.5m" or "500 mm"
    (
        re.compile(
            r'(?i)\b(\d+(?:\.\d+)?)\s*(mm|cm|m)\b',
            re.IGNORECASE
        ),
        "standalone"
    ),
]

# Tolerance patterns
_TOLERANCE_PATTERNS = [
    # Symmetric: ±0.5, +/- 0.5
    (re.compile(r'[±+-](\d+(?:\.\d+)?)'), "symmetric"),
    # Asymmetric: +1/-0.5
    (re.compile(r'\+(\d+(?:\.\d+)?)/-(\d+(?:\.\d+)?)'), "asymmetric_plus_minus"),
    # Asymmetric: -0/+1
    (re.compile(r'-(\d+(?:\.\d+)?)/\+(\d+(?:\.\d+)?)'), "asymmetric_minus_plus"),
    # Range notation: (100-102)
    (re.compile(r'\((\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\)'), "range"),
]

# Standard dimension names mapping
_DIMENSION_NAME_MAPPING = {
    # Length variants
    "overall length": "Overall Length",
    "loa": "Length Overall",
    "length overall": "Length Overall",
    "lbp": "Length Between Perpendiculars",
    "length between perpendiculars": "Length Between Perpendiculars",
    "length": "Length",
    
    # Beam/Breadth variants
    "beam": "Beam",
    "moulded breadth": "Moulded Breadth",
    "molded breadth": "Moulded Breadth",
    "breadth": "Breadth",
    "width": "Beam",
    
    # Depth/Draft variants
    "depth": "Depth",
    "moulded depth": "Moulded Depth",
    "molded depth": "Moulded Depth",
    "draft": "Draft",
    "draught": "Draft",
    "mean draft": "Mean Draft",
    "light draft": "Light Draft",
    "loaded draft": "Loaded Draft",
    
    # Other common dimensions
    "height": "Height",
    "diameter": "Diameter",
    "radius": "Radius",
    "thickness": "Thickness",
    "clearance": "Clearance",
    "spacing": "Spacing",
}


# ═══════════════════════════════════════════════════════════════
#  VESSEL CLASS NORM RANGES (for validation)
# ═══════════════════════════════════════════════════════════════

_VESSEL_CLASS_NORMS = {
    # OPV (Offshore Patrol Vessel) class
    "OPV": {
        "length": (80.0, 110.0),      # meters
        "beam": (10.0, 16.0),
        "depth": (5.0, 8.0),
        "draft": (3.0, 5.0),
    },
    # Frigate class
    "frigate": {
        "length": (100.0, 150.0),
        "beam": (12.0, 18.0),
        "depth": (6.0, 10.0),
        "draft": (4.0, 7.0),
    },
    # Corvette class
    "corvette": {
        "length": (60.0, 100.0),
        "beam": (8.0, 14.0),
        "depth": (4.0, 7.0),
        "draft": (2.5, 4.5),
    },
    # General ranges for unknown class
    "general": {
        "length": (5.0, 400.0),
        "beam": (2.0, 60.0),
        "depth": (1.0, 30.0),
        "draft": (0.5, 20.0),
    },
}


# ═══════════════════════════════════════════════════════════════
#  UNIT CONVERSION UTILITIES
# ═══════════════════════════════════════════════════════════════

def parse_unit(unit_str: str) -> MeasurementUnit:
    """Parse unit string to MeasurementUnit enum."""
    unit_lower = unit_str.lower().strip()
    
    if unit_lower in ("mm", "millimeter", "millimetre", "millimeters", "millimetres"):
        return MeasurementUnit.MILLIMETER
    elif unit_lower in ("cm", "centimeter", "centimetre", "centimeters", "centimetres"):
        return MeasurementUnit.CENTIMETER
    elif unit_lower in ("m", "meter", "metre", "meters", "metres"):
        return MeasurementUnit.METER
    elif unit_lower in ("in", "inch", "inches", '"', "″"):
        return MeasurementUnit.INCH
    elif unit_lower in ("ft", "foot", "feet", "'", "′"):
        return MeasurementUnit.FOOT
    else:
        return MeasurementUnit.METER  # Default


def convert_to_meters(value: float, unit: MeasurementUnit) -> float:
    """Convert any unit to meters."""
    conversions = {
        MeasurementUnit.MILLIMETER: 0.001,
        MeasurementUnit.CENTIMETER: 0.01,
        MeasurementUnit.METER: 1.0,
        MeasurementUnit.INCH: 0.0254,
        MeasurementUnit.FOOT: 0.3048,
        MeasurementUnit.FOOT_INCH: 0.3048,  # Handled separately
    }
    return value * conversions.get(unit, 1.0)


def convert_imperial_ft_in(feet: int, inches: float = 0) -> float:
    """Convert feet and inches to meters."""
    total_feet = feet + (inches / 12.0)
    return total_feet * 0.3048


def normalize_unit(unit: MeasurementUnit) -> str:
    """Get standard abbreviation."""
    mapping = {
        MeasurementUnit.MILLIMETER: "mm",
        MeasurementUnit.CENTIMETER: "cm",
        MeasurementUnit.METER: "m",
        MeasurementUnit.INCH: "in",
        MeasurementUnit.FOOT: "ft",
        MeasurementUnit.FOOT_INCH: "ft",
    }
    return mapping.get(unit, "m")


# ═══════════════════════════════════════════════════════════════
#  TOLERANCE PARSING
# ═══════════════════════════════════════════════════════════════

def parse_tolerance(text: str, nominal_value: float, unit: MeasurementUnit) -> Optional[ToleranceSpec]:
    """
    Extract tolerance specification from text.
    
    Args:
        text: Raw text containing dimension
        nominal_value: The main dimension value
        unit: Unit of measurement
        
    Returns:
        ToleranceSpec or None if no tolerance found
    """
    for pattern, tol_type in _TOLERANCE_PATTERNS:
        match = pattern.search(text)
        if match:
            if tol_type == "symmetric":
                tol = float(match.group(1))
                return ToleranceSpec(
                    nominal_value=nominal_value,
                    symmetric_tolerance=tol,
                    unit=unit
                )
            elif tol_type == "asymmetric_plus_minus":
                plus = float(match.group(1))
                minus = float(match.group(2))
                return ToleranceSpec(
                    nominal_value=nominal_value,
                    plus_tolerance=plus,
                    minus_tolerance=minus,
                    unit=unit
                )
            elif tol_type == "asymmetric_minus_plus":
                minus = float(match.group(1))
                plus = float(match.group(2))
                return ToleranceSpec(
                    nominal_value=nominal_value,
                    plus_tolerance=plus,
                    minus_tolerance=minus,
                    unit=unit
                )
            elif tol_type == "range":
                min_val = float(match.group(1))
                max_val = float(match.group(2))
                # Convert to asymmetric tolerance around nominal
                if nominal_value:
                    plus = max_val - nominal_value
                    minus = nominal_value - min_val
                    return ToleranceSpec(
                        nominal_value=nominal_value,
                        plus_tolerance=plus if plus > 0 else None,
                        minus_tolerance=minus if minus > 0 else None,
                        unit=unit
                    )
    return None


def format_tolerance(tol: Optional[ToleranceSpec]) -> str:
    """Format tolerance for display."""
    if not tol:
        return ""
    
    if tol.symmetric_tolerance:
        return f"±{tol.symmetric_tolerance}"
    elif tol.plus_tolerance and tol.minus_tolerance:
        if tol.plus_tolerance == tol.minus_tolerance:
            return f"±{tol.plus_tolerance}"
        return f"+{tol.plus_tolerance}/-{tol.minus_tolerance}"
    elif tol.plus_tolerance:
        return f"+{tol.plus_tolerance}"
    elif tol.minus_tolerance:
        return f"-{tol.minus_tolerance}"
    return ""


# ═══════════════════════════════════════════════════════════════
#  MAIN EXTRACTION FUNCTIONS
# ═══════════════════════════════════════════════════════════════

def extract_dimensions(text: str, confidence_threshold: float = 0.6) -> List[Dimension]:
    """
    Extract all dimensions from text.
    
    Args:
        text: OCR or VLM extracted text
        confidence_threshold: Minimum confidence to include
        
    Returns:
        List of Dimension objects
    """
    dimensions = []
    found_positions = set()  # Track to avoid duplicates
    
    for pattern, pattern_type in _DIMENSION_PATTERNS:
        for match in pattern.finditer(text):
            # Skip overlapping matches
            pos_key = (match.start(), match.end())
            if pos_key in found_positions:
                continue
            found_positions.add(pos_key)
            
            try:
                dim = _parse_dimension_match(match, pattern_type, text)
                if dim and dim.confidence >= confidence_threshold:
                    dimensions.append(dim)
            except Exception as e:
                logger.debug(f"Failed to parse dimension match: {e}")
                continue
    
    # Sort by confidence descending
    dimensions.sort(key=lambda d: d.confidence, reverse=True)
    return dimensions


def _parse_dimension_match(match: re.Match, pattern_type: str, full_text: str) -> Optional[Dimension]:
    """Parse a single regex match into a Dimension."""
    
    if pattern_type == "metric_with_name":
        name_raw = match.group(1)
        value = float(match.group(2))
        unit_str = match.group(3)
        
        name = _DIMENSION_NAME_MAPPING.get(name_raw.lower(), name_raw.title())
        unit = parse_unit(unit_str)
        raw_text = match.group(0)
        
        # Check for tolerance in surrounding text
        tol = parse_tolerance(full_text[match.start():match.end()+20], value, unit)
        
        return Dimension(
            name=name,
            value=value,
            unit=unit,
            tolerance=format_tolerance(tol),
            raw_text=raw_text,
            location="detected",
            confidence=_calculate_confidence(pattern_type, True, name_raw)
        )
    
    elif pattern_type == "with_tolerance":
        value = float(match.group(1))
        unit_str = match.group(3) if len(match.groups()) >= 3 else "m"
        unit = parse_unit(unit_str)
        raw_text = match.group(0)
        
        tol = parse_tolerance(raw_text, value, unit)
        
        # Try to find a name before this dimension
        name = _find_dimension_name_before(full_text, match.start())
        
        return Dimension(
            name=name or "Dimension",
            value=value,
            unit=unit,
            tolerance=format_tolerance(tol),
            raw_text=raw_text,
            location="detected",
            confidence=_calculate_confidence(pattern_type, bool(name), None)
        )
    
    elif pattern_type == "imperial_ft_in":
        feet = int(match.group(1))
        inches = float(match.group(2)) if match.group(2) else 0
        
        value = convert_imperial_ft_in(feet, inches)
        unit = MeasurementUnit.METER
        raw_text = match.group(0)
        
        name = _find_dimension_name_before(full_text, match.start())
        
        return Dimension(
            name=name or "Dimension",
            value=round(value, 3),
            unit=unit,
            raw_text=raw_text,
            location="detected",
            confidence=0.75  # Imperial conversions are less certain
        )
    
    elif pattern_type == "standalone":
        value = float(match.group(1))
        unit_str = match.group(2)
        unit = parse_unit(unit_str)
        raw_text = match.group(0)
        
        # Look for name before
        name = _find_dimension_name_before(full_text, match.start())
        
        return Dimension(
            name=name or "Dimension",
            value=value,
            unit=unit,
            raw_text=raw_text,
            location="detected",
            confidence=_calculate_confidence(pattern_type, bool(name), None)
        )
    
    return None


def _find_dimension_name_before(text: str, position: int, window: int = 50) -> Optional[str]:
    """Look for a dimension name in text before position."""
    search_text = text[max(0, position-window):position]
    
    for key, mapped_name in _DIMENSION_NAME_MAPPING.items():
        if key in search_text.lower():
            return mapped_name
    
    return None


def _calculate_confidence(pattern_type: str, has_name: bool, name_match: Optional[str]) -> float:
    """Calculate confidence score based on extraction quality."""
    base_confidence = {
        "metric_with_name": 0.95,
        "with_tolerance": 0.85,
        "imperial_ft_in": 0.75,
        "range": 0.80,
        "standalone": 0.70,
    }.get(pattern_type, 0.60)
    
    # Boost for having a name
    if has_name:
        base_confidence = min(base_confidence + 0.05, 0.98)
    else:
        base_confidence -= 0.10
    
    # Known dimension name is better
    if name_match and name_match.lower() in _DIMENSION_NAME_MAPPING:
        base_confidence = min(base_confidence + 0.03, 0.98)
    
    return round(base_confidence, 2)


# ═══════════════════════════════════════════════════════════════
#  VALIDATION FUNCTIONS
# ═══════════════════════════════════════════════════════════════

def validate_dimensions(
    dimensions: List[Dimension],
    vessel_class: str = "general"
) -> Tuple[List[Dimension], List[Dict]]:
    """
    Validate dimensions against vessel class norms.
    
    Returns:
        (valid_dimensions, validation_issues)
    """
    norms = _VESSEL_CLASS_NORMS.get(vessel_class, _VESSEL_CLASS_NORMS["general"])
    valid = []
    issues = []
    
    # Find key dimensions
    length_dim = None
    beam_dim = None
    depth_dim = None
    
    for dim in dimensions:
        name_lower = dim.name.lower()
        
        if any(x in name_lower for x in ["length", "loa", "lbp"]):
            length_dim = dim
        elif any(x in name_lower for x in ["beam", "breadth", "width"]):
            beam_dim = dim
        elif any(x in name_lower for x in ["depth", "moulded depth", "molded depth"]):
            depth_dim = dim
        
        # Check against norms
        for norm_key, (min_val, max_val) in norms.items():
            if norm_key in name_lower:
                meters_value = convert_to_meters(dim.value, dim.unit)
                if meters_value < min_val or meters_value > max_val:
                    issues.append({
                        "dimension": dim.name,
                        "value": f"{dim.value} {normalize_unit(dim.unit)}",
                        "issue": f"Outside typical {vessel_class} range ({min_val}-{max_val} m)",
                        "severity": "warning" if meters_value > max_val * 1.5 or meters_value < min_val * 0.5 else "info"
                    })
        
        valid.append(dim)
    
    # Cross-dimension validation: L > B > D
    if length_dim and beam_dim:
        l_m = convert_to_meters(length_dim.value, length_dim.unit)
        b_m = convert_to_meters(beam_dim.value, beam_dim.unit)
        
        if l_m <= b_m:
            issues.append({
                "dimension": "Length vs Beam",
                "value": f"L={length_dim.value} ≤ B={beam_dim.value}",
                "issue": "Length should be greater than Beam",
                "severity": "error"
            })
    
    if beam_dim and depth_dim:
        b_m = convert_to_meters(beam_dim.value, beam_dim.unit)
        d_m = convert_to_meters(depth_dim.value, depth_dim.unit)
        
        if b_m <= d_m:
            issues.append({
                "dimension": "Beam vs Depth",
                "value": f"B={beam_dim.value} ≤ D={depth_dim.value}",
                "issue": "Beam should typically be greater than Moulded Depth",
                "severity": "warning"
            })
    
    return valid, issues


def calculate_derived_dimensions(dimensions: List[Dimension]) -> List[Dimension]:
    """
    Calculate derived dimensions if possible.
    
    Example: If we have L and B, estimate block coefficient area
    """
    derived = []
    
    # Find L and B
    length_m = None
    beam_m = None
    
    for dim in dimensions:
        name_lower = dim.name.lower()
        if any(x in name_lower for x in ["length", "loa"]):
            length_m = convert_to_meters(dim.value, dim.unit)
        elif any(x in name_lower for x in ["beam", "breadth"]):
            beam_m = convert_to_meters(dim.value, dim.unit)
    
    # Calculate L/B ratio if both available
    if length_m and beam_m and beam_m > 0:
        lb_ratio = length_m / beam_m
        derived.append(Dimension(
            name="Length/Beam Ratio",
            value=round(lb_ratio, 2),
            unit=MeasurementUnit.METER,  # Dimensionless but use meter as placeholder
            raw_text=f"Derived: {round(lb_ratio, 2)}",
            location="calculated",
            confidence=0.70  # Derived values have lower confidence
        ))
    
    return derived


# ═══════════════════════════════════════════════════════════════
#  MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════

def parse_measurements(
    text: str,
    vessel_class: str = "general",
    confidence_threshold: float = 0.6
) -> Dict[str, Any]:
    """
    Main entry point for measurement parsing.
    
    Args:
        text: OCR/VLM extracted text
        vessel_class: Vessel class for validation norms
        confidence_threshold: Minimum confidence to include
        
    Returns:
        {
            "dimensions": List[Dimension],
            "derived": List[Dimension],
            "validation_issues": List[Dict],
            "stats": {
                "total_found": int,
                "high_confidence": int,
                "with_tolerance": int,
            }
        }
    """
    # Extract dimensions
    dimensions = extract_dimensions(text, confidence_threshold)
    
    # Calculate derived values
    derived = calculate_derived_dimensions(dimensions)
    
    # Validate
    valid_dims, issues = validate_dimensions(dimensions, vessel_class)
    
    # Stats
    high_conf = sum(1 for d in valid_dims if d.confidence >= 0.85)
    with_tol = sum(1 for d in valid_dims if d.tolerance)
    
    return {
        "dimensions": valid_dims,
        "derived": derived,
        "validation_issues": issues,
        "stats": {
            "total_found": len(valid_dims),
            "high_confidence": high_conf,
            "with_tolerance": with_tol,
        }
    }


# ═══════════════════════════════════════════════════════════════
#  TESTING
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Test cases
    test_texts = [
        "Overall Length 105.5 m ±0.2",
        "Beam 14.2 m",
        "Moulded Depth 8.5 m",
        "LOA = 102.3 meters",
        "Draft 4.2 m (light)",
        "42'6\" overall length",
        "Hull thickness 12 mm",
        "Diameter 500 mm ±5",
    ]
    
    print("Measurement Parser Tests")
    print("=" * 60)
    
    for text in test_texts:
        result = parse_measurements(text)
        print(f"\nInput: {text}")
        for dim in result["dimensions"]:
            print(f"  → {dim.name}: {dim.value} {normalize_unit(dim.unit)} (conf: {dim.confidence})")

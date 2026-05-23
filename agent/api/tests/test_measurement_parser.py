"""
AGRA Phase 4 Tests — Measurement Parser
Verify dimension extraction and validation.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from api.models.drawing_models import MeasurementUnit, Dimension
from api.rag.measurement_parser import (
    parse_unit,
    convert_to_meters,
    convert_imperial_ft_in,
    normalize_unit,
    parse_tolerance,
    format_tolerance,
    extract_dimensions,
    validate_dimensions,
    calculate_derived_dimensions,
    parse_measurements,
)


def test_parse_unit():
    """Test unit string parsing."""
    assert parse_unit("mm") == MeasurementUnit.MILLIMETER
    assert parse_unit("meters") == MeasurementUnit.METER
    assert parse_unit("cm") == MeasurementUnit.CENTIMETER
    assert parse_unit("inches") == MeasurementUnit.INCH
    assert parse_unit("feet") == MeasurementUnit.FOOT
    print("✓ Unit parsing passed")


def test_convert_to_meters():
    """Test unit conversion to meters."""
    assert convert_to_meters(1000, MeasurementUnit.MILLIMETER) == 1.0
    assert convert_to_meters(100, MeasurementUnit.CENTIMETER) == 1.0
    assert convert_to_meters(1, MeasurementUnit.METER) == 1.0
    assert convert_to_meters(1, MeasurementUnit.FOOT) == 0.3048
    assert abs(convert_to_meters(1, MeasurementUnit.INCH) - 0.0254) < 0.0001
    print("✓ Unit conversion passed")


def test_imperial_conversion():
    """Test feet/inches to meters conversion."""
    # 1 foot = 0.3048 meters
    assert abs(convert_imperial_ft_in(1, 0) - 0.3048) < 0.0001
    # 42'6" = 42.5 feet = 12.954 meters
    result = convert_imperial_ft_in(42, 6)
    expected = 42.5 * 0.3048
    assert abs(result - expected) < 0.001
    print("✓ Imperial conversion passed")


def test_extract_length_with_name():
    """Test extracting length with dimension name."""
    text = "Overall Length 105.5 m ±0.2"
    dims = extract_dimensions(text)
    assert len(dims) == 1
    assert dims[0].name == "Overall Length"
    assert dims[0].value == 105.5
    assert dims[0].unit == MeasurementUnit.METER
    assert dims[0].confidence >= 0.90
    print("✓ Length with name extraction passed")


def test_extract_beam():
    """Test beam extraction."""
    text = "Beam 14.2 m"
    dims = extract_dimensions(text)
    assert len(dims) == 1
    assert "Beam" in dims[0].name
    assert dims[0].value == 14.2
    print("✓ Beam extraction passed")


def test_extract_loa():
    """Test LOA extraction."""
    text = "LOA = 102.3 meters"
    dims = extract_dimensions(text)
    assert len(dims) == 1
    assert dims[0].value == 102.3
    print("✓ LOA extraction passed")


def test_extract_mm_thickness():
    """Test millimeter dimension extraction."""
    text = "Hull thickness 12 mm"
    dims = extract_dimensions(text)
    assert len(dims) == 1
    assert dims[0].value == 12
    assert dims[0].unit == MeasurementUnit.MILLIMETER
    print("✓ Millimeter extraction passed")


def test_extract_with_tolerance():
    """Test dimension with tolerance."""
    text = "Diameter 500 mm ±5"
    dims = extract_dimensions(text)
    assert len(dims) >= 1
    dim = dims[0]
    assert dim.value == 500
    assert dim.tolerance is not None
    print("✓ Tolerance extraction passed")


def test_imperial_extraction():
    """Test imperial dimension extraction."""
    text = "42'6\" overall length"
    dims = extract_dimensions(text)
    assert len(dims) >= 1
    # Should convert to meters
    assert dims[0].unit == MeasurementUnit.METER
    # 42'6" = 12.954 m
    assert dims[0].value > 12.0 and dims[0].value < 13.0
    print("✓ Imperial extraction passed")


def test_validate_opv_dimensions():
    """Test validation against OPV norms."""
    dims = [
        Dimension(name="Overall Length", value=105.0, unit=MeasurementUnit.METER, raw_text="105 m", location="test", confidence=0.95),
        Dimension(name="Beam", value=14.0, unit=MeasurementUnit.METER, raw_text="14 m", location="test", confidence=0.95),
        Dimension(name="Depth", value=7.5, unit=MeasurementUnit.METER, raw_text="7.5 m", location="test", confidence=0.95),
    ]
    valid, issues = validate_dimensions(dims, "OPV")
    assert len(valid) == 3
    # All should pass OPV norms
    assert len(issues) == 0
    print("✓ OPV validation passed")


def test_validate_outlier():
    """Test outlier detection."""
    # 500m length is way too big for OPV
    dims = [
        Dimension(name="Overall Length", value=500.0, unit=MeasurementUnit.METER, raw_text="500 m", location="test", confidence=0.95),
    ]
    valid, issues = validate_dimensions(dims, "OPV")
    assert len(issues) >= 1
    assert any("outside typical" in issue.get("issue", "") for issue in issues)
    print("✓ Outlier detection passed")


def test_cross_dimension_validation():
    """Test L > B validation."""
    # Invalid: Length <= Beam
    dims = [
        Dimension(name="Overall Length", value=50.0, unit=MeasurementUnit.METER, raw_text="50 m", location="test", confidence=0.95),
        Dimension(name="Beam", value=60.0, unit=MeasurementUnit.METER, raw_text="60 m", location="test", confidence=0.95),
    ]
    valid, issues = validate_dimensions(dims)
    assert any("Length should be greater than Beam" in issue.get("issue", "") for issue in issues)
    print("✓ Cross-dimension validation passed")


def test_calculate_lb_ratio():
    """Test L/B ratio calculation."""
    dims = [
        Dimension(name="Overall Length", value=100.0, unit=MeasurementUnit.METER, raw_text="100 m", location="test", confidence=0.95),
        Dimension(name="Beam", value=20.0, unit=MeasurementUnit.METER, raw_text="20 m", location="test", confidence=0.95),
    ]
    derived = calculate_derived_dimensions(dims)
    assert len(derived) == 1
    assert derived[0].name == "Length/Beam Ratio"
    assert derived[0].value == 5.0  # 100/20
    assert derived[0].confidence < 0.80  # Derived has lower confidence
    print("✓ L/B ratio calculation passed")


def test_parse_measurements_integration():
    """Test full parse_measurements function."""
    text = "Overall Length 105.5 m. Beam 14.2 m. Moulded Depth 8.5 m."
    result = parse_measurements(text, vessel_class="OPV")
    
    assert result["stats"]["total_found"] == 3
    assert len(result["dimensions"]) == 3
    assert len(result["validation_issues"]) == 0  # Normal OPV dimensions
    
    print("✓ Full integration test passed")


def run_all_tests():
    """Run all measurement parser tests."""
    print("=" * 60)
    print("Measurement Parser Tests")
    print("=" * 60)
    
    tests = [
        test_parse_unit,
        test_convert_to_meters,
        test_imperial_conversion,
        test_extract_length_with_name,
        test_extract_beam,
        test_extract_loa,
        test_extract_mm_thickness,
        test_extract_with_tolerance,
        test_imperial_extraction,
        test_validate_opv_dimensions,
        test_validate_outlier,
        test_cross_dimension_validation,
        test_calculate_lb_ratio,
        test_parse_measurements_integration,
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

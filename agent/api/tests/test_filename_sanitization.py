"""
Module 7 Phase 6 — Filename Sanitization Tests
Verify that filenames are properly sanitized for downloads.
"""

import sys
import os
import re
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


def sanitize_filename(filename: str) -> str:
    """Sanitize filename for output (matches logic in generate.py)."""
    return re.sub(r'[^\w\s-]', '', Path(filename).stem)[:30].replace(' ', '_') or "document"


def test_basic_filename():
    """Test basic filename sanitization."""
    result = sanitize_filename("Fire Safety.pdf")
    assert result == "Fire_Safety", f"Expected 'Fire_Safety', got '{result}'"


def test_filename_with_numbers():
    """Test filename with version numbers."""
    result = sanitize_filename("SOLAS_Chapter_II_v2.pdf")
    assert result == "SOLAS_Chapter_II_v2", f"Expected 'SOLAS_Chapter_II_v2', got '{result}'"


def test_filename_special_chars():
    """Test filename with special characters."""
    result = sanitize_filename("ICG's Plan (2024).pdf")
    assert result == "ICGs_Plan_2024", f"Expected 'ICGs_Plan_2024', got '{result}'"


def test_long_filename():
    """Test long filename truncation."""
    long_name = "A" * 50 + ".pdf"
    result = sanitize_filename(long_name)
    assert len(result) <= 30, f"Expected <=30 chars, got {len(result)}"
    assert result == "A" * 30, f"Expected 'A'*30, got '{result}'"


def test_empty_filename():
    """Test empty filename fallback."""
    result = sanitize_filename(".pdf")
    assert result == "document", f"Expected 'document', got '{result}'"


def test_filename_with_spaces():
    """Test filename with spaces."""
    result = sanitize_filename("Ship Navigation Standards.pdf")
    assert result == "Ship_Navigation_Standards", f"Expected 'Ship_Navigation_Standards', got '{result}'"


def test_unicode_filename():
    """Test unicode filename preservation."""
    result = sanitize_filename("मेरा_दस्तावेज़.pdf")
    assert "मेरा" in result or "दस" in result, f"Expected unicode preserved, got '{result}'"


def test_filename_patterns():
    """Test various filename patterns."""
    test_cases = [
        ("doc123.pdf", "doc123"),
        ("Equipment-Specs_v1.2.pdf", "Equipment-Specs_v12"),
        ("Fire_Pump_Manual.pdf", "Fire_Pump_Manual"),
        ("SOTR_Gravity_Davit.pdf", "SOTR_Gravity_Davit"),
    ]
    
    for input_name, expected in test_cases:
        result = sanitize_filename(input_name)
        assert result == expected, f"For '{input_name}': expected '{expected}', got '{result}'"


if __name__ == "__main__":
    print("Running Filename Sanitization Tests...")
    
    tests = [
        test_basic_filename,
        test_filename_with_numbers,
        test_filename_special_chars,
        test_long_filename,
        test_empty_filename,
        test_filename_with_spaces,
        test_unicode_filename,
        test_filename_patterns,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            print(f"  ✓ {test.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  ✗ {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ✗ {test.__name__}: Unexpected error: {e}")
            failed += 1
    
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)

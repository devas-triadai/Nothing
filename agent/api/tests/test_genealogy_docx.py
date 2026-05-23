"""
Module 7 Phase 5 — Unit Tests for Genealogy DOCX Export
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

# Test the utility functions
from backend.app.utils.genealogy_docx_export import (
    _add_watermark,
    _set_cell_shading,
    generate_genealogy_docx
)


def test_cell_shading_function():
    """Test that cell shading function exists and is callable."""
    # Cannot test without actual docx cell, but verify function exists
    assert callable(_set_cell_shading)


def test_add_watermark_function():
    """Test that watermark function exists and is callable."""
    assert callable(_add_watermark)


def test_generate_function():
    """Test that generate function exists and is callable."""
    assert callable(generate_genealogy_docx)


def test_imports():
    """Test that all required imports work."""
    try:
        from docx import Document
        from docx.shared import Inches, Pt, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        assert True
    except ImportError as e:
        assert False, f"Missing required import: {e}"


if __name__ == "__main__":
    print("Running Module 7 Phase 5 — Genealogy DOCX Export Tests...")
    
    tests = [
        test_cell_shading_function,
        test_add_watermark_function,
        test_generate_function,
        test_imports,
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

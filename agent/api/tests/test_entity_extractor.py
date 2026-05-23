"""
Module 7 Phase 4 — Unit Tests for Entity Extraction
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from api.rag.entity_extractor import (
    normalize_entity_name,
    _quick_text_similarity,
    _map_entity_type,
    extract_regulations_rule_based,
    extract_equipment_rule_based,
    ENTITY_TYPES
)


def test_normalize_entity_name_lowercase():
    """Test normalization lowercases text."""
    result = normalize_entity_name("Fire Pump")
    assert result == "fire pump", f"Expected 'fire pump', got '{result}'"


def test_normalize_entity_name_whitespace():
    """Test whitespace normalization."""
    result = normalize_entity_name("fire   pump  system")
    assert result == "fire pump", f"Expected 'fire pump', got '{result}'"


def test_normalize_entity_name_special_chars():
    """Test special character removal."""
    result = normalize_entity_name("fire-pump_system!")
    assert "fire" in result and "pump" in result


def test_normalize_entity_name_stopwords():
    """Test stopword removal."""
    result = normalize_entity_name("the fire pump system")
    assert "the" not in result
    assert "system" not in result
    assert "fire pump" in result


def test_map_entity_type_equipment():
    """Test equipment type mapping."""
    assert _map_entity_type("equipment") == "equipment"
    assert _map_entity_type("device") == "equipment"
    assert _map_entity_type("machinery") == "equipment"


def test_map_entity_type_regulation():
    """Test regulation type mapping."""
    assert _map_entity_type("regulation") == "regulation"
    assert _map_entity_type("rule") == "regulation"
    assert _map_entity_type("code") == "regulation"


def test_map_entity_type_ship():
    """Test ship type mapping."""
    assert _map_entity_type("ship") == "ship_type"
    assert _map_entity_type("vessel") == "ship_type"


def test_map_entity_type_unknown():
    """Test unknown type returns None."""
    assert _map_entity_type("unknown_type") is None
    assert _map_entity_type("xyz123") is None


def test_quick_text_similarity_identical():
    """Test identical text similarity."""
    sim = _quick_text_similarity("fire pump", "fire pump")
    assert sim == 1.0, f"Expected 1.0, got {sim}"


def test_quick_text_similarity_different():
    """Test completely different text."""
    sim = _quick_text_similarity("fire pump", "navigation system")
    assert sim == 0.0, f"Expected 0.0, got {sim}"


def test_quick_text_similarity_partial():
    """Test partial overlap."""
    sim = _quick_text_similarity("fire pump system", "fire suppression pump")
    assert 0 < sim < 1, f"Expected between 0 and 1, got {sim}"


def test_extract_regulations_solas():
    """Test SOLAS regulation extraction."""
    text = "As per SOLAS Chapter II-2, all ships must have fire safety systems."
    regs = extract_regulations_rule_based(text)
    
    assert len(regs) > 0, "Should extract SOLAS regulation"
    assert any("SOLAS" in r["name"] for r in regs)


def test_extract_regulations_iso():
    """Test ISO standard extraction."""
    text = "Equipment must comply with ISO 9001 and IEC 60092 standards."
    regs = extract_regulations_rule_based(text)
    
    iso_regs = [r for r in regs if "ISO" in r["name"]]
    iec_regs = [r for r in regs if "IEC" in r["name"]]
    
    assert len(iso_regs) > 0 or len(iec_regs) > 0, "Should extract ISO/IEC standards"


def test_extract_equipment_keywords():
    """Test equipment keyword extraction."""
    text = "The fire pump and smoke detector must be connected to the EPIRB system."
    equip = extract_equipment_rule_based(text)
    
    names = [e["name"] for e in equip]
    assert "fire pump" in names or "pump" in names
    assert "smoke detector" in names or "detector" in names


def test_entity_types_defined():
    """Test that entity types are defined."""
    assert "equipment" in ENTITY_TYPES
    assert "ship_type" in ENTITY_TYPES
    assert "regulation" in ENTITY_TYPES
    assert "requirement" in ENTITY_TYPES


if __name__ == "__main__":
    print("Running Module 7 Phase 4 — Entity Extractor Tests...")
    
    tests = [
        test_normalize_entity_name_lowercase,
        test_normalize_entity_name_whitespace,
        test_normalize_entity_name_special_chars,
        test_normalize_entity_name_stopwords,
        test_map_entity_type_equipment,
        test_map_entity_type_regulation,
        test_map_entity_type_ship,
        test_map_entity_type_unknown,
        test_quick_text_similarity_identical,
        test_quick_text_similarity_different,
        test_quick_text_similarity_partial,
        test_extract_regulations_solas,
        test_extract_regulations_iso,
        test_extract_equipment_keywords,
        test_entity_types_defined,
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

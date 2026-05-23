"""
AGRA Compliance Module Phase 2 Tests — SOTR Parser
Verify clause extraction and SOTR detection.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from api.models.compliance_models import ClauseCategory, ComplianceClauseBase
from api.rag.sotr_parser import (
    is_sotr_document,
    detect_sotr_in_text,
    extract_clauses,
    parse_sotr_document,
    parsed_clause_to_base_model,
    extract_clauses_to_models,
    ParsedClause,
)


# Sample SOTR text for testing
SAMPLE_SOTR_TEXT = """
STATEMENT OF TECHNICAL REQUIREMENTS
OFFSHORE PATROL VESSEL (OPV)

1. GENERAL REQUIREMENTS

1.1 Scope of Supply
The Vendor shall supply and deliver one (1) Offshore Patrol Vessel (OPV) 
as per the specifications herein. The vessel shall comply with IRS Rules 
and Regulations for the class notation +A1, +LMC, +UMS.

1.2 General Description
The vessel shall be of steel construction with the following 
main dimensions:
- Overall Length: approximately 105 meters
- Beam: approximately 14 meters
- Design Draft: approximately 4.5 meters

2. HULL AND STRUCTURE

2.1 Hull Construction
The hull shall be constructed of steel to IRS Grade A and AH36 
steel plates. All welding shall be in accordance with IRS welding 
regulations and ISO 5817 quality level B.
Acceptance criteria: IRS Class approval certificate for hull.

2.2 Structural Strength
The vessel structure shall be designed and built to withstand 
all loads during specified operating conditions including 
seastate 6 conditions.

3. MACHINERY AND PROPULSION

3.1 Main Engines
The vessel shall be fitted with two (2) diesel engines with 
a combined output of not less than 8000 kW. The engines shall 
be IMO Tier III compliant and meet MARPOL Annex VI regulations.

3.2 Propulsion System
The propulsion system may be either CPP or FPP type at the 
Vendor's discretion. The system shall provide a minimum 
speed of 22 knots in calm water conditions.

4. SAFETY SYSTEMS

4.1 Fire Detection and Fighting
The vessel shall be fitted with a comprehensive fire detection 
system covering all compartments. The system shall be addressable 
and comply with SOLAS Chapter II-2 requirements.

4.2 Lifesaving Appliances
Lifesaving appliances shall be provided as per SOLAS Chapter III 
for a complement of 100 persons plus 10% spare capacity.
Acceptance criteria: Liferaft and lifeboat capacity calculations 
approved by IRS.

5. COMMERCIAL TERMS

5.1 Delivery Schedule
The vessel shall be delivered within 24 months from contract 
effective date. Delivery shall be at Vendor's shipyard, free 
of all liens and encumbrances.

5.2 Warranty
The Vendor shall provide a warranty period of 12 months from 
delivery date covering all defects in material and workmanship.
Payment terms: 30% advance, 40% on launching, 30% on delivery.
"""


def test_is_sotr_document_true():
    """Test SOTR detection with SOTR filename."""
    is_sotr, confidence = is_sotr_document(
        "SOTR_OPV_Construction.pdf",
        SAMPLE_SOTR_TEXT[:500]
    )
    
    assert is_sotr == True
    assert confidence >= 0.50
    print("✓ SOTR detection (true) passed")


def test_is_sotr_document_false():
    """Test SOTR detection with non-SOTR filename."""
    is_sotr, confidence = is_sotr_document(
        "random_report.pdf",
        "This is just a regular report about something."
    )
    
    assert is_sotr == False
    assert confidence < 0.50
    print("✓ SOTR detection (false) passed")


def test_detect_sotr_in_text():
    """Test SOTR text analysis."""
    result = detect_sotr_in_text(SAMPLE_SOTR_TEXT[:2000])
    
    assert result["is_likely_sotr"] == True
    assert result["confidence"] > 0.0
    assert len(result["indicators_found"]) > 0
    assert result["clause_count"] > 0
    print("✓ SOTR text analysis passed")


def test_extract_clauses_count():
    """Test extraction of correct number of clauses."""
    clauses = extract_clauses(SAMPLE_SOTR_TEXT)
    
    # Should find clauses: 1.1, 1.2, 2.1, 2.2, 3.1, 3.2, 4.1, 4.2, 5.1, 5.2
    assert len(clauses) >= 10
    print(f"✓ Clause extraction count ({len(clauses)} clauses) passed")


def test_extract_clause_number():
    """Test clause number extraction."""
    clauses = extract_clauses(SAMPLE_SOTR_TEXT)
    
    # Check first few clause numbers
    numbers = [c.clause_number for c in clauses[:5]]
    assert "1.1" in numbers or "1." in numbers[0]
    assert any("2." in n for n in numbers)
    print("✓ Clause number extraction passed")


def test_extract_clause_title():
    """Test clause title extraction."""
    clauses = extract_clauses(SAMPLE_SOTR_TEXT)
    
    # Should extract titles like "Scope of Supply", "Hull Construction"
    titles = [c.clause_title for c in clauses if c.clause_title]
    assert len(titles) > 0
    
    # Check for expected titles
    title_text = " ".join(titles).lower()
    assert any(word in title_text for word in ["scope", "hull", "machinery", "safety"])
    print("✓ Clause title extraction passed")


def test_detect_category_technical():
    """Test technical category detection."""
    text = "The hull shall be constructed of steel plates. Welding per IRS rules."
    
    from api.rag.sotr_parser import _detect_category
    category = _detect_category(text, "Hull Construction")
    
    assert category == ClauseCategory.TECHNICAL
    print("✓ Technical category detection passed")


def test_detect_category_commercial():
    """Test commercial category detection."""
    text = "Payment terms: 30% advance. Delivery within 24 months."
    
    from api.rag.sotr_parser import _detect_category
    category = _detect_category(text, "Delivery Schedule")
    
    assert category == ClauseCategory.COMMERCIAL
    print("✓ Commercial category detection passed")


def test_detect_category_safety():
    """Test safety category detection."""
    text = "Fire detection system shall cover all compartments. SOLAS compliance required."
    
    from api.rag.sotr_parser import _detect_category
    category = _detect_category(text, "Fire Fighting")
    
    assert category == ClauseCategory.SAFETY
    print("✓ Safety category detection passed")


def test_detect_mandatory():
    """Test mandatory language detection."""
    from api.rag.sotr_parser import _detect_mandatory
    
    # Mandatory
    assert _detect_mandatory("The Vendor shall supply...") == True
    assert _detect_mandatory("Must comply with...") == True
    
    # Optional
    assert _detect_mandatory("The Vendor may provide...") == False
    
    # Default (no keywords)
    assert _detect_mandatory("The vessel is blue.") == True  # Default to mandatory
    print("✓ Mandatory detection passed")


def test_detect_critical():
    """Test critical clause detection."""
    from api.rag.sotr_parser import _detect_critical
    
    # Safety is always critical
    assert _detect_critical("Fire system required.", ClauseCategory.SAFETY) == True
    
    # Critical keywords
    assert _detect_critical("Hull integrity is vital.", ClauseCategory.TECHNICAL) == True
    
    # Non-critical
    assert _detect_critical("Paint color may be selected.", ClauseCategory.GENERAL) == False
    print("✓ Critical detection passed")


def test_extract_acceptance_criteria():
    """Test acceptance criteria extraction."""
    from api.rag.sotr_parser import _extract_acceptance_criteria
    
    text1 = "Acceptance criteria: IRS Class approval certificate."
    assert "IRS Class" in (_extract_acceptance_criteria(text1) or "")
    
    text2 = "Shall comply with SOLAS requirements."
    assert "SOLAS" in (_extract_acceptance_criteria(text2) or "")
    
    text3 = "No criteria mentioned here."
    assert _extract_acceptance_criteria(text3) is None
    print("✓ Acceptance criteria extraction passed")


def test_clause_number_sort_key():
    """Test clause number sorting."""
    from api.rag.sotr_parser import _clause_number_sort_key
    
    # Test sorting
    numbers = ["1.2", "1.1", "2.1", "1.10", "1.2.1"]
    sorted_numbers = sorted(numbers, key=_clause_number_sort_key)
    
    assert sorted_numbers == ["1.1", "1.2", "1.2.1", "1.10", "2.1"]
    print("✓ Clause number sorting passed")


def test_parsed_clause_to_base_model():
    """Test conversion to Pydantic model."""
    parsed = ParsedClause(
        clause_number="1.1",
        clause_title="Test Clause",
        clause_text="Test content.",
        category=ClauseCategory.TECHNICAL,
        is_mandatory=True,
        is_critical=False,
        acceptance_criteria="Test criteria",
        raw_text="1.1 Test Clause. Test content."
    )
    
    model = parsed_clause_to_base_model(parsed, sotr_doc_id=123)
    
    assert isinstance(model, ComplianceClauseBase)
    assert model.clause_number == "1.1"
    assert model.clause_title == "Test Clause"
    assert model.category == ClauseCategory.TECHNICAL
    assert model.is_mandatory == True
    print("✓ Parsed clause to model conversion passed")


def test_parse_sotr_document_full():
    """Test full SOTR document parsing."""
    result = parse_sotr_document(
        SAMPLE_SOTR_TEXT,
        "SOTR_OPV_Test.pdf",
        sotr_doc_id=456
    )
    
    assert result["is_sotr"] == True
    assert result["confidence"] >= 0.50
    assert result["sotr_doc_id"] == 456
    assert result["filename"] == "SOTR_OPV_Test.pdf"
    assert result["total_clauses"] >= 10
    assert len(result["categories"]) > 0
    assert result["mandatory_count"] > 0
    assert len(result["clauses"]) >= 10
    
    # Check clause structure
    first_clause = result["clauses"][0]
    assert isinstance(first_clause, ComplianceClauseBase)
    print("✓ Full SOTR document parsing passed")


def test_extract_clauses_to_models():
    """Test direct extraction to Pydantic models."""
    models = extract_clauses_to_models(SAMPLE_SOTR_TEXT, sotr_doc_id=789)
    
    assert len(models) >= 10
    assert all(isinstance(m, ComplianceClauseBase) for m in models)
    
    # Check sorted order
    numbers = [m.clause_number for m in models[:5]]
    assert numbers == sorted(numbers, key=lambda x: [int(p) for p in x.split('.')])
    print("✓ Extract clauses to models passed")


def test_empty_text_handling():
    """Test handling of empty text."""
    clauses = extract_clauses("")
    assert len(clauses) == 0
    
    result = parse_sotr_document("", "empty.pdf", 0)
    assert result["is_sotr"] == False
    print("✓ Empty text handling passed")


def test_nested_clause_numbers():
    """Test extraction of nested clause numbers (e.g., 1.2.1)."""
    text = """
1.1 First level
1.1.1 Second level
1.1.2 Another second level
1.2 Different first level
"""
    
    clauses = extract_clauses(text)
    numbers = [c.clause_number for c in clauses]
    
    assert "1.1" in numbers
    assert "1.1.1" in numbers
    assert "1.1.2" in numbers
    assert "1.2" in numbers
    print("✓ Nested clause number extraction passed")


def run_all_tests():
    """Run all SOTR parser tests."""
    print("=" * 60)
    print("SOTR Parser Tests (Phase 2)")
    print("=" * 60)
    
    tests = [
        test_is_sotr_document_true,
        test_is_sotr_document_false,
        test_detect_sotr_in_text,
        test_extract_clauses_count,
        test_extract_clause_number,
        test_extract_clause_title,
        test_detect_category_technical,
        test_detect_category_commercial,
        test_detect_category_safety,
        test_detect_mandatory,
        test_detect_critical,
        test_extract_acceptance_criteria,
        test_clause_number_sort_key,
        test_parsed_clause_to_base_model,
        test_parse_sotr_document_full,
        test_extract_clauses_to_models,
        test_empty_text_handling,
        test_nested_clause_numbers,
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

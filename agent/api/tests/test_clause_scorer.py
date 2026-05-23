"""
AGRA Compliance Module Phase 3 Tests — Clause Scoring Engine
Verify LLM-based clause scoring logic.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from api.models.compliance_models import (
    ClauseStatus, ComplianceClauseBase, ClauseScoreBase,
    ClauseCategory
)
from api.rag.clause_scorer import (
    _parse_llm_json,
    score_single_clause,
    ScoringResult,
    calculate_confidence_factors,
    generate_evaluation_summary,
)


# Sample LLM responses for testing
_SAMPLE_COMPLIANT_RESPONSE = """
```json
{
  "status": "compliant",
  "confidence": 0.95,
  "vendor_response_summary": "Vendor confirms full compliance with steel grade requirement",
  "evidence": "We confirm that the hull will be constructed using IRS Grade A steel plates",
  "gaps": null,
  "recommendation": "accept"
}
```
"""

_SAMPLE_PARTIAL_RESPONSE = """
{
  "status": "partial",
  "confidence": 0.70,
  "vendor_response_summary": "Vendor meets most criteria but with conditions",
  "evidence": "We can provide Grade A steel but need to verify availability",
  "gaps": "Final confirmation pending availability check",
  "recommendation": "conditional"
}
"""

_SAMPLE_NON_COMPLIANT_RESPONSE = """
```json
{
  "status": "non_compliant",
  "confidence": 0.85,
  "vendor_response_summary": "Vendor proposes alternative not meeting specifications",
  "evidence": "We propose using Grade B steel instead",
  "gaps": "Grade B does not meet IRS Grade A requirement",
  "recommendation": "reject"
}
```
"""

_SAMPLE_NOT_APPLICABLE_RESPONSE = """
{
  "status": "not_applicable",
  "confidence": 0.90,
  "vendor_response_summary": "This requirement is outside vendor's scope",
  "evidence": "This item will be supplied by owner",
  "gaps": null,
  "recommendation": "accept"
}
"""


def test_parse_llm_json_with_markdown():
    """Test JSON parsing with markdown code blocks."""
    result = _parse_llm_json(_SAMPLE_COMPLIANT_RESPONSE)
    
    assert result is not None
    assert result["status"] == "compliant"
    assert result["confidence"] == 0.95
    assert "vendor_response_summary" in result
    print("✓ JSON parsing with markdown passed")


def test_parse_llm_json_without_markdown():
    """Test JSON parsing without markdown."""
    result = _parse_llm_json(_SAMPLE_PARTIAL_RESPONSE)
    
    assert result is not None
    assert result["status"] == "partial"
    assert result["confidence"] == 0.70
    print("✓ JSON parsing without markdown passed")


def test_parse_llm_json_invalid():
    """Test JSON parsing with invalid input."""
    result = _parse_llm_json("This is not JSON at all")
    
    assert result is None
    print("✓ JSON parsing with invalid input passed")


def test_parse_llm_json_array():
    """Test JSON array parsing."""
    array_response = '[{"status": "compliant"}, {"status": "partial"}]'
    result = _parse_llm_json(array_response)
    
    assert result is not None
    assert isinstance(result, list)
    assert len(result) == 2
    print("✓ JSON array parsing passed")


def test_scoring_result_structure():
    """Test ScoringResult dataclass."""
    result = ScoringResult(
        clause_number="1.1",
        status=ClauseStatus.COMPLIANT,
        confidence=0.95,
        vendor_response_summary="Test summary",
        evidence_text="Test evidence",
        gaps_identified=None,
        recommendation="accept",
        llm_raw_response="raw"
    )
    
    assert result.clause_number == "1.1"
    assert result.status == ClauseStatus.COMPLIANT
    assert result.confidence == 0.95
    assert result.vendor_response_summary == "Test summary"
    print("✓ ScoringResult structure passed")


def test_calculate_confidence_factors_high_evidence():
    """Test confidence calculation with strong evidence."""
    result = ScoringResult(
        clause_number="1.1",
        status=ClauseStatus.COMPLIANT,
        confidence=0.90,
        vendor_response_summary="Complete response with all details",
        evidence_text="A" * 250,  # Long evidence
        gaps_identified="None",
        recommendation="accept",
        llm_raw_response="raw"
    )
    
    clause = ComplianceClauseBase(
        clause_number="1.1",
        clause_title="Test Clause",
        clause_text="Test requirement",
        category=ClauseCategory.TECHNICAL,
        is_mandatory=True,
        is_critical=False,
        acceptance_criteria="Test criteria"
    )
    
    factors = calculate_confidence_factors(result, clause)
    
    assert factors["evidence_strength"] == 0.95  # > 200 chars
    assert factors["completeness"] == 0.95  # All fields present
    assert factors["final_confidence"] > 0.80
    print("✓ Confidence factors (high evidence) passed")


def test_calculate_confidence_factors_low_evidence():
    """Test confidence calculation with weak evidence."""
    result = ScoringResult(
        clause_number="1.1",
        status=ClauseStatus.PARTIAL,
        confidence=0.60,
        vendor_response_summary="Brief response",
        evidence_text="Short",  # < 50 chars
        gaps_identified=None,
        recommendation="review",
        llm_raw_response="raw"
    )
    
    clause = ComplianceClauseBase(
        clause_number="1.1",
        clause_title="Test Clause",
        clause_text="Test requirement",
        category=ClauseCategory.TECHNICAL,
        is_mandatory=True,
        is_critical=False,
        acceptance_criteria="Test criteria"
    )
    
    factors = calculate_confidence_factors(result, clause)
    
    assert factors["evidence_strength"] == 0.30  # < 50 chars
    assert factors["completeness"] == 0.75  # Missing gaps
    assert factors["final_confidence"] < 0.80
    print("✓ Confidence factors (low evidence) passed")


def test_calculate_confidence_factors_direct_reference():
    """Test confidence with direct clause reference."""
    result = ScoringResult(
        clause_number="2.3",
        status=ClauseStatus.COMPLIANT,
        confidence=0.85,
        vendor_response_summary="Response to clause 2.3",
        evidence_text="Regarding clause 2.3, we confirm full compliance",
        gaps_identified=None,
        recommendation="accept",
        llm_raw_response="raw"
    )
    
    clause = ComplianceClauseBase(
        clause_number="2.3",
        clause_title="Specific Requirement",
        clause_text="Test requirement",
        category=ClauseCategory.TECHNICAL,
        is_mandatory=True,
        is_critical=False,
        acceptance_criteria="Test criteria"
    )
    
    factors = calculate_confidence_factors(result, clause)
    
    assert factors["direct_reference"] == 0.95  # Clause number in evidence
    assert factors["final_confidence"] > 0.80
    print("✓ Confidence factors (direct reference) passed")


def test_generate_evaluation_summary_perfect():
    """Test summary generation with perfect compliance."""
    scored_clauses = [
        (ComplianceClauseBase(clause_number="1.1", clause_text="Test", category=ClauseCategory.TECHNICAL),
         ClauseScoreBase(status=ClauseStatus.COMPLIANT, confidence=0.95)),
        (ComplianceClauseBase(clause_number="1.2", clause_text="Test", category=ClauseCategory.TECHNICAL),
         ClauseScoreBase(status=ClauseStatus.COMPLIANT, confidence=0.90)),
        (ComplianceClauseBase(clause_number="1.3", clause_text="Test", category=ClauseCategory.SAFETY),
         ClauseScoreBase(status=ClauseStatus.COMPLIANT, confidence=0.92)),
    ]
    
    summary = generate_evaluation_summary(scored_clauses)
    
    assert summary["total_clauses"] == 3
    assert summary["counts"]["compliant"] == 3
    assert summary["compliance_percentage"] == 100.0
    assert summary["recommendation"] == "accept"
    assert summary["average_confidence"] > 0.90
    print("✓ Evaluation summary (perfect) passed")


def test_generate_evaluation_summary_mixed():
    """Test summary with mixed results."""
    scored_clauses = [
        (ComplianceClauseBase(clause_number="1.1", clause_text="Test", category=ClauseCategory.TECHNICAL),
         ClauseScoreBase(status=ClauseStatus.COMPLIANT, confidence=0.95)),
        (ComplianceClauseBase(clause_number="1.2", clause_text="Test", category=ClauseCategory.TECHNICAL),
         ClauseScoreBase(status=ClauseStatus.PARTIAL, confidence=0.70)),
        (ComplianceClauseBase(clause_number="1.3", clause_text="Test", category=ClauseCategory.COMMERCIAL),
         ClauseScoreBase(status=ClauseStatus.NON_COMPLIANT, confidence=0.80)),
        (ComplianceClauseBase(clause_number="1.4", clause_text="Test", category=ClauseCategory.SAFETY),
         ClauseScoreBase(status=ClauseStatus.COMPLIANT, confidence=0.90)),
    ]
    
    summary = generate_evaluation_summary(scored_clauses)
    
    assert summary["total_clauses"] == 4
    assert summary["counts"]["compliant"] == 2
    assert summary["counts"]["partial"] == 1
    assert summary["counts"]["non_compliant"] == 1
    
    # Compliance % = (2 + 0.5) / 3 * 100 = 83.3%
    assert summary["compliance_percentage"] > 80.0
    
    # 1 non-compliant but more compliant, should be conditional
    assert summary["recommendation"] == "conditional"
    
    # Check category breakdown
    assert "technical" in summary["category_breakdown"]
    assert "commercial" in summary["category_breakdown"]
    assert "safety" in summary["category_breakdown"]
    print("✓ Evaluation summary (mixed) passed")


def test_generate_evaluation_summary_reject():
    """Test summary that should be rejected."""
    scored_clauses = [
        (ComplianceClauseBase(clause_number="1.1", clause_text="Test", category=ClauseCategory.TECHNICAL),
         ClauseScoreBase(status=ClauseStatus.NON_COMPLIANT, confidence=0.85)),
        (ComplianceClauseBase(clause_number="1.2", clause_text="Test", category=ClauseCategory.TECHNICAL),
         ClauseScoreBase(status=ClauseStatus.NON_COMPLIANT, confidence=0.80)),
        (ComplianceClauseBase(clause_number="1.3", clause_text="Test", category=ClauseCategory.COMMERCIAL),
         ClauseScoreBase(status=ClauseStatus.NON_COMPLIANT, confidence=0.75)),
    ]
    
    summary = generate_evaluation_summary(scored_clauses)
    
    assert summary["counts"]["non_compliant"] == 3
    assert summary["compliance_percentage"] == 0.0
    assert summary["recommendation"] == "reject"
    print("✓ Evaluation summary (reject) passed")


def test_generate_evaluation_summary_with_not_applicable():
    """Test summary with not applicable clauses."""
    scored_clauses = [
        (ComplianceClauseBase(clause_number="1.1", clause_text="Test", category=ClauseCategory.TECHNICAL),
         ClauseScoreBase(status=ClauseStatus.COMPLIANT, confidence=0.95)),
        (ComplianceClauseBase(clause_number="1.2", clause_text="Test", category=ClauseCategory.GENERAL),
         ClauseScoreBase(status=ClauseStatus.NOT_APPLICABLE, confidence=0.90)),
        (ComplianceClauseBase(clause_number="1.3", clause_text="Test", category=ClauseCategory.TECHNICAL),
         ClauseScoreBase(status=ClauseStatus.COMPLIANT, confidence=0.92)),
    ]
    
    summary = generate_evaluation_summary(scored_clauses)
    
    assert summary["total_clauses"] == 3
    assert summary["counts"]["not_applicable"] == 1
    assert summary["counts"]["compliant"] == 2
    
    # Only scored clauses count for percentage
    assert summary["compliance_percentage"] == 100.0
    print("✓ Evaluation summary (with NA) passed")


def test_status_mapping():
    """Test status string to enum mapping."""
    status_map = {
        "compliant": ClauseStatus.COMPLIANT,
        "partial": ClauseStatus.PARTIAL,
        "non_compliant": ClauseStatus.NON_COMPLIANT,
        "non-compliant": ClauseStatus.NON_COMPLIANT,
        "not_applicable": ClauseStatus.NOT_APPLICABLE,
        "not-applicable": ClauseStatus.NOT_APPLICABLE,
        "pending": ClauseStatus.PENDING,
    }
    
    for key, expected in status_map.items():
        assert status_map[key] == expected, f"Failed for {key}"
    
    print("✓ Status mapping passed")


def test_confidence_capping():
    """Test that confidence values are capped at 1.0."""
    result = ScoringResult(
        clause_number="1.1",
        status=ClauseStatus.COMPLIANT,
        confidence=1.5,  # Over limit
        vendor_response_summary="Test",
        evidence_text="Test evidence text that is long enough to get high score",
        gaps_identified=None,
        recommendation="accept",
        llm_raw_response="raw"
    )
    
    clause = ComplianceClauseBase(
        clause_number="1.1",
        clause_title="Test",
        clause_text="Test",
        category=ClauseCategory.TECHNICAL,
        is_mandatory=True,
        is_critical=False,
        acceptance_criteria="Test"
    )
    
    factors = calculate_confidence_factors(result, clause)
    
    # Final confidence should be capped
    assert factors["final_confidence"] <= 1.0
    print("✓ Confidence capping passed")


def test_empty_scored_clauses():
    """Test summary with no clauses."""
    summary = generate_evaluation_summary([])
    
    assert summary["total_clauses"] == 0
    assert summary["compliance_percentage"] == 0.0
    assert summary["average_confidence"] == 0.0
    print("✓ Empty scored clauses passed")


def test_progress_callback_simulation():
    """Test progress tracking simulation."""
    progress_calls = []
    
    def mock_callback(clause_number, status, progress_percent):
        progress_calls.append((clause_number, status, progress_percent))
    
    # Simulate processing 4 clauses
    for i in range(4):
        mock_callback(f"1.{i+1}", "compliant", int((i+1)/4*100))
    
    assert len(progress_calls) == 4
    assert progress_calls[0] == ("1.1", "compliant", 25)
    assert progress_calls[3] == ("1.4", "compliant", 100)
    print("✓ Progress callback simulation passed")


def run_all_tests():
    """Run all clause scorer tests."""
    print("=" * 60)
    print("Clause Scorer Tests (Phase 3)")
    print("=" * 60)
    
    tests = [
        test_parse_llm_json_with_markdown,
        test_parse_llm_json_without_markdown,
        test_parse_llm_json_invalid,
        test_parse_llm_json_array,
        test_scoring_result_structure,
        test_calculate_confidence_factors_high_evidence,
        test_calculate_confidence_factors_low_evidence,
        test_calculate_confidence_factors_direct_reference,
        test_generate_evaluation_summary_perfect,
        test_generate_evaluation_summary_mixed,
        test_generate_evaluation_summary_reject,
        test_generate_evaluation_summary_with_not_applicable,
        test_status_mapping,
        test_confidence_capping,
        test_empty_scored_clauses,
        test_progress_callback_simulation,
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

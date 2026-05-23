"""
AGRA Compliance Module Phase 1 Tests — Data Models
Verify Pydantic and SQLAlchemy compliance models.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from api.models.compliance_models import (
    ComplianceStatus,
    ClauseStatus,
    Recommendation,
    ClauseCategory,
    ComplianceEvaluationRequest,
    ClauseScoreRequest,
    ComplianceReportRequest,
    ComplianceClauseBase,
    ComplianceSummary,
    ComplianceEvaluationResponse,
    SmartComplianceSuggestion,
)


def test_compliance_status_enum():
    """Test compliance status enum values."""
    assert ComplianceStatus.CREATED == "created"
    assert ComplianceStatus.PARSING_SOTR == "parsing_sotr"
    assert ComplianceStatus.SCORING == "scoring"
    assert ComplianceStatus.COMPLETED == "completed"
    assert ComplianceStatus.FAILED == "failed"
    print("✓ ComplianceStatus enum passed")


def test_clause_status_enum():
    """Test clause status enum values."""
    assert ClauseStatus.COMPLIANT == "compliant"
    assert ClauseStatus.PARTIAL == "partial"
    assert ClauseStatus.NON_COMPLIANT == "non_compliant"
    assert ClauseStatus.NOT_APPLICABLE == "not_applicable"
    assert ClauseStatus.PENDING == "pending"
    print("✓ ClauseStatus enum passed")


def test_recommendation_enum():
    """Test recommendation enum values."""
    assert Recommendation.ACCEPT == "accept"
    assert Recommendation.CONDITIONAL == "conditional"
    assert Recommendation.REJECT == "reject"
    print("✓ Recommendation enum passed")


def test_clause_category_enum():
    """Test clause category enum values."""
    assert ClauseCategory.TECHNICAL == "technical"
    assert ClauseCategory.COMMERCIAL == "commercial"
    assert ClauseCategory.SAFETY == "safety"
    assert ClauseCategory.GENERAL == "general"
    print("✓ ClauseCategory enum passed")


def test_compliance_evaluation_request():
    """Test evaluation request model."""
    request = ComplianceEvaluationRequest(
        sotr_doc_id=123,
        vendor_doc_id=456,
        project_name="OPV Project",
        vessel_name="ICGS Sarthi",
        vendor_name="ABC Shipyard",
        auto_start=True
    )
    
    assert request.sotr_doc_id == 123
    assert request.vendor_doc_id == 456
    assert request.project_name == "OPV Project"
    assert request.vessel_name == "ICGS Sarthi"
    assert request.vendor_name == "ABC Shipyard"
    assert request.auto_start == True
    print("✓ ComplianceEvaluationRequest model passed")


def test_clause_score_request():
    """Test clause score request model."""
    request = ClauseScoreRequest(
        clause_id=789,
        status=ClauseStatus.COMPLIANT,
        notes="Vendor meets all requirements",
        confidence=0.95
    )
    
    assert request.clause_id == 789
    assert request.status == ClauseStatus.COMPLIANT
    assert request.notes == "Vendor meets all requirements"
    assert request.confidence == 0.95
    print("✓ ClauseScoreRequest model passed")


def test_compliance_report_request():
    """Test report request model."""
    request = ComplianceReportRequest(
        report_type="full",
        include_appendix=True
    )
    
    assert request.report_type == "full"
    assert request.include_appendix == True
    print("✓ ComplianceReportRequest model passed")


def test_compliance_clause_base():
    """Test compliance clause base model."""
    clause = ComplianceClauseBase(
        clause_number="1.2.1",
        clause_title="Hull Construction",
        clause_text="The hull shall be constructed to IRS rules",
        category=ClauseCategory.TECHNICAL,
        is_mandatory=True,
        is_critical=True,
        acceptance_criteria="IRS Class approval"
    )
    
    assert clause.clause_number == "1.2.1"
    assert clause.clause_title == "Hull Construction"
    assert clause.category == ClauseCategory.TECHNICAL
    assert clause.is_mandatory == True
    assert clause.is_critical == True
    print("✓ ComplianceClauseBase model passed")


def test_compliance_summary():
    """Test compliance summary calculations."""
    summary = ComplianceSummary(
        total_clauses=20,
        compliant_count=15,
        partial_count=3,
        non_compliant_count=2,
        not_applicable_count=0,
        compliance_percentage=75.0
    )
    
    assert summary.total_clauses == 20
    assert summary.compliant_count == 15
    assert summary.partial_count == 3
    assert summary.non_compliant_count == 2
    assert summary.compliance_percentage == 75.0
    assert summary.scored_clauses == 20  # 15 + 3 + 2
    print("✓ ComplianceSummary model passed")


def test_smart_compliance_suggestion():
    """Test smart suggestion model."""
    suggestion = SmartComplianceSuggestion(
        detected_doc_type="bid_document",
        confidence=0.92,
        suggested_action="select_sotr",
        suggested_sotr_id=123,
        suggested_sotr_name="SOTR_OPV_Construction.pdf",
        message="Bid document detected. Select SOTR to check compliance."
    )
    
    assert suggestion.detected_doc_type == "bid_document"
    assert suggestion.confidence == 0.92
    assert suggestion.suggested_action == "select_sotr"
    assert suggestion.suggested_sotr_id == 123
    print("✓ SmartComplianceSuggestion model passed")


def test_request_validation():
    """Test model validation."""
    # Valid request
    try:
        request = ComplianceEvaluationRequest(
            sotr_doc_id=1,
            vendor_doc_id=2
        )
        assert request.auto_start == False  # Default value
        print("✓ Request validation passed")
    except Exception as e:
        print(f"✗ Request validation failed: {e}")
        raise


def test_clause_score_confidence_range():
    """Test confidence score validation."""
    # Valid confidence
    request = ClauseScoreRequest(
        clause_id=1,
        status=ClauseStatus.COMPLIANT,
        confidence=0.85
    )
    assert request.confidence == 0.85
    
    # Edge cases
    request_zero = ClauseScoreRequest(
        clause_id=1,
        status=ClauseStatus.PENDING,
        confidence=0.0
    )
    assert request_zero.confidence == 0.0
    
    request_max = ClauseScoreRequest(
        clause_id=1,
        status=ClauseStatus.COMPLIANT,
        confidence=1.0
    )
    assert request_max.confidence == 1.0
    
    print("✓ Clause score confidence range passed")


def test_json_schema_generation():
    """Test that models can generate JSON schema."""
    try:
        schema = ComplianceEvaluationRequest.model_json_schema()
        assert "properties" in schema
        assert "sotr_doc_id" in schema["properties"]
        assert "vendor_doc_id" in schema["properties"]
        print("✓ JSON schema generation passed")
    except Exception as e:
        print(f"✗ JSON schema generation failed: {e}")
        raise


def test_backward_compatibility_import():
    """Test that all models can be imported from package."""
    from api.models import (
        ComplianceStatus,
        ClauseStatus,
        ComplianceEvaluationRequest,
        ComplianceClauseResponse,
        ComplianceEvaluationResponse,
    )
    
    # Verify they're the same
    assert ComplianceStatus.CREATED == "created"
    assert ClauseStatus.COMPLIANT == "compliant"
    print("✓ Package import backward compatibility passed")


def run_all_tests():
    """Run all compliance model tests."""
    print("=" * 60)
    print("Compliance Module Phase 1 — Model Tests")
    print("=" * 60)
    
    tests = [
        test_compliance_status_enum,
        test_clause_status_enum,
        test_recommendation_enum,
        test_clause_category_enum,
        test_compliance_evaluation_request,
        test_clause_score_request,
        test_compliance_report_request,
        test_compliance_clause_base,
        test_compliance_summary,
        test_smart_compliance_suggestion,
        test_request_validation,
        test_clause_score_confidence_range,
        test_json_schema_generation,
        test_backward_compatibility_import,
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

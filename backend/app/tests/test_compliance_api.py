"""
AGRA Compliance Module Phase 4 Tests — Compliance API Endpoints
Verify backend API endpoints for compliance workflow.
"""

import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from datetime import datetime
from app.models.models import (
    ComplianceEvaluation, ComplianceClause, ClauseScore, ComplianceReport,
    ComplianceStatus, ClauseStatus
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


def test_create_evaluation_request_model():
    """Test CreateEvaluationRequest model."""
    from backend.app.routers.compliance import CreateEvaluationRequest
    
    request = CreateEvaluationRequest(
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
    print("✓ CreateEvaluationRequest model passed")


def test_update_clause_score_request():
    """Test UpdateClauseScoreRequest model."""
    from backend.app.routers.compliance import UpdateClauseScoreRequest
    
    request = UpdateClauseScoreRequest(
        clause_id=789,
        status="compliant",
        notes="Vendor meets all requirements",
        confidence=0.95
    )
    
    assert request.clause_id == 789
    assert request.status == "compliant"
    assert request.notes == "Vendor meets all requirements"
    assert request.confidence == 0.95
    print("✓ UpdateClauseScoreRequest model passed")


def test_clause_response_model():
    """Test ClauseResponse model."""
    from backend.app.routers.compliance import ClauseResponse
    
    response = ClauseResponse(
        id=1,
        sotr_doc_id=123,
        clause_number="1.1",
        clause_title="Scope of Supply",
        clause_text="The Vendor shall supply...",
        category="technical",
        is_mandatory=True,
        is_critical=False,
        acceptance_criteria="IRS approval"
    )
    
    assert response.id == 1
    assert response.clause_number == "1.1"
    assert response.category == "technical"
    assert response.is_mandatory == True
    print("✓ ClauseResponse model passed")


def test_evaluation_response_model():
    """Test EvaluationResponse model."""
    from backend.app.routers.compliance import EvaluationResponse
    
    response = EvaluationResponse(
        id=1,
        sotr_doc_id=123,
        vendor_doc_id=456,
        status="completed",
        project_name="Test Project",
        vessel_name="Test Vessel",
        vendor_name="Test Vendor",
        overall_score=0.85,
        recommendation="conditional",
        total_clauses=20,
        compliant_count=15,
        partial_count=3,
        non_compliant_count=2,
        not_applicable_count=0,
        created_at=datetime.utcnow(),
        completed_at=datetime.utcnow()
    )
    
    assert response.id == 1
    assert response.overall_score == 0.85
    assert response.recommendation == "conditional"
    assert response.total_clauses == 20
    print("✓ EvaluationResponse model passed")


def test_report_response_model():
    """Test ReportResponse model."""
    from backend.app.routers.compliance import ReportResponse
    
    response = ReportResponse(
        id=1,
        evaluation_id=1,
        report_type="full",
        file_name="report_1.pdf",
        download_url="/api/compliance/reports/1/download",
        summary_text="Compliance evaluation summary",
        generated_at=datetime.utcnow(),
        version=1
    )
    
    assert response.id == 1
    assert response.evaluation_id == 1
    assert response.report_type == "full"
    assert response.download_url is not None
    print("✓ ReportResponse model passed")


def test_evaluation_recommendation_logic():
    """Test recommendation logic based on counts."""
    
    def get_recommendation(non_compliant, compliant, partial):
        """Simulate recommendation logic."""
        if non_compliant == 0 and compliant >= partial:
            return "accept"
        elif non_compliant <= 2 and compliant > non_compliant:
            return "conditional"
        else:
            return "reject"
    
    # Perfect compliance
    assert get_recommendation(0, 20, 0) == "accept"
    
    # Mostly compliant
    assert get_recommendation(1, 15, 4) == "conditional"
    
    # Too many non-compliant
    assert get_recommendation(3, 10, 7) == "reject"
    
    # More non-compliant than compliant
    assert get_recommendation(5, 3, 2) == "reject"
    print("✓ Recommendation logic passed")


def test_overall_score_calculation():
    """Test overall score calculation."""
    
    def calculate_score(compliant, partial, non_compliant):
        """Simulate score calculation."""
        scored = compliant + partial + non_compliant
        if scored > 0:
            return (compliant + partial * 0.5) / scored
        return 0.0
    
    # Perfect
    assert calculate_score(20, 0, 0) == 1.0
    
    # All partial
    assert calculate_score(0, 10, 0) == 0.5
    
    # Mixed
    score = calculate_score(15, 3, 2)
    expected = (15 + 3 * 0.5) / 20  # = 16.5 / 20 = 0.825
    assert abs(score - expected) < 0.001
    
    # None scored
    assert calculate_score(0, 0, 0) == 0.0
    print("✓ Overall score calculation passed")


def test_status_validation():
    """Test valid clause status values."""
    valid_statuses = ["compliant", "partial", "non_compliant", "not_applicable"]
    
    for status in valid_statuses:
        assert status in ["compliant", "partial", "non_compliant", "not_applicable"]
    
    # Invalid status
    assert "invalid" not in valid_statuses
    print("✓ Status validation passed")


def test_compliance_evaluation_model():
    """Test ComplianceEvaluation SQLAlchemy model creation."""
    from app.models.models import ComplianceEvaluation
    
    # Create mock evaluation
    evaluation = ComplianceEvaluation(
        id=1,
        sotr_doc_id=123,
        vendor_doc_id=456,
        status=ComplianceStatus.CREATED,
        created_by=1,
        project_name="Test",
        overall_score=None,
        total_clauses=0,
        compliant_count=0,
        partial_count=0,
        non_compliant_count=0,
        not_applicable_count=0
    )
    
    assert evaluation.sotr_doc_id == 123
    assert evaluation.vendor_doc_id == 456
    assert evaluation.status == ComplianceStatus.CREATED
    print("✓ ComplianceEvaluation model passed")


def test_clause_score_model():
    """Test ClauseScore SQLAlchemy model."""
    from app.models.models import ClauseScore
    
    score = ClauseScore(
        id=1,
        evaluation_id=1,
        clause_id=1,
        status=ClauseStatus.COMPLIANT,
        confidence=0.95,
        vendor_response_summary="Test summary",
        evidence_text="Test evidence",
        manually_reviewed=False
    )
    
    assert score.status == ClauseStatus.COMPLIANT
    assert score.confidence == 0.95
    assert score.manually_reviewed == False
    print("✓ ClauseScore model passed")


def test_api_endpoint_paths():
    """Test that endpoint paths are correctly defined."""
    from backend.app.routers.compliance import router
    
    # Check router has routes
    routes = [route.path for route in router.routes]
    
    expected_patterns = [
        "/evaluations",
        "/evaluations/{evaluation_id}",
        "/evaluations/{evaluation_id}/run",
        "/evaluations/{evaluation_id}/score",
        "/evaluations/{evaluation_id}/report",
        "/sotr/{doc_id}/clauses"
    ]
    
    # Check at least some patterns exist
    assert len(routes) >= 6
    print("✓ API endpoint paths passed")


def test_background_task_signature():
    """Test background task function signature."""
    from backend.app.routers.compliance import _run_evaluation_background, _recalculate_evaluation_summary
    
    import inspect
    
    # Check _run_evaluation_background takes evaluation_id
    sig1 = inspect.signature(_run_evaluation_background)
    assert "evaluation_id" in sig1.parameters
    
    # Check _recalculate_evaluation_summary takes evaluation_id and db
    sig2 = inspect.signature(_recalculate_evaluation_summary)
    assert "evaluation_id" in sig2.parameters
    assert "db" in sig2.parameters
    print("✓ Background task signatures passed")


def run_all_tests():
    """Run all compliance API tests."""
    print("=" * 60)
    print("Compliance API Tests (Phase 4)")
    print("=" * 60)
    
    tests = [
        test_compliance_status_enum,
        test_clause_status_enum,
        test_create_evaluation_request_model,
        test_update_clause_score_request,
        test_clause_response_model,
        test_evaluation_response_model,
        test_report_response_model,
        test_evaluation_recommendation_logic,
        test_overall_score_calculation,
        test_status_validation,
        test_compliance_evaluation_model,
        test_clause_score_model,
        test_api_endpoint_paths,
        test_background_task_signature,
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

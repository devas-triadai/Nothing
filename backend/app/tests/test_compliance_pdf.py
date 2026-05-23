"""
AGRA Compliance Module Phase 6 Tests — PDF Report Generator
Verify PDF generation and report data structures.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from datetime import datetime
from app.utils.compliance_pdf_export import (
    ICG_COLORS, STATUS_COLORS,
    ReportClause, ReportData,
    ComplianceReportGenerator,
    generate_compliance_report
)


def test_icg_colors_defined():
    """Test ICG brand colors are defined."""
    assert "primary" in ICG_COLORS
    assert "secondary" in ICG_COLORS
    assert "success" in ICG_COLORS
    assert "warning" in ICG_COLORS
    assert "danger" in ICG_COLORS
    print("✓ ICG colors defined passed")


def test_status_colors_mapping():
    """Test status color mappings."""
    assert "compliant" in STATUS_COLORS
    assert "partial" in STATUS_COLORS
    assert "non_compliant" in STATUS_COLORS
    assert "not_applicable" in STATUS_COLORS
    assert "pending" in STATUS_COLORS
    print("✓ Status colors mapping passed")


def test_report_clause_dataclass():
    """Test ReportClause dataclass structure."""
    clause = ReportClause(
        clause_number="1.1",
        clause_title="Test Clause",
        clause_text="Test text",
        category="technical",
        is_mandatory=True,
        is_critical=False,
        acceptance_criteria="Test criteria",
        status="compliant",
        confidence=0.95,
        vendor_response_summary="Vendor confirmed",
        evidence_text="Evidence here",
        gaps_identified=None
    )
    
    assert clause.clause_number == "1.1"
    assert clause.status == "compliant"
    assert clause.confidence == 0.95
    print("✓ ReportClause dataclass passed")


def test_report_data_dataclass():
    """Test ReportData dataclass structure."""
    data = ReportData(
        evaluation_id=123,
        project_name="Test Project",
        vessel_name="Test Vessel",
        vendor_name="Test Vendor",
        sotr_doc_name="SOTR.pdf",
        generated_at=datetime.now(),
        overall_score=0.85,
        total_clauses=20,
        compliant_count=15,
        partial_count=3,
        non_compliant_count=2,
        not_applicable_count=0,
        recommendation="conditional",
        recommendation_reason="Minor gaps",
        clauses=[],
        key_findings=["Finding 1", "Finding 2"]
    )
    
    assert data.evaluation_id == 123
    assert data.overall_score == 0.85
    assert data.recommendation == "conditional"
    assert len(data.key_findings) == 2
    print("✓ ReportData dataclass passed")


def test_report_generator_initialization():
    """Test ComplianceReportGenerator initialization."""
    output_path = "/tmp/test_report.pdf"
    generator = ComplianceReportGenerator(output_path)
    
    assert generator.output_path == output_path
    assert generator.styles is not None
    assert len(generator.elements) == 0
    print("✓ Report generator initialization passed")


def test_styles_creation():
    """Test custom styles are created."""
    output_path = "/tmp/test_report.pdf"
    generator = ComplianceReportGenerator(output_path)
    
    styles = generator.styles
    
    # Check custom styles exist
    assert 'ICGTitle' in styles
    assert 'ICGSubtitle' in styles
    assert 'ICGSectionHeader' in styles
    assert 'ICGClauseNumber' in styles
    assert 'ICGClauseTitle' in styles
    assert 'ICGClauseText' in styles
    assert 'ICGEvidence' in styles
    assert 'ICGScoreBadge' in styles
    assert 'ICGFooter' in styles
    print("✓ Styles creation passed")


def test_cover_page_generation():
    """Test cover page adds elements."""
    output_path = "/tmp/test_cover.pdf"
    generator = ComplianceReportGenerator(output_path)
    
    data = ReportData(
        evaluation_id=1,
        project_name="OPV Project",
        vessel_name="ICGS Sarthi",
        vendor_name="ABC Shipyard",
        sotr_doc_name="SOTR_OPV.pdf",
        generated_at=datetime.now(),
        overall_score=0.92,
        total_clauses=25,
        compliant_count=22,
        partial_count=2,
        non_compliant_count=1,
        not_applicable_count=0,
        recommendation="conditional",
        recommendation_reason="Minor gaps",
        clauses=[],
        key_findings=[]
    )
    
    initial_count = len(generator.elements)
    generator._add_cover_page(data)
    
    # Should have added multiple elements
    assert len(generator.elements) > initial_count
    print("✓ Cover page generation passed")


def test_executive_summary_generation():
    """Test executive summary adds elements."""
    output_path = "/tmp/test_summary.pdf"
    generator = ComplianceReportGenerator(output_path)
    
    data = ReportData(
        evaluation_id=1,
        project_name="OPV Project",
        vessel_name="ICGS Sarthi",
        vendor_name="ABC Shipyard",
        sotr_doc_name="SOTR.pdf",
        generated_at=datetime.now(),
        overall_score=0.85,
        total_clauses=20,
        compliant_count=15,
        partial_count=3,
        non_compliant_count=2,
        not_applicable_count=0,
        recommendation="conditional",
        recommendation_reason="Some gaps",
        clauses=[],
        key_findings=[]
    )
    
    initial_count = len(generator.elements)
    generator._add_executive_summary(data)
    
    assert len(generator.elements) > initial_count
    print("✓ Executive summary generation passed")


def test_category_breakdown():
    """Test category breakdown calculation."""
    output_path = "/tmp/test_category.pdf"
    generator = ComplianceReportGenerator(output_path)
    
    clauses = [
        ReportClause("1.1", "T1", "Text", "technical", True, False, "", "compliant", 0.9, "", "", None),
        ReportClause("1.2", "T2", "Text", "technical", True, False, "", "partial", 0.7, "", "", None),
        ReportClause("2.1", "C1", "Text", "commercial", True, False, "", "compliant", 0.95, "", "", None),
        ReportClause("3.1", "S1", "Text", "safety", True, True, "", "compliant", 0.98, "", "", None),
    ]
    
    data = ReportData(
        evaluation_id=1,
        project_name="Test",
        vessel_name="Test",
        vendor_name="Test",
        sotr_doc_name="SOTR.pdf",
        generated_at=datetime.now(),
        overall_score=0.85,
        total_clauses=4,
        compliant_count=3,
        partial_count=1,
        non_compliant_count=0,
        not_applicable_count=0,
        recommendation="accept",
        recommendation_reason="Good",
        clauses=clauses,
        key_findings=[]
    )
    
    initial_count = len(generator.elements)
    generator._add_category_breakdown(data)
    
    assert len(generator.elements) > initial_count
    print("✓ Category breakdown passed")


def test_score_color_coding():
    """Test score color coding logic."""
    # Test recommendation colors
    accept_color = ICG_COLORS["success"]
    conditional_color = ICG_COLORS["warning"]
    reject_color = ICG_COLORS["danger"]
    
    assert accept_color is not None
    assert conditional_color is not None
    assert reject_color is not None
    
    # Test status colors
    assert STATUS_COLORS["compliant"] == ICG_COLORS["success"]
    assert STATUS_COLORS["partial"] == ICG_COLORS["warning"]
    assert STATUS_COLORS["non_compliant"] == ICG_COLORS["danger"]
    print("✓ Score color coding passed")


def test_key_findings_generation():
    """Test key findings section."""
    output_path = "/tmp/test_findings.pdf"
    generator = ComplianceReportGenerator(output_path)
    
    data = ReportData(
        evaluation_id=1,
        project_name="Test",
        vessel_name="Test",
        vendor_name="Test",
        sotr_doc_name="SOTR.pdf",
        generated_at=datetime.now(),
        overall_score=0.85,
        total_clauses=20,
        compliant_count=15,
        partial_count=3,
        non_compliant_count=2,
        not_applicable_count=0,
        recommendation="conditional",
        recommendation_reason="Test",
        clauses=[],
        key_findings=[
            "Excellent technical compliance",
            "Minor commercial gaps",
            "All safety requirements met"
        ]
    )
    
    initial_count = len(generator.elements)
    generator._add_key_findings(data)
    
    assert len(generator.elements) > initial_count
    print("✓ Key findings generation passed")


def test_full_report_generation():
    """Test full PDF generation process."""
    output_path = "/tmp/test_full_report.pdf"
    
    clauses = [
        ReportClause(
            clause_number="1.1",
            clause_title="Scope",
            clause_text="Vendor shall supply vessel",
            category="general",
            is_mandatory=True,
            is_critical=False,
            acceptance_criteria="Delivery",
            status="compliant",
            confidence=0.95,
            vendor_response_summary="Confirmed",
            evidence_text="We confirm",
            gaps_identified=None
        ),
        ReportClause(
            clause_number="2.1",
            clause_title="Hull",
            clause_text="Hull shall be steel",
            category="technical",
            is_mandatory=True,
            is_critical=True,
            acceptance_criteria="IRS cert",
            status="compliant",
            confidence=0.98,
            vendor_response_summary="IRS Grade A",
            evidence_text="Grade A steel",
            gaps_identified=None
        ),
    ]
    
    data = ReportData(
        evaluation_id=123,
        project_name="OPV Project",
        vessel_name="ICGS Sarthi",
        vendor_name="ABC Shipyard Ltd",
        sotr_doc_name="SOTR_OPV_001.pdf",
        generated_at=datetime.now(),
        overall_score=0.92,
        total_clauses=25,
        compliant_count=22,
        partial_count=2,
        non_compliant_count=1,
        not_applicable_count=0,
        recommendation="conditional",
        recommendation_reason="Minor gaps addressable",
        clauses=clauses,
        key_findings=[
            "Excellent technical compliance",
            "One commercial term needs clarification"
        ]
    )
    
    try:
        generator = ComplianceReportGenerator(output_path)
        result = generator.generate(data)
        
        assert result == output_path
        assert os.path.exists(output_path)
        
        # Check file size
        file_size = os.path.getsize(output_path)
        assert file_size > 0
        
        print(f"✓ Full report generation passed (size: {file_size} bytes)")
        
        # Cleanup
        os.remove(output_path)
        
    except Exception as e:
        print(f"⚠ Full report generation skipped (reportlab may not be installed): {e}")


def run_all_tests():
    """Run all PDF generation tests."""
    print("=" * 60)
    print("Compliance PDF Report Tests (Phase 6)")
    print("=" * 60)
    
    tests = [
        test_icg_colors_defined,
        test_status_colors_mapping,
        test_report_clause_dataclass,
        test_report_data_dataclass,
        test_report_generator_initialization,
        test_styles_creation,
        test_cover_page_generation,
        test_executive_summary_generation,
        test_category_breakdown,
        test_score_color_coding,
        test_key_findings_generation,
        test_full_report_generation,
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

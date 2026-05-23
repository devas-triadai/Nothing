"""
Module 5 & 10 — Unit Tests for Content Generation & Genealogy Integration
Tests executive summary, PPT generation, and quiz with genealogy/provenance.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from api.utils.genealogy_client import (
    format_superseded_warning,
    format_genealogy_provenance,
    format_multi_doc_citation,
    should_include_genealogy,
)


def test_format_superseded_warning():
    """Test superseded warning formatting."""
    superseded_docs = {
        "doc1": {"superseded_by_name": "New_SOP_v2.pdf", "date": "2024-01-15"},
        "doc2": {"superseded_by_name": "Updated_Manual.pdf", "date": "2024-02-20"},
    }
    
    warning = format_superseded_warning(superseded_docs)
    
    assert "⚠️" in warning
    assert "DOCUMENT STATUS WARNING" in warning
    assert "New_SOP_v2.pdf" in warning
    assert "Updated_Manual.pdf" in warning
    assert "superseded" in warning.lower()


def test_format_superseded_warning_empty():
    """Test empty superseded dict returns empty string."""
    warning = format_superseded_warning({})
    assert warning == ""


def test_format_genealogy_provenance():
    """Test genealogy provenance table formatting."""
    lineage_info = [
        {
            "filename": "SOP_v1.pdf",
            "version": 1,
            "status": "superseded",
            "superseded_by_name": "SOP_v2.pdf",
        },
        {
            "filename": "SOP_v2.pdf",
            "version": 2,
            "status": "current",
            "supersedes": [{"filename": "SOP_v1.pdf"}],
        },
    ]
    
    provenance = format_genealogy_provenance(lineage_info)
    
    assert "Document Genealogy" in provenance
    assert "SOP_v1.pdf" in provenance
    assert "SOP_v2.pdf" in provenance
    assert "v1" in provenance
    assert "v2" in provenance
    assert "|" in provenance  # Markdown table format


def test_format_genealogy_provenance_empty():
    """Test empty genealogy returns empty string."""
    provenance = format_genealogy_provenance([])
    assert provenance == ""


def test_format_multi_doc_citation():
    """Test multi-document citation format."""
    citation = format_multi_doc_citation(1, "Safety_Manual_v3.pdf", "12")
    
    assert "Safety_Manual" in citation
    assert "p.12" in citation
    assert "[" in citation and "]" in citation


def test_should_include_genealogy():
    """Test genealogy inclusion check."""
    # Should include for non-builtin docs
    assert should_include_genealogy(["doc1", "doc2"]) == True
    assert should_include_genealogy(["123", "456"]) == True
    
    # Should NOT include for only builtin docs
    assert should_include_genealogy(["builtin:standard1", "builtin:standard2"]) == False
    
    # Mixed should include
    assert should_include_genealogy(["builtin:standard1", "doc123"]) == True


def test_should_include_genealogy_empty():
    """Test empty list returns False."""
    assert should_include_genealogy([]) == False


# Mock tests for genealogy client functions

def test_genealogy_client_imports():
    """Test that all genealogy client functions can be imported."""
    try:
        from api.utils.genealogy_client import (
            check_superseded_status,
            get_document_lineage,
            _get_cached,
            _set_cache,
        )
        assert True
    except ImportError as e:
        assert False, f"Failed to import genealogy_client functions: {e}"


def test_citation_validator_imports():
    """Test citation validator imports for Module 2 integration."""
    try:
        from api.rag.citation_validator import (
            extract_citations,
            validate_citations_against_sources,
            format_validation_report,
        )
        assert True
    except ImportError as e:
        assert False, f"Failed to import citation_validator: {e}"


def test_hallucination_detector_imports():
    """Test hallucination detector imports for Module 2 integration."""
    try:
        from api.rag.hallucination_detector import (
            extract_claims,
            verify_claim_against_source,
            detect_hallucinations,
            format_hallucination_report,
        )
        assert True
    except ImportError as e:
        assert False, f"Failed to import hallucination_detector: {e}"


if __name__ == "__main__":
    print("Running Module 5 & 10 unit tests...")
    
    tests = [
        test_format_superseded_warning,
        test_format_superseded_warning_empty,
        test_format_genealogy_provenance,
        test_format_genealogy_provenance_empty,
        test_format_multi_doc_citation,
        test_should_include_genealogy,
        test_should_include_genealogy_empty,
        test_genealogy_client_imports,
        test_citation_validator_imports,
        test_hallucination_detector_imports,
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

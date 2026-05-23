"""
AGRA Chat Enhancement Phase 3 Tests — Drawing Context Search
Verify term extraction, query building, relevance scoring, and context assembly.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from api.rag.drawing_context_search import (
    DrawingSearchTerms,
    SearchResult,
    ContextAssembly,
    extract_search_terms,
    build_vessel_queries,
    build_drawing_queries,
    build_equipment_queries,
    build_compliance_queries,
    calculate_relevance_boost,
    categorize_results,
    _infer_vessel_type,
    assemble_context
)


def test_drawing_search_terms_dataclass():
    """Test DrawingSearchTerms dataclass initialization."""
    terms = DrawingSearchTerms(
        vessel_name="ICGS Sarthi",
        drawing_number="OPV-001",
        project_name="OPV Project"
    )
    
    assert terms.vessel_name == "ICGS Sarthi"
    assert terms.drawing_number == "OPV-001"
    assert terms.project_name == "OPV Project"
    assert terms.equipment_tags == []  # Default
    assert terms.materials == []  # Default
    print("✓ DrawingSearchTerms dataclass passed")


def test_extract_search_terms_full():
    """Test search term extraction with complete drawing data."""
    drawing_data = {
        "title_block": {
            "vessel_name": "ICGS Sarthi",
            "drawing_number": "OPV-HULL-001",
            "project_name": "OPV Modernization"
        },
        "drawing_type": "structural_drawing",
        "equipment_tags": [
            {"tag_number": "HULL-MAIN"},
            {"tag_number": "STEEL-A1"}
        ],
        "dimensions": [{"name": "Length", "value": 85.5}],
        "ocr_metadata": {
            "printed_text": "Grade-A Steel Hull Section 12mm thickness"
        }
    }
    
    terms = extract_search_terms(drawing_data)
    
    assert terms.vessel_name == "ICGS Sarthi"
    assert terms.drawing_number == "OPV-HULL-001"
    assert terms.project_name == "OPV Modernization"
    assert terms.drawing_type == "structural_drawing"
    assert len(terms.equipment_tags) == 2
    assert "steel" in terms.materials or "grade-a" in terms.materials
    print("✓ Extract search terms full passed")


def test_extract_search_terms_minimal():
    """Test search term extraction with minimal drawing data."""
    drawing_data = {
        "title_block": {},
        "drawing_type": "unknown",
        "equipment_tags": []
    }
    
    terms = extract_search_terms(drawing_data)
    
    assert terms.vessel_name is None
    assert terms.drawing_number is None
    assert terms.drawing_type == "unknown"
    assert terms.equipment_tags == []
    print("✓ Extract search terms minimal passed")


def test_build_vessel_queries():
    """Test vessel query building."""
    terms = DrawingSearchTerms(
        vessel_name="ICGS Sarthi",
        project_name="OPV Project",
        drawing_type="general_arrangement"
    )
    
    queries = build_vessel_queries(terms)
    
    assert len(queries) >= 2
    assert any("ICGS Sarthi" in q for q in queries)
    assert any("OPV Project" in q for q in queries)
    print(f"✓ Build vessel queries passed ({len(queries)} queries)")


def test_build_drawing_queries():
    """Test drawing query building."""
    terms = DrawingSearchTerms(
        drawing_number="OPV-HULL-001-R1",
        drawing_type="structural_drawing"
    )
    
    queries = build_drawing_queries(terms)
    
    assert len(queries) >= 1
    # Should extract base number (remove revision)
    assert any("OPV-HULL-001" in q for q in queries)
    print(f"✓ Build drawing queries passed ({len(queries)} queries)")


def test_build_equipment_queries():
    """Test equipment query building."""
    terms = DrawingSearchTerms(
        equipment_tags=["ENG-001", "HULL-A1", "PUMP-12"],
        materials=["steel", "grade-a"]
    )
    
    queries = build_equipment_queries(terms)
    
    assert len(queries) >= 3  # At least 3 for 3 tags
    assert any("ENG-001" in q for q in queries)
    assert any("steel" in q for q in queries)
    print(f"✓ Build equipment queries passed ({len(queries)} queries)")


def test_build_compliance_queries():
    """Test compliance/SOTR query building."""
    terms = DrawingSearchTerms(
        vessel_name="ICGS Sarthi",
        drawing_type="general_arrangement"
    )
    
    queries = build_compliance_queries(terms)
    
    assert len(queries) >= 2
    assert any("SOTR" in q or "sotr" in q.lower() for q in queries)
    assert any("ICGS Sarthi" in q for q in queries)
    print(f"✓ Build compliance queries passed ({len(queries)} queries)")


def test_infer_vessel_type():
    """Test vessel type inference from drawing type."""
    assert _infer_vessel_type("general_arrangement") == "OPV offshore patrol vessel"
    assert _infer_vessel_type("structural_drawing") == "hull structural"
    assert _infer_vessel_type("piping_diagram") == "marine piping systems"
    assert _infer_vessel_type("electrical_schematic") == "marine electrical"
    assert _infer_vessel_type("unknown_type") is None
    print("✓ Infer vessel type passed")


def test_calculate_relevance_boost_vessel_match():
    """Test relevance boost for vessel name match."""
    terms = DrawingSearchTerms(vessel_name="ICGS Sarthi")
    
    result = {
        "metadata": {
            "vessel_name": "ICGS Sarthi",
            "filename": "Sarthi_Specs.pdf"
        }
    }
    
    boost = calculate_relevance_boost(result, terms)
    
    assert boost >= 1.5  # Vessel match gives 1.5x boost
    print(f"✓ Relevance boost vessel match passed (boost: {boost})")


def test_calculate_relevance_boost_drawing_match():
    """Test relevance boost for drawing number match."""
    terms = DrawingSearchTerms(drawing_number="OPV-001")
    
    result = {
        "metadata": {
            "title_block": {"drawing_number": "OPV-001"}
        }
    }
    
    boost = calculate_relevance_boost(result, terms)
    
    assert boost >= 2.0  # Drawing match gives 2.0x boost
    print(f"✓ Relevance boost drawing match passed (boost: {boost})")


def test_calculate_relevance_boost_no_match():
    """Test relevance boost when no matches."""
    terms = DrawingSearchTerms(vessel_name="ICGS Sarthi")
    
    result = {
        "metadata": {
            "vessel_name": "Different Vessel",
            "doc_type": "specification"
        }
    }
    
    boost = calculate_relevance_boost(result, terms)
    
    assert boost == 1.0  # No boost
    print(f"✓ Relevance boost no match passed (boost: {boost})")


def test_categorize_results():
    """Test result categorization."""
    results = [
        SearchResult(
            document_id="1",
            document_name="Sarthi_SOTR.pdf",
            document_type="sotr_requirements",
            relevance_score=0.9,
            excerpt="SOTR document"
        ),
        SearchResult(
            document_id="2",
            document_name="Vessel_Specs.pdf",
            document_type="vessel_specification",
            relevance_score=0.85,
            excerpt="Vessel specs",
            metadata={"vessel_name": "ICGS Sarthi"}
        ),
        SearchResult(
            document_id="3",
            document_name="Blueprint.pdf",
            document_type="blueprint",
            relevance_score=0.8,
            excerpt="Drawing"
        ),
        SearchResult(
            document_id="4",
            document_name="Parts.pdf",
            document_type="parts_catalog",
            relevance_score=0.75,
            excerpt="Equipment parts"
        )
    ]
    
    vessel_specs, drawings, parts, sotrs, other = categorize_results(results)
    
    assert len(sotrs) == 1
    assert len(vessel_specs) == 1
    assert len(drawings) == 1
    assert len(parts) == 1
    assert len(other) == 0
    print("✓ Categorize results passed")


def test_search_result_model():
    """Test SearchResult model validation."""
    result = SearchResult(
        document_id="doc-123",
        document_name="test.pdf",
        document_type="specification",
        relevance_score=0.85,
        excerpt="Test excerpt",
        vessel_name="ICGS Sarthi",
        drawing_number="OPV-001",
        equipment_tags=["TAG-1"]
    )
    
    assert result.relevance_score == 0.85
    assert result.vessel_name == "ICGS Sarthi"
    assert result.drawing_number == "OPV-001"
    print("✓ SearchResult model passed")


def test_context_assembly_model():
    """Test ContextAssembly model."""
    assembly = ContextAssembly(
        vessel_matches=[],
        similar_drawings=[],
        matching_parts=[],
        related_sotrs=[],
        raw_context_text="Test context",
        total_sources=5,
        highest_relevance=0.9
    )
    
    assert assembly.total_sources == 5
    assert assembly.highest_relevance == 0.9
    print("✓ ContextAssembly model passed")


def test_assemble_context():
    """Test context assembly function."""
    drawing_data = {
        "title_block": {"vessel_name": "Test Vessel"},
        "drawing_type": "test"
    }
    
    search_results = [
        SearchResult(
            document_id="1",
            document_name="Vessel_Specs.pdf",
            document_type="vessel_specification",
            relevance_score=0.9,
            excerpt="Vessel specifications for Test Vessel",
            vessel_name="Test Vessel"
        ),
        SearchResult(
            document_id="2",
            document_name="Blueprint.pdf",
            document_type="blueprint",
            relevance_score=0.8,
            excerpt="Similar blueprint"
        )
    ]
    
    context = assemble_context(drawing_data, search_results)
    
    assert context.total_sources == 2
    assert context.highest_relevance == 0.9
    assert len(context.vessel_matches) == 1
    assert len(context.similar_drawings) == 1
    assert len(context.raw_context_text) > 0
    print("✓ Assemble context passed")


def test_extract_materials_from_ocr():
    """Test material extraction from OCR text."""
    drawing_data = {
        "title_block": {},
        "equipment_tags": [],
        "ocr_metadata": {
            "printed_text": "Grade-A Steel construction with Aluminum fittings"
        }
    }
    
    terms = extract_search_terms(drawing_data)
    
    assert "steel" in terms.materials or "grade-a" in terms.materials
    print(f"✓ Extract materials from OCR passed: {terms.materials}")


def run_all_tests():
    """Run all drawing context search tests."""
    print("=" * 60)
    print("Drawing Context Search Phase 3 Tests")
    print("=" * 60)
    
    tests = [
        test_drawing_search_terms_dataclass,
        test_extract_search_terms_full,
        test_extract_search_terms_minimal,
        test_build_vessel_queries,
        test_build_drawing_queries,
        test_build_equipment_queries,
        test_build_compliance_queries,
        test_infer_vessel_type,
        test_calculate_relevance_boost_vessel_match,
        test_calculate_relevance_boost_drawing_match,
        test_calculate_relevance_boost_no_match,
        test_categorize_results,
        test_search_result_model,
        test_context_assembly_model,
        test_assemble_context,
        test_extract_materials_from_ocr,
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

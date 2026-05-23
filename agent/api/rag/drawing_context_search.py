"""
AGRA Chat Enhancement Phase 3 — Drawing Context Search
RAG integration to search vessel database using extracted drawing data.

Offline/Local: Uses Qdrant vector store at localhost
"""

import logging
import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from pydantic import BaseModel, Field

from api.rag.vector_store import get_store

logger = logging.getLogger("agra.drawing_context_search")


# ═══════════════════════════════════════════════════════════════
#  DATA MODELS
# ═══════════════════════════════════════════════════════════════

class SearchResult(BaseModel):
    """A single search result from vector store."""
    document_id: str
    document_name: str
    document_type: str
    relevance_score: float = Field(..., ge=0.0, le=1.0)
    excerpt: str
    metadata: Dict[str, Any] = {}
    vessel_name: Optional[str] = None
    drawing_number: Optional[str] = None
    equipment_tags: List[str] = []


class ContextAssembly(BaseModel):
    """Assembled context for LLM consumption."""
    vessel_matches: List[SearchResult]
    similar_drawings: List[SearchResult]
    matching_parts: List[SearchResult]
    related_sotrs: List[SearchResult]
    raw_context_text: str
    total_sources: int
    highest_relevance: float


class SearchMetrics(BaseModel):
    """Metrics for search operations."""
    total_searches: int = 0
    avg_results_per_search: float = 0.0
    cache_hits: int = 0
    vessel_match_rate: float = 0.0


# ═══════════════════════════════════════════════════════════════
#  SEARCH TERM EXTRACTION
# ═══════════════════════════════════════════════════════════════

@dataclass
class DrawingSearchTerms:
    """Extracted search terms from a drawing."""
    vessel_name: Optional[str] = None
    drawing_number: Optional[str] = None
    project_name: Optional[str] = None
    drawing_type: str = "unknown"
    equipment_tags: List[str] = None
    dimensions: List[Dict[str, Any]] = None
    materials: List[str] = None
    
    def __post_init__(self):
        if self.equipment_tags is None:
            self.equipment_tags = []
        if self.dimensions is None:
            self.dimensions = []
        if self.materials is None:
            self.materials = []


def extract_search_terms(drawing_data: Dict[str, Any]) -> DrawingSearchTerms:
    """
    Extract searchable terms from drawing analysis results.
    
    Args:
        drawing_data: Drawing analysis result dictionary
    
    Returns:
        DrawingSearchTerms with extracted values
    """
    terms = DrawingSearchTerms()
    
    # Extract from title block
    title_block = drawing_data.get("title_block", {})
    if isinstance(title_block, dict):
        terms.vessel_name = title_block.get("vessel_name")
        terms.drawing_number = title_block.get("drawing_number")
        terms.project_name = title_block.get("project_name")
    
    # Drawing type
    terms.drawing_type = drawing_data.get("drawing_type", "unknown")
    
    # Equipment tags
    equipment = drawing_data.get("equipment_tags", [])
    for item in equipment[:5]:  # Top 5
        if isinstance(item, dict):
            tag = item.get("tag_number") or item.get("description", "")
            if tag:
                terms.equipment_tags.append(tag)
    
    # Dimensions (for material detection)
    dimensions = drawing_data.get("dimensions", [])
    for dim in dimensions[:3]:
        if isinstance(dim, dict):
            terms.dimensions.append(dim)
    
    # Detect materials from text/OCR
    ocr_data = drawing_data.get("ocr_metadata", {})
    ocr_text = ""
    if isinstance(ocr_data, dict):
        ocr_text = ocr_data.get("printed_text", "") + " " + ocr_data.get("handwritten_text", "")
    
    # Material keywords
    material_keywords = [
        "steel", "aluminum", "aluminium", "titanium", "carbon fiber",
        "composite", "fiberglass", "GRP", "FRP", "wood", "alloy",
        "stainless", "grade-a", "grade-b", "mild steel", "MS"
    ]
    
    text_lower = ocr_text.lower()
    for material in material_keywords:
        if material.lower() in text_lower:
            terms.materials.append(material)
    
    return terms


# ═══════════════════════════════════════════════════════════════
#  QUERY BUILDERS
# ═══════════════════════════════════════════════════════════════

def build_vessel_queries(terms: DrawingSearchTerms) -> List[str]:
    """Build search queries targeting vessel specifications."""
    queries = []
    
    if terms.vessel_name:
        queries.append(f"vessel {terms.vessel_name} specifications technical data")
        queries.append(f"{terms.vessel_name} blueprints drawings specifications")
    
    if terms.project_name:
        queries.append(f"project {terms.project_name} vessel specifications")
    
    if terms.drawing_type != "unknown":
        vessel_type = _infer_vessel_type(terms.drawing_type)
        if vessel_type:
            queries.append(f"{vessel_type} vessel specifications SOTR requirements")
    
    return queries


def build_drawing_queries(terms: DrawingSearchTerms) -> List[str]:
    """Build search queries targeting similar drawings."""
    queries = []
    
    if terms.drawing_number:
        # Extract base number (remove revision suffixes)
        base_number = re.sub(r'[-_][Rr]\d+$', '', terms.drawing_number)
        queries.append(f"drawing {base_number} blueprint technical drawing")
        queries.append(f"{base_number} specifications")
    
    if terms.drawing_type != "unknown":
        type_name = terms.drawing_type.replace('_', ' ')
        queries.append(f"{type_name} blueprints vessel drawings")
    
    return queries


def build_equipment_queries(terms: DrawingSearchTerms) -> List[str]:
    """Build search queries targeting equipment/parts catalogs."""
    queries = []
    
    for tag in terms.equipment_tags[:3]:
        queries.append(f"equipment {tag} technical specifications parts catalog")
        queries.append(f"{tag} specifications manual")
    
    if terms.materials:
        material_str = " ".join(terms.materials[:2])
        queries.append(f"{material_str} vessel parts specifications")
    
    return queries


def build_compliance_queries(terms: DrawingSearchTerms) -> List[str]:
    """Build search queries targeting SOTR/compliance documents."""
    queries = []
    
    if terms.vessel_name:
        queries.append(f"SOTR requirements {terms.vessel_name}")
    
    vessel_type = _infer_vessel_type(terms.drawing_type)
    if vessel_type:
        queries.append(f"{vessel_type} SOTR technical requirements specifications")
    
    # Generic compliance
    queries.append("vessel SOTR technical specifications compliance requirements")
    
    return queries


def _infer_vessel_type(drawing_type: str) -> Optional[str]:
    """Infer vessel type from drawing type."""
    type_mapping = {
        "general_arrangement": "OPV offshore patrol vessel",
        "structural_drawing": "hull structural",
        "piping_diagram": "marine piping systems",
        "electrical_schematic": "marine electrical",
        "equipment_layout": "vessel equipment",
    }
    return type_mapping.get(drawing_type)


# ═══════════════════════════════════════════════════════════════
#  RELEVANCE SCORING
# ═══════════════════════════════════════════════════════════════

def calculate_relevance_boost(
    result: Dict[str, Any],
    terms: DrawingSearchTerms
) -> float:
    """
    Calculate relevance boost based on exact matches.
    
    Returns:
        Boost multiplier (1.0 = no boost)
    """
    boost = 1.0
    
    meta = result.get("metadata", {})
    
    # Vessel name exact match
    if terms.vessel_name:
        result_vessel = meta.get("vessel_name") or meta.get("title_block", {}).get("vessel_name", "")
        if result_vessel and terms.vessel_name.lower() == result_vessel.lower():
            boost *= 1.5
    
    # Drawing number exact match
    if terms.drawing_number:
        result_drawing = meta.get("drawing_number") or meta.get("title_block", {}).get("drawing_number", "")
        if result_drawing and terms.drawing_number.lower() == result_drawing.lower():
            boost *= 2.0
    
    # Equipment tag match
    if terms.equipment_tags:
        result_equipment = meta.get("equipment_tags", [])
        for tag in terms.equipment_tags:
            if any(tag.lower() in str(e).lower() for e in result_equipment):
                boost *= 1.3
                break
    
    # Document type relevance
    doc_type = meta.get("doc_type", "").lower()
    if "sotr" in doc_type or "specification" in doc_type:
        boost *= 1.2
    if "blueprint" in doc_type or "drawing" in doc_type:
        boost *= 1.15
    
    return boost


# ═══════════════════════════════════════════════════════════════
#  SEARCH EXECUTION
# ═══════════════════════════════════════════════════════════════

def execute_search(
    queries: List[str],
    terms: DrawingSearchTerms,
    top_k: int = 5,
    filters: Optional[Dict[str, Any]] = None
) -> List[SearchResult]:
    """
    Execute vector store search with relevance boosting.
    
    Args:
        queries: List of search queries
        terms: Extracted search terms for boosting
        top_k: Number of results per query
        filters: Optional document type filters
    
    Returns:
        List of SearchResult with boosted relevance
    """
    store = get_store()
    all_results = []
    seen_ids = set()
    
    for query in queries:
        try:
            raw_results = store.search(query, top_k=top_k)
            
            for raw in raw_results:
                doc_id = raw.get("id", "")
                if doc_id in seen_ids:
                    continue
                seen_ids.add(doc_id)
                
                # Get base score
                base_score = raw.get("score", 0.0)
                
                # Apply boost
                boost = calculate_relevance_boost(raw, terms)
                final_score = min(base_score * boost, 0.99)  # Cap at 0.99
                
                # Extract metadata
                meta = raw.get("metadata", {})
                tb = meta.get("title_block", {})
                
                result = SearchResult(
                    document_id=doc_id,
                    document_name=meta.get("filename", "Unknown"),
                    document_type=meta.get("doc_type", "document"),
                    relevance_score=round(final_score, 3),
                    excerpt=raw.get("text", "")[:400],
                    metadata=meta,
                    vessel_name=tb.get("vessel_name") or meta.get("vessel_name"),
                    drawing_number=tb.get("drawing_number") or meta.get("drawing_number"),
                    equipment_tags=meta.get("equipment_tags", [])
                )
                all_results.append(result)
                
        except Exception as e:
            logger.warning(f"Search failed for query '{query}': {e}")
            continue
    
    # Sort by relevance and return
    all_results.sort(key=lambda x: x.relevance_score, reverse=True)
    return all_results


# ═══════════════════════════════════════════════════════════════
#  CONTEXT ASSEMBLY
# ═══════════════════════════════════════════════════════════════

def categorize_results(results: List[SearchResult]) -> Tuple[List[SearchResult], ...]:
    """
    Categorize search results by document type.
    
    Returns:
        Tuple of (vessel_specs, drawings, parts, sotrs, other)
    """
    vessel_specs = []
    drawings = []
    parts = []
    sotrs = []
    other = []
    
    for result in results:
        doc_type = result.document_type.lower()
        
        if "sotr" in doc_type or "requirement" in doc_type:
            sotrs.append(result)
        elif "spec" in doc_type and "vessel" in str(result.metadata).lower():
            vessel_specs.append(result)
        elif "drawing" in doc_type or "blueprint" in doc_type:
            drawings.append(result)
        elif "part" in doc_type or "equipment" in doc_type or "catalog" in doc_type:
            parts.append(result)
        else:
            other.append(result)
    
    return vessel_specs, drawings, parts, sotrs, other


def assemble_context(
    drawing_data: Dict[str, Any],
    search_results: List[SearchResult],
    max_tokens: int = 2000
) -> ContextAssembly:
    """
    Assemble search results into context for LLM.
    
    Args:
        drawing_data: Original drawing analysis
        search_results: Results from execute_search
        max_tokens: Approximate max tokens for context
    
    Returns:
        ContextAssembly with categorized results
    """
    # Categorize results
    vessel_specs, drawings, parts, sotrs, _ = categorize_results(search_results)
    
    # Build raw context text (truncated to fit token budget)
    context_parts = []
    char_budget = max_tokens * 4  # Rough approximation: 4 chars per token
    current_chars = 0
    
    # Priority order: vessel specs > drawings > parts > sotrs
    for category, name in [
        (vessel_specs, "Vessel Specifications"),
        (drawings, "Similar Drawings"),
        (parts, "Equipment/Parts"),
        (sotrs, "SOTR/Requirements")
    ]:
        if current_chars >= char_budget:
            break
        
        for result in category[:3]:  # Top 3 per category
            entry = f"\n[{name}] {result.document_name} (relevance: {result.relevance_score:.0%}):\n{result.excerpt[:200]}\n"
            
            if current_chars + len(entry) > char_budget:
                break
            
            context_parts.append(entry)
            current_chars += len(entry)
    
    raw_context = "".join(context_parts)
    
    # Calculate highest relevance
    highest = max((r.relevance_score for r in search_results), default=0.0)
    
    return ContextAssembly(
        vessel_matches=vessel_specs[:5],
        similar_drawings=drawings[:5],
        matching_parts=parts[:5],
        related_sotrs=sotrs[:3],
        raw_context_text=raw_context,
        total_sources=len(search_results),
        highest_relevance=highest
    )


# ═══════════════════════════════════════════════════════════════
#  MAIN INTERFACE
# ═══════════════════════════════════════════════════════════════

def search_drawing_context(
    drawing_data: Dict[str, Any],
    include_vessels: bool = True,
    include_drawings: bool = True,
    include_equipment: bool = True,
    include_compliance: bool = True,
    top_k: int = 5
) -> ContextAssembly:
    """
    Main interface: Search for context related to a drawing.
    
    Args:
        drawing_data: Drawing analysis results
        include_*: Toggle different search categories
        top_k: Results per query
    
    Returns:
        ContextAssembly with all relevant context
    """
    # Extract terms
    terms = extract_search_terms(drawing_data)
    
    logger.info(f"Searching context for: vessel={terms.vessel_name}, drawing={terms.drawing_number}")
    
    all_results = []
    
    # Execute category searches
    if include_vessels:
        vessel_queries = build_vessel_queries(terms)
        vessel_results = execute_search(vessel_queries, terms, top_k)
        all_results.extend(vessel_results)
        logger.debug(f"Vessel search: {len(vessel_results)} results")
    
    if include_drawings:
        drawing_queries = build_drawing_queries(terms)
        drawing_results = execute_search(drawing_queries, terms, top_k)
        all_results.extend(drawing_results)
        logger.debug(f"Drawing search: {len(drawing_results)} results")
    
    if include_equipment and terms.equipment_tags:
        equipment_queries = build_equipment_queries(terms)
        equipment_results = execute_search(equipment_queries, terms, top_k)
        all_results.extend(equipment_results)
        logger.debug(f"Equipment search: {len(equipment_results)} results")
    
    if include_compliance:
        compliance_queries = build_compliance_queries(terms)
        compliance_results = execute_search(compliance_queries, terms, top_k)
        all_results.extend(compliance_results)
        logger.debug(f"Compliance search: {len(compliance_results)} results")
    
    # Deduplicate by ID
    seen = set()
    unique_results = []
    for r in all_results:
        if r.document_id not in seen:
            seen.add(r.document_id)
            unique_results.append(r)
    
    # Sort by relevance
    unique_results.sort(key=lambda x: x.relevance_score, reverse=True)
    
    logger.info(f"Total unique context sources: {len(unique_results)}")
    
    # Assemble context
    return assemble_context(drawing_data, unique_results)


# ═══════════════════════════════════════════════════════════════
#  QUICK SEARCH UTILITIES
# ═══════════════════════════════════════════════════════════════

def quick_vessel_search(vessel_name: str, top_k: int = 5) -> List[SearchResult]:
    """Quick search for vessel specifications by name."""
    terms = DrawingSearchTerms(vessel_name=vessel_name)
    queries = build_vessel_queries(terms)
    return execute_search(queries, terms, top_k)


def quick_drawing_search(drawing_number: str, top_k: int = 5) -> List[SearchResult]:
    """Quick search for similar drawings by number."""
    terms = DrawingSearchTerms(drawing_number=drawing_number)
    queries = build_drawing_queries(terms)
    return execute_search(queries, terms, top_k)


def quick_equipment_search(equipment_tag: str, top_k: int = 5) -> List[SearchResult]:
    """Quick search for equipment specifications."""
    terms = DrawingSearchTerms(equipment_tags=[equipment_tag])
    queries = build_equipment_queries(terms)
    return execute_search(queries, terms, top_k)


# ═══════════════════════════════════════════════════════════════
#  TEST BLOCK
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("Drawing Context Search Module - Phase 3")
    print("=" * 50)
    
    # Test term extraction
    test_drawing = {
        "title_block": {
            "vessel_name": "ICGS Sarthi",
            "drawing_number": "OPV-HULL-001-R1",
            "project_name": "OPV Modernization"
        },
        "drawing_type": "structural_drawing",
        "equipment_tags": [
            {"tag_number": "HULL-MAIN", "description": "Main hull section"},
            {"tag_number": "STEEL-A1", "description": "Grade A steel"}
        ],
        "ocr_metadata": {
            "printed_text": "Grade-A Steel Hull Section 12mm thickness"
        }
    }
    
    print("\nTest: Extract Search Terms")
    terms = extract_search_terms(test_drawing)
    print(f"  Vessel: {terms.vessel_name}")
    print(f"  Drawing: {terms.drawing_number}")
    print(f"  Equipment: {terms.equipment_tags}")
    print(f"  Materials: {terms.materials}")
    
    print("\nTest: Build Queries")
    vessel_q = build_vessel_queries(terms)
    print(f"  Vessel queries: {len(vessel_q)}")
    
    drawing_q = build_drawing_queries(terms)
    print(f"  Drawing queries: {len(drawing_q)}")
    
    equipment_q = build_equipment_queries(terms)
    print(f"  Equipment queries: {len(equipment_q)}")
    
    print("\nTest: Query Plan Examples")
    for q in vessel_q[:2]:
        print(f"  • {q}")
    
    print("\n" + "=" * 50)
    print("Context Search Module Ready")

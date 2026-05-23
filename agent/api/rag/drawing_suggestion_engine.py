"""
AGRA Chat Enhancement Phase 4 — Drawing Suggestion Engine
Generates intelligent suggestions based on drawing + database cross-reference.

Offline/Local: Uses llama-server @ localhost:8080 for advanced suggestions
"""

import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum
from pydantic import BaseModel, Field

from api.rag import llm as llm_engine
from api.rag.drawing_context_search import ContextAssembly, SearchResult

logger = logging.getLogger("agra.drawing_suggestion_engine")


# ═══════════════════════════════════════════════════════════════
#  SUGGESTION TYPES
# ═══════════════════════════════════════════════════════════════

class SuggestionType(str, Enum):
    """Types of AI-generated suggestions."""
    VESSEL_MATCH = "vessel_match"           # High compatibility with known vessel
    UPGRADE = "upgrade"                     # Material/tech upgrade available
    CROSS_REFERENCE = "cross_reference"     # Similar items in database
    GAP_ANALYSIS = "gap_analysis"           # Missing info / low confidence
    ADVANCEMENT = "advancement"             # Modernization potential
    COMPLIANCE = "compliance"               # SOTR compliance status
    STANDARDIZATION = "standardization"       # Standardization opportunity
    QUALITY_ALERT = "quality_alert"         # Quality/concern notification


# ═══════════════════════════════════════════════════════════════
#  DATA MODELS
# ═══════════════════════════════════════════════════════════════

class Suggestion(BaseModel):
    """A single AI-generated suggestion."""
    type: SuggestionType
    title: str
    description: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    priority: int = Field(..., ge=1, le=5, description="1=critical, 5=info")
    action: Optional[str] = None
    action_url: Optional[str] = None
    metadata: Dict[str, Any] = {}


class SuggestionSet(BaseModel):
    """Complete set of suggestions for a drawing query."""
    suggestions: List[Suggestion]
    summary: str
    overall_confidence: float
    total_suggestions: int
    high_priority_count: int
    critical_actions: List[str]


class SuggestionMetrics(BaseModel):
    """Metrics for suggestion generation."""
    total_generated: int = 0
    by_type: Dict[str, int] = {}
    avg_confidence: float = 0.0
    high_priority_rate: float = 0.0


# ═══════════════════════════════════════════════════════════════
#  SUGGESTION GENERATORS
# ═══════════════════════════════════════════════════════════════

def generate_vessel_match_suggestions(
    drawing_data: Dict[str, Any],
    context: ContextAssembly
) -> List[Suggestion]:
    """Generate suggestions based on vessel database matches."""
    suggestions = []
    
    title_block = drawing_data.get("title_block", {})
    vessel_name = title_block.get("vessel_name")
    
    if not vessel_name or not context.vessel_matches:
        return suggestions
    
    # Find best vessel match
    best_match = None
    for match in context.vessel_matches:
        if match.vessel_name and match.vessel_name.lower() == vessel_name.lower():
            if not best_match or match.relevance_score > best_match.relevance_score:
                best_match = match
    
    if best_match and best_match.relevance_score > 0.70:
        # High match confidence
        if best_match.relevance_score >= 0.85:
            suggestions.append(Suggestion(
                type=SuggestionType.VESSEL_MATCH,
                title=f"Exact Match: {vessel_name}",
                description=f"This drawing shows high correlation ({best_match.relevance_score:.0%}) with {vessel_name} specifications in database. Drawing appears to be an authentic {vessel_name} blueprint.",
                confidence=best_match.relevance_score,
                priority=2,
                action="view_vessel_specs",
                action_url=f"/vessels/{vessel_name}",
                metadata={
                    "vessel_name": vessel_name,
                    "match_score": best_match.relevance_score,
                    "document_id": best_match.document_id
                }
            ))
        else:
            # Good match but not exact
            suggestions.append(Suggestion(
                type=SuggestionType.VESSEL_MATCH,
                title=f"Probable Match: {vessel_name}",
                description=f"Drawing shares {best_match.relevance_score:.0%} characteristics with {vessel_name}. Likely related but may be variant or earlier revision.",
                confidence=best_match.relevance_score,
                priority=3,
                action="compare_versions",
                metadata={
                    "vessel_name": vessel_name,
                    "match_score": best_match.relevance_score
                }
            ))
    
    # Check for similar vessels (cross-vessel insights)
    similar_vessels = [m for m in context.vessel_matches 
                      if m.vessel_name and m.vessel_name.lower() != vessel_name.lower()]
    
    if similar_vessels and similar_vessels[0].relevance_score > 0.60:
        suggestions.append(Suggestion(
            type=SuggestionType.CROSS_REFERENCE,
            title=f"Similar Vessel: {similar_vessels[0].vessel_name}",
            description=f"Design patterns match {similar_vessels[0].vessel_name} ({similar_vessels[0].relevance_score:.0%}). Cross-vessel standardization possible.",
            confidence=similar_vessels[0].relevance_score,
            priority=4,
            action="view_similar_vessel",
            metadata={"similar_vessel": similar_vessels[0].vessel_name}
        ))
    
    return suggestions


def generate_upgrade_suggestions(
    drawing_data: Dict[str, Any],
    context: ContextAssembly
) -> List[Suggestion]:
    """Generate material/technology upgrade suggestions."""
    suggestions = []
    
    # Extract materials from drawing
    ocr_data = drawing_data.get("ocr_metadata", {})
    ocr_text = ""
    if isinstance(ocr_data, dict):
        ocr_text = ocr_data.get("printed_text", "") + " " + ocr_data.get("handwritten_text", "")
    
    text_lower = ocr_text.lower()
    
    # Material upgrade detection
    material_upgrades = {
        "mild steel": ("Grade-A Steel", "Upgrade to Grade-A for better corrosion resistance per latest SOTR"),
        "ms plate": ("Grade-A Steel", "Replace with Grade-A steel for improved durability"),
        "aluminum": ("Marine Aluminum 5083", "Consider 5083-H321 for better seawater corrosion resistance"),
        "wood": ("FRP Composite", "Replace with Fire-Retardant FRP for SOLAS compliance"),
        "carbon steel": ("Stainless Steel 316L", "Upgrade to 316L for critical seawater-exposed components")
    }
    
    for material, (upgrade, reason) in material_upgrades.items():
        if material in text_lower:
            # Check if vessel specs already use better material
            specs_use_better = False
            for match in context.vessel_matches:
                if upgrade.lower() in match.excerpt.lower():
                    specs_use_better = True
                    break
            
            if not specs_use_better:
                suggestions.append(Suggestion(
                    type=SuggestionType.UPGRADE,
                    title=f"Material Upgrade: {upgrade}",
                    description=f"Current: {material.upper()}. {reason}. Recommended per ICG modernization guidelines.",
                    confidence=0.75,
                    priority=3,
                    action="view_upgrade_specs",
                    metadata={
                        "current_material": material,
                        "recommended": upgrade,
                        "reason": reason
                    }
                ))
    
    return suggestions


def generate_advancement_suggestions(
    drawing_data: Dict[str, Any],
    context: ContextAssembly,
    query: str
) -> List[Suggestion]:
    """Generate modernization/advancement potential suggestions."""
    suggestions = []
    
    title_block = drawing_data.get("title_block", {})
    vessel_name = title_block.get("vessel_name")
    
    if not vessel_name:
        return suggestions
    
    # Check for SOTR documents
    sotr_matches = context.related_sotrs
    
    if sotr_matches:
        best_sotr = max(sotr_matches, key=lambda x: x.relevance_score)
        
        # If good SOTR match, suggest advancement review
        if best_sotr.relevance_score > 0.70:
            suggestions.append(Suggestion(
                type=SuggestionType.ADVANCEMENT,
                title="Modernization Potential: HIGH",
                description=f"Drawing aligns with {best_sotr.document_name} ({best_sotr.relevance_score:.0%} match). Suitable for fleet modernization consideration.",
                confidence=best_sotr.relevance_score,
                priority=2,
                action="initiate_modernization_review",
                metadata={
                    "sotr_document": best_sotr.document_name,
                    "sotr_score": best_sotr.relevance_score
                }
            ))
    
    # Check for equipment modernization
    equipment_tags = drawing_data.get("equipment_tags", [])
    if len(equipment_tags) > 3:  # Rich equipment data
        suggestions.append(Suggestion(
            type=SuggestionType.ADVANCEMENT,
            title="Equipment Upgrade Opportunity",
            description=f"{len(equipment_tags)} equipment items identified. Consider integrated system upgrade for operational efficiency.",
            confidence=0.70,
            priority=4,
            action="view_equipment_options",
            metadata={"equipment_count": len(equipment_tags)}
        ))
    
    return suggestions


def generate_quality_suggestions(
    drawing_data: Dict[str, Any],
    analysis_confidence: float
) -> List[Suggestion]:
    """Generate quality/confidence-based suggestions."""
    suggestions = []
    
    # Low overall confidence warning
    if analysis_confidence < 0.60:
        suggestions.append(Suggestion(
            type=SuggestionType.GAP_ANALYSIS,
            title="Low Analysis Confidence: Manual Review Required",
            description=f"System confidence is {analysis_confidence:.0%}. Key dimensions or specifications may be unclear. Recommend manual verification before use.",
            confidence=1.0,  # Always certain about uncertainty
            priority=1,  # Critical
            action="request_manual_review",
            metadata={"confidence": analysis_confidence, "reason": "low_extraction_confidence"}
        ))
    elif analysis_confidence < 0.75:
        suggestions.append(Suggestion(
            type=SuggestionType.QUALITY_ALERT,
            title="Moderate Confidence: Verify Critical Dimensions",
            description=f"Analysis confidence: {analysis_confidence:.0%}. Most data reliable, but verify critical measurements independently.",
            confidence=0.90,
            priority=3,
            action="verify_dimensions",
            metadata={"confidence": analysis_confidence}
        ))
    
    # Check for missing title block fields
    title_block = drawing_data.get("title_block", {})
    critical_fields = ["vessel_name", "drawing_number", "project_name"]
    missing = [f for f in critical_fields if not title_block.get(f)]
    
    if missing:
        suggestions.append(Suggestion(
            type=SuggestionType.GAP_ANALYSIS,
            title=f"Missing: {', '.join(missing).replace('_', ' ').title()}",
            description="Critical identification fields not extracted. Drawing may be incomplete or scanning quality insufficient.",
            confidence=0.85,
            priority=2,
            action="improve_scan_quality",
            metadata={"missing_fields": missing}
        ))
    
    # High confidence praise
    if analysis_confidence >= 0.85:
        suggestions.append(Suggestion(
            type=SuggestionType.QUALITY_ALERT,
            title="High Quality Analysis",
            description=f"{analysis_confidence:.0%} confidence achieved. Drawing quality excellent for automated processing.",
            confidence=analysis_confidence,
            priority=5,  # Informational
            action=None,
            metadata={"confidence": analysis_confidence}
        ))
    
    return suggestions


def generate_standardization_suggestions(
    drawing_data: Dict[str, Any],
    context: ContextAssembly
) -> List[Suggestion]:
    """Generate standardization opportunity suggestions."""
    suggestions = []
    
    similar_drawings = context.similar_drawings
    
    if len(similar_drawings) >= 3:
        # Many similar drawings = standardization opportunity
        avg_score = sum(d.relevance_score for d in similar_drawings[:3]) / 3
        
        suggestions.append(Suggestion(
            type=SuggestionType.STANDARDIZATION,
            title="Standardization Opportunity",
            description=f"{len(similar_drawings)} similar drawings found (avg {avg_score:.0%} match). Consider consolidating into standard specification to reduce inventory complexity.",
            confidence=avg_score,
            priority=4,
            action="view_standardization_options",
            metadata={
                "similar_count": len(similar_drawings),
                "avg_similarity": avg_score
            }
        ))
    
    # Check for equipment standardization
    equipment_tags = drawing_data.get("equipment_tags", [])
    if equipment_tags:
        # Look for standardized equipment in parts catalog
        standardized_matches = [m for m in context.matching_parts 
                             if any(tag.get("tag_number", "").lower() in m.excerpt.lower() 
                                   for tag in equipment_tags if isinstance(tag, dict))]
        
        if len(standardized_matches) >= 2:
            suggestions.append(Suggestion(
                type=SuggestionType.STANDARDIZATION,
                title="Equipment Standardization",
                description=f"{len(standardized_matches)} standardized equipment items found in catalog. Use approved standard parts where possible.",
                confidence=0.75,
                priority=3,
                action="view_standard_parts",
                metadata={"standard_parts_available": len(standardized_matches)}
            ))
    
    return suggestions


def generate_compliance_suggestions(
    drawing_data: Dict[str, Any],
    context: ContextAssembly
) -> List[Suggestion]:
    """Generate SOTR/compliance-related suggestions."""
    suggestions = []
    
    sotr_matches = context.related_sotrs
    
    if not sotr_matches:
        suggestions.append(Suggestion(
            type=SuggestionType.COMPLIANCE,
            title="No SOTR Reference Found",
            description="No applicable SOTR documents identified. Verify compliance requirements manually or upload relevant SOTR for automated checking.",
            confidence=0.80,
            priority=3,
            action="upload_sotr",
            metadata={"sotr_found": False}
        ))
    else:
        best_sotr = max(sotr_matches, key=lambda x: x.relevance_score)
        
        if best_sotr.relevance_score < 0.50:
            suggestions.append(Suggestion(
                type=SuggestionType.COMPLIANCE,
                title="Weak SOTR Alignment",
                description=f"Closest SOTR match: {best_sotr.document_name} ({best_sotr.relevance_score:.0%}). Review for compliance gaps.",
                confidence=best_sotr.relevance_score,
                priority=2,
                action="review_compliance",
                metadata={"sotr_match": best_sotr.relevance_score}
            ))
        else:
            suggestions.append(Suggestion(
                type=SuggestionType.COMPLIANCE,
                title="SOTR Aligned",
                description=f"Drawing aligns with {best_sotr.document_name} ({best_sotr.relevance_score:.0%}). Compliance review recommended.",
                confidence=best_sotr.relevance_score,
                priority=4,
                action="run_compliance_check",
                metadata={"sotr_match": best_sotr.relevance_score}
            ))
    
    return suggestions


# ═══════════════════════════════════════════════════════════════
#  LLM-ENHANCED SUGGESTIONS (Optional)
# ═══════════════════════════════════════════════════════════════

ADVANCED_SUGGESTION_PROMPT = """You are an expert maritime engineering consultant for the Indian Coast Guard.

DRAWING ANALYSIS:
- Vessel: {vessel_name}
- Drawing Type: {drawing_type}
- Confidence: {confidence:.0%}
- Equipment Found: {equipment_count} items

DATABASE MATCHES:
{context_summary}

Generate 2-3 strategic suggestions for this drawing. Each suggestion should be:
1. Actionable (e.g., "Upgrade to Grade-A steel", "Standardize with ICGS Sarthi specs")
2. Specific to ICG context
3. Prioritized (Critical/High/Medium/Low)

Format each suggestion as:
TITLE: <brief title>
TYPE: <vessel_match|upgrade|advancement|gap_analysis|standardization>
PRIORITY: <1-5>
DESCRIPTION: <detailed explanation>
---"""


def generate_llm_enhanced_suggestions(
    drawing_data: Dict[str, Any],
    context: ContextAssembly,
    analysis_confidence: float
) -> List[Suggestion]:
    """Generate advanced suggestions using LLM (for high-value queries)."""
    suggestions = []
    
    # Only use LLM for high-confidence analyses (saves compute)
    if analysis_confidence < 0.70:
        return suggestions
    
    try:
        title_block = drawing_data.get("title_block", {})
        vessel_name = title_block.get("vessel_name", "Unknown")
        drawing_type = drawing_data.get("drawing_type", "unknown")
        equipment = drawing_data.get("equipment_tags", [])
        
        # Build context summary
        context_parts = []
        if context.vessel_matches:
            best = max(context.vessel_matches, key=lambda x: x.relevance_score)
            context_parts.append(f"- Vessel Match: {best.vessel_name} ({best.relevance_score:.0%})")
        if context.related_sotrs:
            best = max(context.related_sotrs, key=lambda x: x.relevance_score)
            context_parts.append(f"- SOTR: {best.document_name} ({best.relevance_score:.0%})")
        if context.similar_drawings:
            context_parts.append(f"- Similar Drawings: {len(context.similar_drawings)} found")
        
        context_summary = "\n".join(context_parts) if context_parts else "- No strong database matches"
        
        # Build prompt
        prompt = ADVANCED_SUGGESTION_PROMPT.format(
            vessel_name=vessel_name,
            drawing_type=drawing_type,
            confidence=analysis_confidence,
            equipment_count=len(equipment),
            context_summary=context_summary
        )
        
        # Get LLM response
        response = llm_engine.llm_complete(
            prompt=prompt,
            max_tokens=400,
            temperature=0.3
        )
        
        # Parse suggestions from response
        # Simple parsing - look for pattern
        lines = response.strip().split('\n')
        current_suggestion = {}
        
        for line in lines:
            line = line.strip()
            if line.startswith('TITLE:'):
                current_suggestion['title'] = line[6:].strip()
            elif line.startswith('TYPE:'):
                type_str = line[5:].strip().lower()
                current_suggestion['type'] = type_str
            elif line.startswith('PRIORITY:'):
                try:
                    current_suggestion['priority'] = int(line[9:].strip())
                except:
                    current_suggestion['priority'] = 3
            elif line.startswith('DESCRIPTION:'):
                current_suggestion['description'] = line[12:].strip()
            elif line == '---' and current_suggestion:
                # Save completed suggestion
                try:
                    sug_type = SuggestionType(current_suggestion.get('type', 'quality_alert'))
                except:
                    sug_type = SuggestionType.QUALITY_ALERT
                
                suggestions.append(Suggestion(
                    type=sug_type,
                    title=current_suggestion.get('title', 'Suggestion'),
                    description=current_suggestion.get('description', ''),
                    confidence=analysis_confidence * 0.9,  # Slightly lower for LLM-generated
                    priority=current_suggestion.get('priority', 3),
                    action=None,
                    metadata={"source": "llm_enhanced"}
                ))
                current_suggestion = {}
        
        logger.info(f"LLM generated {len(suggestions)} enhanced suggestions")
        
    except Exception as e:
        logger.warning(f"LLM suggestion generation failed: {e}")
    
    return suggestions


# ═══════════════════════════════════════════════════════════════
#  MAIN SUGGESTION ENGINE
# ═══════════════════════════════════════════════════════════════

def generate_suggestions(
    drawing_data: Dict[str, Any],
    context: ContextAssembly,
    query: str,
    analysis_confidence: float,
    use_llm_enhancement: bool = False
) -> SuggestionSet:
    """
    Main suggestion engine: Generate all suggestions for a drawing query.
    
    Args:
        drawing_data: Drawing analysis results
        context: RAG context assembly
        query: Original user query
        analysis_confidence: Overall analysis confidence
        use_llm_enhancement: Whether to use LLM for advanced suggestions
    
    Returns:
        SuggestionSet with all generated suggestions
    """
    all_suggestions: List[Suggestion] = []
    
    # Generate base suggestions from different generators
    all_suggestions.extend(generate_vessel_match_suggestions(drawing_data, context))
    all_suggestions.extend(generate_upgrade_suggestions(drawing_data, context))
    all_suggestions.extend(generate_advancement_suggestions(drawing_data, context, query))
    all_suggestions.extend(generate_quality_suggestions(drawing_data, analysis_confidence))
    all_suggestions.extend(generate_standardization_suggestions(drawing_data, context))
    all_suggestions.extend(generate_compliance_suggestions(drawing_data, context))
    
    # LLM enhancement (optional, for high-value queries)
    if use_llm_enhancement and analysis_confidence >= 0.70:
        llm_suggestions = generate_llm_enhanced_suggestions(drawing_data, context, analysis_confidence)
        all_suggestions.extend(llm_suggestions)
    
    # Sort by priority (lower number = higher priority)
    all_suggestions.sort(key=lambda x: (x.priority, -x.confidence))
    
    # Deduplicate by type (keep highest confidence per type)
    seen_types = set()
    unique_suggestions = []
    for sug in all_suggestions:
        if sug.type not in seen_types:
            seen_types.add(sug.type)
            unique_suggestions.append(sug)
    
    # Build summary
    high_priority = [s for s in unique_suggestions if s.priority <= 2]
    critical_actions = [s.action for s in high_priority if s.action]
    
    if unique_suggestions:
        avg_conf = sum(s.confidence for s in unique_suggestions) / len(unique_suggestions)
    else:
        avg_conf = 0.0
    
    # Generate human-readable summary
    if len(unique_suggestions) == 0:
        summary = "No specific suggestions generated. Drawing may require manual review."
    elif len(unique_suggestions) == 1:
        summary = f"One key suggestion: {unique_suggestions[0].title}"
    else:
        priority_summary = f"{len(high_priority)} critical/high priority" if high_priority else "All suggestions are informational"
        summary = f"Generated {len(unique_suggestions)} suggestions. {priority_summary}."
    
    return SuggestionSet(
        suggestions=unique_suggestions,
        summary=summary,
        overall_confidence=round(avg_conf, 2),
        total_suggestions=len(unique_suggestions),
        high_priority_count=len(high_priority),
        critical_actions=critical_actions
    )


# ═══════════════════════════════════════════════════════════════
#  QUICK SUGGESTION UTILITIES
# ═══════════════════════════════════════════════════════════════

def quick_quality_suggestion(confidence: float) -> Optional[Suggestion]:
    """Generate a quick quality-based suggestion."""
    if confidence >= 0.85:
        return Suggestion(
            type=SuggestionType.QUALITY_ALERT,
            title="Excellent Quality",
            description=f"{confidence:.0%} confidence analysis. High reliability for decision-making.",
            confidence=confidence,
            priority=5,
            action=None
        )
    elif confidence < 0.60:
        return Suggestion(
            type=SuggestionType.GAP_ANALYSIS,
            title="Manual Review Recommended",
            description=f"Low confidence ({confidence:.0%}). Verify critical data before use.",
            confidence=1.0,
            priority=1,
            action="manual_review"
        )
    return None


def quick_vessel_suggestion(vessel_name: str, match_score: float) -> Optional[Suggestion]:
    """Generate a quick vessel match suggestion."""
    if match_score >= 0.80:
        return Suggestion(
            type=SuggestionType.VESSEL_MATCH,
            title=f"{vessel_name} Confirmed",
            description=f"High confidence match ({match_score:.0%}) with {vessel_name} database.",
            confidence=match_score,
            priority=2,
            action="view_vessel"
        )
    return None


# ═══════════════════════════════════════════════════════════════
#  TEST BLOCK
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("Drawing Suggestion Engine - Phase 4")
    print("=" * 50)
    
    # Test data
    test_drawing = {
        "title_block": {
            "vessel_name": "ICGS Sarthi",
            "drawing_number": "OPV-HULL-001",
            "project_name": "OPV Modernization"
        },
        "drawing_type": "structural_drawing",
        "equipment_tags": [{"tag_number": "HULL-MAIN"}, {"tag_number": "STEEL-A1"}],
        "ocr_metadata": {"printed_text": "Grade-A Steel Hull Section 12mm"}
    }
    
    test_context = ContextAssembly(
        vessel_matches=[
            SearchResult(
                document_id="1",
                document_name="Sarthi_Specs.pdf",
                document_type="vessel_specification",
                relevance_score=0.92,
                excerpt="Specifications for ICGS Sarthi",
                vessel_name="ICGS Sarthi"
            )
        ],
        similar_drawings=[
            SearchResult(
                document_id="2",
                document_name="Sarthi_Hull_R1.pdf",
                document_type="blueprint",
                relevance_score=0.85,
                excerpt="Previous revision"
            ),
            SearchResult(
                document_id="3",
                document_name="Sarthi_Hull_R2.pdf",
                document_type="blueprint",
                relevance_score=0.80,
                excerpt="Another revision"
            )
        ],
        matching_parts=[],
        related_sotrs=[
            SearchResult(
                document_id="4",
                document_name="OPV_SOTR_v2.3.pdf",
                document_type="sotr",
                relevance_score=0.75,
                excerpt="OPV technical requirements"
            )
        ],
        raw_context_text="Test context",
        total_sources=4,
        highest_relevance=0.92
    )
    
    print("\nTest: Generate Suggestions")
    suggestion_set = generate_suggestions(
        test_drawing,
        test_context,
        "analyze this drawing",
        0.88,
        use_llm_enhancement=False
    )
    
    print(f"  Total suggestions: {suggestion_set.total_suggestions}")
    print(f"  High priority: {suggestion_set.high_priority_count}")
    print(f"  Overall confidence: {suggestion_set.overall_confidence}")
    print(f"  Summary: {suggestion_set.summary}")
    
    print("\nSuggestions:")
    for i, sug in enumerate(suggestion_set.suggestions[:3], 1):
        print(f"  {i}. [{sug.type.value}] {sug.title}")
        print(f"     Priority: {sug.priority}, Confidence: {sug.confidence:.0%}")
    
    print("\n" + "=" * 50)
    print("Suggestion Engine Ready")

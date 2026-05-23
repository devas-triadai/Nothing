"""
AGRA Compliance Module Phase 2 — SOTR Parser & Clause Extractor
Extracts structured clauses from Statement of Technical Requirements documents.

Capabilities:
- Detect SOTR document type using existing classifier
- Extract numbered clauses (1.1, 1.2, 2.1, etc.)
- Parse clause categories (Technical, Commercial, Safety)
- Identify mandatory vs optional requirements
- Extract acceptance criteria
"""

import re
import logging
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum

from api.models.compliance_models import ClauseCategory, ComplianceClauseBase
from api.rag.drawing_classifier import classify_tier1

logger = logging.getLogger("agra.sotr_parser")


# ═══════════════════════════════════════════════════════════════
#  SOTR DETECTION PATTERNS
# ═══════════════════════════════════════════════════════════════

_SOTR_INDICATORS = [
    r"(?i)statement\s+of\s+technical\s+requirements",
    r"(?i)\bsotr\b",
    r"(?i)technical\s+requirements",
    r"(?i)technical\s+specification",
    r"(?i)scope\s+of\s+supply",
    r"(?i)general\s+requirements",
]

_CLAUSE_NUMBER_PATTERNS = [
    # Standard numbered clauses: 1.1, 1.2.1, 2.1, etc.
    r"^\s*(\d+(?:\.\d+)*)\s*[.:-]?\s*",
    # Alternative: (1), (1.1), (a), (i)
    r"^\s*\((\d+(?:\.\d+)*|[a-z])\)\s*",
]

_CATEGORY_KEYWORDS = {
    ClauseCategory.TECHNICAL: [
        "technical", "specification", "hull", "machinery", "electrical",
        "propulsion", "navigation", "communication", "hull construction",
        "steel", "welding", "equipment", "system", "design", "material"
    ],
    ClauseCategory.COMMERCIAL: [
        "commercial", "price", "cost", "payment", "delivery", "schedule",
        "warranty", "guarantee", "penalty", "liquidated", "damages",
        "contract", "terms", "conditions", "bid", "tender"
    ],
    ClauseCategory.SAFETY: [
        "safety", "fire", "lifesaving", "rescue", "emergency", "alarm",
        "detection", "extinguishing", "collision", "avoidance", "survival",
        "protection", "hazard", "risk"
    ],
    ClauseCategory.QUALITY: [
        "quality", "inspection", "survey", "testing", "commissioning",
        "approval", "certification", "class", "verification", "validation",
        "standard", "iso", "irs", "dnv", "abs"
    ],
    ClauseCategory.ENVIRONMENTAL: [
        "environment", "pollution", "marpol", "emission", "waste",
        "effluent", "ballast", "bilge", "sewage", "garbage", "oil"
    ],
    ClauseCategory.GENERAL: [
        "general", "introduction", "scope", "definition", "abbreviation",
        "reference", "document", "applicable", "regulation", "rule"
    ],
}

_MANDATORY_KEYWORDS = [
    "shall", "must", "required", "mandatory", "compulsory",
    "necessary", "essential", "obligation", "obligate"
]

_OPTIONAL_KEYWORDS = [
    "may", "can", "optional", "if required", "if requested",
    "at the discretion", "if deemed", "as applicable"
]

_ACCEPTANCE_CRITERIA_PATTERNS = [
    r"(?i)acceptance\s*(?:criteria|standard)s?\s*[:=]\s*(.+?)(?:\n|$)",
    r"(?i)shall\s+be\s+accepted\s+when\s*[:=]\s*(.+?)(?:\n|$)",
    r"(?i)compliance\s*(?:with|to)\s*[:=]\s*(.+?)(?:\n|$)",
    r"(?i)shall\s+comply\s+with\s*(.+?)(?:\n|$)",
    r"(?i)conformance\s*(?:with|to)\s*[:=]\s*(.+?)(?:\n|$)",
]


# ═══════════════════════════════════════════════════════════════
#  DATA CLASSES
# ═══════════════════════════════════════════════════════════════

@dataclass
class ParsedClause:
    """Internal representation of a parsed clause."""
    clause_number: str
    clause_title: Optional[str]
    clause_text: str
    category: ClauseCategory
    is_mandatory: bool
    is_critical: bool
    acceptance_criteria: Optional[str]
    raw_text: str  # Original text including number


# ═══════════════════════════════════════════════════════════════
#  SOTR DETECTION
# ═══════════════════════════════════════════════════════════════

def is_sotr_document(filename: str, content_preview: str = "") -> Tuple[bool, float]:
    """
    Detect if document is likely an SOTR.
    
    Returns:
        (is_sotr, confidence)
    """
    confidence = 0.0
    
    # Check filename patterns
    for pattern in _SOTR_INDICATORS:
        if re.search(pattern, filename, re.IGNORECASE):
            confidence += 0.30
    
    # Check content patterns
    if content_preview:
        for pattern in _SOTR_INDICATORS:
            if re.search(pattern, content_preview[:2000], re.IGNORECASE):
                confidence += 0.40
    
    # Use existing classifier as fallback
    classification = classify_tier1(filename, content_preview[:500])
    if classification["drawing_type"].value == "standard":
        confidence += 0.20
    
    # Check for clause structure
    if content_preview:
        clause_matches = len(re.findall(r"^\s*\d+\.\d+", content_preview[:3000], re.MULTILINE))
        if clause_matches >= 3:
            confidence += 0.10
    
    is_sotr = confidence >= 0.50
    return is_sotr, min(confidence, 0.95)


def detect_sotr_in_text(text: str) -> Dict[str, Any]:
    """
    Analyze text to detect SOTR characteristics.
    
    Returns dict with detection results.
    """
    indicators_found = []
    
    for pattern in _SOTR_INDICATORS:
        matches = re.findall(pattern, text[:5000], re.IGNORECASE)
        if matches:
            indicators_found.extend(matches)
    
    # Check for clause numbering structure
    clause_pattern = r"^\s*(\d+(?:\.\d+){0,2})\s*[.:-]\s*(.+)$"
    clause_matches = re.findall(clause_pattern, text[:5000], re.MULTILINE)
    
    return {
        "is_likely_sotr": len(indicators_found) > 0 or len(clause_matches) >= 3,
        "confidence": min(len(indicators_found) * 0.2 + len(clause_matches) * 0.1, 0.9),
        "indicators_found": list(set(indicators_found)),
        "clause_count": len(clause_matches),
        "sample_clauses": clause_matches[:5] if clause_matches else []
    }


# ═══════════════════════════════════════════════════════════════
#  CLAUSE EXTRACTION
# ═══════════════════════════════════════════════════════════════

def extract_clauses(text: str) -> List[ParsedClause]:
    """
    Extract all numbered clauses from SOTR text.
    
    Args:
        text: Full SOTR document text
        
    Returns:
        List of ParsedClause objects
    """
    clauses = []
    
    # Normalize text
    text = _normalize_text(text)
    
    # Find all clause boundaries
    clause_positions = _find_clause_boundaries(text)
    
    for i, (start_pos, end_pos) in enumerate(clause_positions):
        clause_text = text[start_pos:end_pos].strip()
        
        if not clause_text:
            continue
        
        # Parse clause components
        clause_number = _extract_clause_number(clause_text)
        if not clause_number:
            continue
        
        clause_title = _extract_clause_title(clause_text)
        clean_text = _clean_clause_text(clause_text, clause_number, clause_title)
        
        category = _detect_category(clean_text, clause_title or "")
        is_mandatory = _detect_mandatory(clean_text)
        is_critical = _detect_critical(clean_text, category)
        acceptance_criteria = _extract_acceptance_criteria(clean_text)
        
        clauses.append(ParsedClause(
            clause_number=clause_number,
            clause_title=clause_title,
            clause_text=clean_text,
            category=category,
            is_mandatory=is_mandatory,
            is_critical=is_critical,
            acceptance_criteria=acceptance_criteria,
            raw_text=clause_text
        ))
    
    # Sort by clause number
    clauses.sort(key=lambda c: _clause_number_sort_key(c.clause_number))
    
    logger.info(f"Extracted {len(clauses)} clauses from SOTR text")
    return clauses


def _normalize_text(text: str) -> str:
    """Normalize text for parsing."""
    # Convert multiple spaces to single
    text = re.sub(r' +', ' ', text)
    # Ensure proper spacing around newlines
    text = re.sub(r'\n\s*\n+', '\n\n', text)
    return text


def _find_clause_boundaries(text: str) -> List[Tuple[int, int]]:
    """
    Find start and end positions of each clause in text.
    
    Returns list of (start, end) tuples.
    """
    boundaries = []
    
    # Pattern to match clause numbers at line start
    clause_start_pattern = r'(?:^|\n)\s*(\d+(?:\.\d+){0,2})\s*[.:-]\s*'
    
    matches = list(re.finditer(clause_start_pattern, text))
    
    for i, match in enumerate(matches):
        start = match.start()
        
        # End is either start of next clause or end of text
        if i < len(matches) - 1:
            end = matches[i + 1].start()
        else:
            end = len(text)
        
        boundaries.append((start, end))
    
    return boundaries


def _extract_clause_number(text: str) -> Optional[str]:
    """Extract clause number from clause text."""
    # Match at start of text
    match = re.match(r'\s*(\d+(?:\.\d+)*)\s*[.:-]?\s*', text)
    if match:
        return match.group(1)
    return None


def _extract_clause_title(text: str) -> Optional[str]:
    """Extract clause title from clause text."""
    # Remove clause number
    text_no_number = re.sub(r'^\s*\d+(?:\.\d+)*\s*[.:-]?\s*', '', text)
    
    # Look for title patterns
    # Pattern 1: Title in ALL CAPS or Title Case followed by newline
    title_match = re.match(r'^([A-Z][A-Za-z\s&-]{2,50}?)(?:\n|:\s)', text_no_number)
    if title_match:
        return title_match.group(1).strip()
    
    # Pattern 2: Short phrase before long text
    lines = text_no_number.split('\n')
    if lines:
        first_line = lines[0].strip()
        if 5 <= len(first_line) <= 100 and first_line[0].isupper():
            # Check if it looks like a title (not a full sentence)
            if not first_line.endswith('.') or len(first_line) < 60:
                return first_line
    
    return None


def _clean_clause_text(text: str, clause_number: str, title: Optional[str]) -> str:
    """Clean clause text by removing number and title."""
    # Remove clause number
    text = re.sub(r'^\s*' + re.escape(clause_number) + r'\s*[.:-]?\s*', '', text)
    
    # Remove title if found
    if title:
        text = re.sub(r'^' + re.escape(title) + r'\s*:?\s*', '', text)
    
    return text.strip()


def _detect_category(text: str, title: str) -> ClauseCategory:
    """Detect clause category based on keywords."""
    combined_text = (title + " " + text).lower()
    
    scores = {}
    for category, keywords in _CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in combined_text)
        scores[category] = score
    
    # Return category with highest score, default to GENERAL
    if max(scores.values()) > 0:
        return max(scores, key=scores.get)
    
    return ClauseCategory.GENERAL


def _detect_mandatory(text: str) -> bool:
    """Detect if clause is mandatory based on language."""
    text_lower = text.lower()
    
    mandatory_count = sum(1 for kw in _MANDATORY_KEYWORDS if kw in text_lower)
    optional_count = sum(1 for kw in _OPTIONAL_KEYWORDS if kw in text_lower)
    
    # Default to mandatory if unclear
    if mandatory_count == 0 and optional_count == 0:
        return True
    
    return mandatory_count > optional_count


def _detect_critical(text: str, category: ClauseCategory) -> bool:
    """Detect if clause is critical to safety/operation."""
    text_lower = text.lower()
    
    # Safety clauses are always critical
    if category == ClauseCategory.SAFETY:
        return True
    
    # Check for critical keywords
    critical_keywords = [
        "safety", "critical", "essential", "vital", "life-saving",
        "primary", "main", "hull integrity", "watertight", "structural"
    ]
    
    return any(kw in text_lower for kw in critical_keywords)


def _extract_acceptance_criteria(text: str) -> Optional[str]:
    """Extract acceptance criteria from clause text."""
    for pattern in _ACCEPTANCE_CRITERIA_PATTERNS:
        match = re.search(pattern, text)
        if match:
            criteria = match.group(1).strip()
            # Limit length
            if len(criteria) > 200:
                criteria = criteria[:200] + "..."
            return criteria
    
    return None


def _clause_number_sort_key(clause_number: str) -> List[int]:
    """Convert clause number to sortable tuple."""
    parts = clause_number.split('.')
    return [int(p) for p in parts]


# ═══════════════════════════════════════════════════════════════
#  OUTPUT CONVERSION
# ═══════════════════════════════════════════════════════════════

def parsed_clause_to_base_model(parsed: ParsedClause, sotr_doc_id: int) -> ComplianceClauseBase:
    """Convert ParsedClause to ComplianceClauseBase Pydantic model."""
    return ComplianceClauseBase(
        clause_number=parsed.clause_number,
        clause_title=parsed.clause_title,
        clause_text=parsed.clause_text,
        category=parsed.category,
        is_mandatory=parsed.is_mandatory,
        is_critical=parsed.is_critical,
        acceptance_criteria=parsed.acceptance_criteria
    )


def extract_clauses_to_models(text: str, sotr_doc_id: int) -> List[ComplianceClauseBase]:
    """
    Extract clauses and convert directly to Pydantic models.
    
    Args:
        text: SOTR document text
        sotr_doc_id: Document ID for reference
        
    Returns:
        List of ComplianceClauseBase models
    """
    parsed_clauses = extract_clauses(text)
    return [
        parsed_clause_to_base_model(pc, sotr_doc_id)
        for pc in parsed_clauses
    ]


# ═══════════════════════════════════════════════════════════════
#  MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════

def parse_sotr_document(
    text: str,
    filename: str = "",
    sotr_doc_id: int = 0
) -> Dict[str, Any]:
    """
    Main entry point for SOTR document parsing.
    
    Args:
        text: Full document text
        filename: Original filename (for detection)
        sotr_doc_id: Document ID
        
    Returns:
        Dict with detection results, clauses, and metadata
    """
    # Detect if this is an SOTR
    is_sotr, confidence = is_sotr_document(filename, text[:1000])
    
    if not is_sotr:
        detection = detect_sotr_in_text(text)
        return {
            "is_sotr": False,
            "confidence": detection["confidence"],
            "reason": "Document does not match SOTR patterns",
            "indicators_found": detection["indicators_found"],
            "suggested_action": "Verify document type or use manual clause extraction"
        }
    
    # Extract clauses
    parsed_clauses = extract_clauses(text)
    
    # Convert to models
    clause_models = [
        parsed_clause_to_base_model(pc, sotr_doc_id)
        for pc in parsed_clauses
    ]
    
    # Calculate statistics
    categories = {}
    mandatory_count = 0
    critical_count = 0
    
    for pc in parsed_clauses:
        cat = pc.category.value
        categories[cat] = categories.get(cat, 0) + 1
        if pc.is_mandatory:
            mandatory_count += 1
        if pc.is_critical:
            critical_count += 1
    
    return {
        "is_sotr": True,
        "confidence": confidence,
        "sotr_doc_id": sotr_doc_id,
        "filename": filename,
        "total_clauses": len(clause_models),
        "categories": categories,
        "mandatory_count": mandatory_count,
        "critical_count": critical_count,
        "clauses": clause_models
    }


# ═══════════════════════════════════════════════════════════════
#  TESTING
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Test with sample SOTR text
    sample_text = """
1. GENERAL REQUIREMENTS

1.1 Scope of Supply
The Vendor shall supply and deliver one (1) Offshore Patrol Vessel (OPV) 
as per the specifications herein. The vessel shall comply with IRS Rules 
and Regulations.

1.2 Technical Specifications
1.2.1 Hull Construction
The hull shall be constructed of steel to IRS Grade A and AH36. 
All welding shall be in accordance with IRS welding regulations.
Acceptance criteria: IRS Class approval certificate.

1.2.2 Main Propulsion
The main propulsion system shall consist of two (2) diesel engines 
with a combined output of not less than 8000 kW. The engines shall 
be IMO Tier III compliant.

2. COMMERCIAL TERMS

2.1 Delivery Schedule
The vessel shall be delivered within 24 months from contract signing.
Delivery shall be at Vendor's shipyard.

2.2 Warranty Period
The Vendor shall provide a warranty period of 12 months from delivery.
"""
    
    result = parse_sotr_document(sample_text, "SOTR_OPV_001.pdf", 123)
    
    print("SOTR Parser Test Results:")
    print("=" * 60)
    print(f"Is SOTR: {result['is_sotr']}")
    print(f"Confidence: {result['confidence']:.2%}")
    print(f"Total Clauses: {result['total_clauses']}")
    print(f"Categories: {result['categories']}")
    print(f"Mandatory: {result['mandatory_count']}")
    print(f"Critical: {result['critical_count']}")
    print("\nExtracted Clauses:")
    for clause in result['clauses'][:5]:
        print(f"  {clause.clause_number}: {clause.clause_title or 'Untitled'}")
        print(f"    Category: {clause.category.value}")
        print(f"    Mandatory: {clause.is_mandatory}, Critical: {clause.is_critical}")
        if clause.acceptance_criteria:
            print(f"    Criteria: {clause.acceptance_criteria}")

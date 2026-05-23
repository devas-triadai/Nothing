"""
AGRA Module 2 — Citation Validator
Validates that citations in LLM responses match the provided sources.
"""

import re
from typing import List, Dict, Any, Tuple
import logging

logger = logging.getLogger("agra.citation_validator")


def extract_citations(text: str) -> List[Dict[str, Any]]:
    """
    Extract citation markers [N] from text.
    
    Returns list of dicts:
    - citation_num: The citation number (e.g., 1, 2, 3)
    - position: Character position in text
    - surrounding_text: Text around the citation (for context)
    """
    citations = []
    
    # Pattern: [1], [2], [12], etc. followed by word characters or end of text
    pattern = r'\[(\d+)\]'
    
    for match in re.finditer(pattern, text):
        citation_num = int(match.group(1))
        position = match.start()
        
        # Get surrounding text (100 chars before and after)
        start = max(0, position - 100)
        end = min(len(text), position + 100)
        surrounding = text[start:end].replace('\n', ' ')
        
        # Extract the claim (sentence containing the citation)
        # Look for sentence boundaries
        sent_start = text.rfind('.', 0, position)
        if sent_start == -1:
            sent_start = 0
        else:
            sent_start += 1
            
        sent_end = text.find('.', position)
        if sent_end == -1:
            sent_end = len(text)
        else:
            sent_end += 1
        
        claim = text[sent_start:sent_end].strip()
        
        citations.append({
            "citation_num": citation_num,
            "position": position,
            "surrounding_text": surrounding,
            "claim": claim,
        })
    
    return citations


def validate_citations_against_sources(
    response_text: str,
    sources: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Validate all citations in response against provided sources.
    
    Args:
        response_text: The LLM-generated response
        sources: List of source dicts with 'index' key matching citation numbers
    
    Returns:
        Dict with validation results:
        - total_citations: Total number of citation markers found
        - valid_citations: Citations that match a source
        - invalid_citations: Citations that don't match any source
        - unverified_claims: Claims without any citation
        - citation_accuracy: Percentage of valid citations
        - details: List of per-citation validation results
    """
    # Build source lookup by index
    source_lookup = {}
    for source in sources:
        idx = source.get("index")
        if idx is not None:
            source_lookup[idx] = source
    
    # Extract citations
    citations = extract_citations(response_text)
    
    if not citations:
        return {
            "total_citations": 0,
            "valid_citations": 0,
            "invalid_citations": 0,
            "unverified_claims": 0,  # Can't determine without citations
            "citation_accuracy": 100.0,  # Vacuously accurate
            "details": [],
            "warnings": ["No citations found in response"],
        }
    
    # Validate each citation
    valid_count = 0
    invalid_count = 0
    details = []
    
    for cit in citations:
        citation_num = cit["citation_num"]
        
        if citation_num in source_lookup:
            source = source_lookup[citation_num]
            valid_count += 1
            details.append({
                "citation_num": citation_num,
                "valid": True,
                "source_document": source.get("document", "Unknown"),
                "source_page": source.get("page", "?"),
                "claim": cit["claim"],
            })
        else:
            invalid_count += 1
            details.append({
                "citation_num": citation_num,
                "valid": False,
                "error": f"Citation [{citation_num}] does not match any source",
                "claim": cit["claim"],
            })
    
    # Count unique citations (avoid double-counting same citation used multiple times)
    unique_citation_nums = set(c["citation_num"] for c in citations)
    total_unique = len(unique_citation_nums)
    
    # Calculate accuracy
    if total_unique > 0:
        accuracy = (valid_count / total_unique) * 100.0
    else:
        accuracy = 100.0
    
    # Detect unverified claims (sentences without citations)
    # Split into sentences and check for citations
    sentences = re.split(r'(?<=[.!?])\s+', response_text)
    unverified = 0
    
    for sent in sentences:
        sent = sent.strip()
        if len(sent) > 20:  # Meaningful sentence
            if not re.search(r'\[\d+\]', sent):
                # Check if it's a factual claim (not a transition phrase)
                non_factual_starts = [
                    "however", "therefore", "in conclusion", "furthermore",
                    "additionally", "moreover", "consequently", "nevertheless",
                    "in summary", "to summarize", "note that", "please note"
                ]
                sent_lower = sent.lower()
                if not any(sent_lower.startswith(phrase) for phrase in non_factual_starts):
                    unverified += 1
    
    return {
        "total_citations": total_unique,
        "valid_citations": valid_count,
        "invalid_citations": invalid_count,
        "unverified_claims": unverified,
        "citation_accuracy": accuracy,
        "details": details,
        "warnings": [d["error"] for d in details if not d["valid"]],
    }


def format_validation_report(validation_result: Dict[str, Any]) -> str:
    """
    Format validation results as a human-readable report.
    """
    lines = [
        "=== Citation Validation Report ===",
        f"Total citations: {validation_result['total_citations']}",
        f"Valid citations: {validation_result['valid_citations']}",
        f"Invalid citations: {validation_result['invalid_citations']}",
        f"Unverified claims: {validation_result['unverified_claims']}",
        f"Citation accuracy: {validation_result['citation_accuracy']:.1f}%",
        "",
    ]
    
    if validation_result["warnings"]:
        lines.append("Warnings:")
        for warning in validation_result["warnings"]:
            lines.append(f"  - {warning}")
    
    if validation_result["details"]:
        lines.extend(["", "Details:"])
        for detail in validation_result["details"]:
            status = "✓" if detail["valid"] else "✗"
            lines.append(f"  [{status}] [{detail['citation_num']}] {detail.get('source_document', 'Unknown')}")
    
    return "\n".join(lines)

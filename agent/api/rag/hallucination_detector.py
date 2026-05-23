"""
AGRA Module 2 — Hallucination Detector
Detects unsupported claims in LLM responses using claim extraction and source verification.
"""

import re
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger("agra.hallucination_detector")


def extract_claims(text: str) -> List[Dict[str, Any]]:
    """
    Extract factual claims from text.
    
    Simple approach: Extract sentences that appear to be factual assertions.
    More sophisticated approaches could use NER or dependency parsing.
    
    Returns list of dicts with:
    - claim_text: The extracted claim
    - position: Character position
    - has_citation: Whether claim has a citation
    - citation_nums: List of citation numbers if any
    """
    claims = []
    
    # Split into sentences
    sentences = re.split(r'(?<=[.!?])\s+', text)
    
    # Filter out non-factual sentences
    non_factual_patterns = [
        r'^(however|therefore|in conclusion|furthermore|additionally|moreover|consequently|nevertheless|in summary|to summarize)\b',
        r'^(note that|please note|as mentioned|as discussed)\b',
        r'^(if you|would you|could you|please)\b',  # Questions/requests
        r'^(i am|i will|we can|let me)\b',  # First person meta-text
    ]
    
    position = 0
    for sent in sentences:
        sent = sent.strip()
        if len(sent) < 20:  # Skip very short fragments
            position += len(sent) + 1
            continue
        
        # Check if non-factual
        is_non_factual = any(re.search(pattern, sent, re.IGNORECASE) for pattern in non_factual_patterns)
        if is_non_factual:
            position += len(sent) + 1
            continue
        
        # Check for citations
        citation_matches = re.findall(r'\[(\d+)\]', sent)
        has_citation = len(citation_matches) > 0
        
        claims.append({
            "claim_text": sent,
            "position": position,
            "has_citation": has_citation,
            "citation_nums": [int(m) for m in citation_matches] if citation_matches else [],
        })
        
        position += len(sent) + 1
    
    return claims


def verify_claim_against_source(claim: str, source_text: str) -> str:
    """
    Verify if a claim is supported by source text.
    
    Simple heuristic-based verification:
    - Check for exact phrase matches
    - Check for keyword overlap
    
    Returns: "supported", "contradicted", or "unsupported"
    
    Note: This is a simplified version. A production system would use:
    - NLI (Natural Language Inference) model
    - Semantic similarity
    - LLM-based entailment checking
    """
    claim_lower = claim.lower()
    source_lower = source_text.lower()
    
    # Clean claim for matching
    claim_clean = re.sub(r'\[\d+\]', '', claim_lower)  # Remove citations
    claim_clean = re.sub(r'[^\w\s]', ' ', claim_clean)  # Remove punctuation
    claim_clean = ' '.join(claim_clean.split())  # Normalize whitespace
    
    # Exact or near-exact match
    if claim_clean in source_lower:
        return "supported"
    
    # Extract key terms (nouns, numbers, technical terms)
    # Simple approach: words > 5 chars or containing numbers
    key_terms = []
    for word in claim_clean.split():
        if len(word) > 5 or re.search(r'\d', word):
            key_terms.append(word)
    
    if not key_terms:
        return "unsupported"  # Can't verify without key terms
    
    # Check if key terms appear in source
    matches = sum(1 for term in key_terms if term in source_lower)
    match_ratio = matches / len(key_terms)
    
    # Heuristic thresholds
    if match_ratio >= 0.7:
        return "supported"
    elif match_ratio >= 0.3:
        return "partial"  # Partial support
    else:
        return "unsupported"


def detect_hallucinations(
    response_text: str,
    sources: List[Dict[str, Any]],
    validation_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Detect hallucinations in LLM response.
    
    Args:
        response_text: The LLM-generated response
        sources: List of source dicts with 'index' and 'excerpt' keys
        validation_result: Optional pre-computed citation validation
    
    Returns:
        Dict with hallucination detection results:
        - total_claims: Total number of claims extracted
        - supported_claims: Claims verified against sources
        - unsupported_claims: Claims not found in sources (hallucinations)
        - contradicted_claims: Claims contradicted by sources
        - hallucination_rate: Percentage of unsupported claims
        - details: Per-claim verification results
    """
    # Extract claims
    claims = extract_claims(response_text)
    
    if not claims:
        return {
            "total_claims": 0,
            "supported_claims": 0,
            "unsupported_claims": 0,
            "contradicted_claims": 0,
            "hallucination_rate": 0.0,
            "details": [],
        }
    
    # Build source lookup
    source_lookup = {}
    for source in sources:
        idx = source.get("index")
        if idx is not None:
            source_lookup[idx] = source.get("excerpt", "")
    
    # Verify each claim
    supported = 0
    unsupported = 0
    contradicted = 0
    partial = 0
    details = []
    
    for claim in claims:
        claim_text = claim["claim_text"]
        citation_nums = claim["citation_nums"]
        
        # If claim has no citations, it's unverified (potential hallucination)
        if not citation_nums:
            unsupported += 1
            details.append({
                "claim": claim_text[:200],
                "status": "unverified",
                "reason": "No citation provided",
            })
            continue
        
        # Verify against cited sources
        verifications = []
        for citation_num in citation_nums:
            source_text = source_lookup.get(citation_num, "")
            if source_text:
                result = verify_claim_against_source(claim_text, source_text)
                verifications.append(result)
        
        # Determine overall status
        if verifications:
            if "contradicted" in verifications:
                contradicted += 1
                status = "contradicted"
            elif "supported" in verifications:
                supported += 1
                status = "supported"
            elif "partial" in verifications:
                partial += 1
                status = "partial"
            else:
                unsupported += 1
                status = "unsupported"
        else:
            # Citations don't exist (invalid citations)
            unsupported += 1
            status = "unsupported"
        
        details.append({
            "claim": claim_text[:200],
            "citations": citation_nums,
            "status": status,
        })
    
    # Calculate hallucination rate
    # Count unsupported + unverified as hallucinations
    total_hallucinations = unsupported
    total_verifiable = len(claims)
    
    if total_verifiable > 0:
        hallucination_rate = (total_hallucinations / total_verifiable) * 100.0
    else:
        hallucination_rate = 0.0
    
    return {
        "total_claims": len(claims),
        "supported_claims": supported,
        "partially_supported_claims": partial,
        "unsupported_claims": unsupported,
        "contradicted_claims": contradicted,
        "hallucination_rate": hallucination_rate,
        "details": details,
    }


def format_hallucination_report(detection_result: Dict[str, Any]) -> str:
    """
    Format hallucination detection results as a human-readable report.
    """
    lines = [
        "=== Hallucination Detection Report ===",
        f"Total claims: {detection_result['total_claims']}",
        f"Supported: {detection_result['supported_claims']}",
        f"Partially supported: {detection_result.get('partially_supported_claims', 0)}",
        f"Unsupported: {detection_result['unsupported_claims']}",
        f"Contradicted: {detection_result['contradicted_claims']}",
        f"Hallucination rate: {detection_result['hallucination_rate']:.1f}%",
        "",
    ]
    
    # Show problematic claims
    problematic = [d for d in detection_result["details"] if d["status"] in ("unsupported", "unverified", "contradicted")]
    
    if problematic:
        lines.append("Potentially Hallucinated Claims:")
        for detail in problematic[:5]:  # Show top 5
            status_icon = "✗" if detail["status"] == "contradicted" else "?"
            lines.append(f"  [{status_icon}] {detail['status'].upper()}: {detail['claim'][:100]}...")
    
    return "\n".join(lines)

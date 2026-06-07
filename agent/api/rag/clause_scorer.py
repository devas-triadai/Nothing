"""
AGRA Compliance Module Phase 3 — Clause Scoring Engine
LLM-based comparison of vendor submission against SOTR clauses.

Scoring Logic:
1. For each SOTR clause, find relevant vendor text via RAG
2. LLM compares vendor response against acceptance criteria
3. Score: Compliant/Partial/Non-Compliant/Not Applicable
4. Confidence score based on evidence strength
"""

import re
import json
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

from api.models.compliance_models import (
    ClauseStatus, ComplianceClauseBase, ClauseScoreBase,
    ComplianceEvaluationResponse
)
from api.rag import llm as llm_engine
from api.rag.vector_store import get_store

logger = logging.getLogger("agra.clause_scorer")


# ═══════════════════════════════════════════════════════════════
#  LLM PROMPT TEMPLATES
# ═══════════════════════════════════════════════════════════════

_CLAUSE_SCORING_PROMPT = """You are a compliance officer for the Indian Coast Guard evaluating vendor submissions against SOTR requirements and database reference standards.

SOTR CLAUSE:
Number: {clause_number}
Title: {clause_title}
Requirement: {clause_text}
Category: {category}
Mandatory: {is_mandatory}
Critical: {is_critical}
Acceptance Criteria: {acceptance_criteria}

APPLICABLE STANDARDS (from database):
{standards_text}

VENDOR SUBMISSION (relevant excerpts):
{vendor_text}

Evaluate if the vendor submission meets this requirement and complies with the database reference standards.

Return ONLY valid JSON in this exact format:
{{
  "status": "compliant|partial|non_compliant|not_applicable",
  "confidence": 0.0-1.0,
  "vendor_response_summary": "brief summary of what vendor said",
  "evidence": "exact text from vendor submission supporting this score",
  "gaps": "missing elements or deviations if any",
  "recommendation": "accept|conditional|reject|review"
}}

Scoring Guidelines:
- COMPLIANT: Vendor fully meets all acceptance criteria with clear evidence
- PARTIAL: Vendor meets some criteria but has minor gaps or conditions
- NON_COMPLIANT: Vendor does not meet criteria or has significant deviations
- NOT_APPLICABLE: This clause doesn't apply to this vendor's scope

Confidence Guidelines:
- 0.9-1.0: Direct explicit reference with complete evidence
- 0.7-0.9: Clear implicit compliance with good evidence
- 0.5-0.7: Partial evidence or qualified response
- 0.3-0.5: Weak evidence or unclear response
- 0.0-0.3: No evidence or non-response"""


_BATCH_CLAUSE_PROMPT = """You are a compliance officer evaluating multiple SOTR clauses against a vendor submission.

VENDOR SUBMISSION (full text):
{vendor_full_text}

Evaluate each clause below and return a JSON array of results.

CLAUSES TO EVALUATE:
{clauses_text}

Return ONLY valid JSON array where each element matches:
{{
  "clause_number": "1.1",
  "status": "compliant|partial|non_compliant|not_applicable",
  "confidence": 0.0-1.0,
  "vendor_response_summary": "brief summary",
  "evidence": "supporting text",
  "gaps": "missing elements"
}}"""


# ═══════════════════════════════════════════════════════════════
#  DATA CLASSES
# ═══════════════════════════════════════════════════════════════

@dataclass
class ScoringResult:
    """Internal scoring result before conversion to model."""
    clause_number: str
    status: ClauseStatus
    confidence: float
    vendor_response_summary: str
    evidence_text: str
    gaps_identified: Optional[str]
    recommendation: str
    llm_raw_response: str


# ═══════════════════════════════════════════════════════════════
#  VENDOR TEXT RETRIEVAL
# ═══════════════════════════════════════════════════════════════

def check_speed_compliance(text: str) -> Optional[Tuple[float, str]]:
    """
    Check if the text specifies a vessel speed exceeding the Indian Coast Guard (ICG) limit of 50.0 knots.
    Returns (speed_value, matched_text) if a violation is found, else None.
    """
    if not text:
        return None
    # Match numbers (integers or decimals) followed by knots, kts, or knot
    pattern = re.compile(r'\b(\d+(?:\.\d+)?)\s*(?:knots|kts|knot)\b', re.IGNORECASE)
    for match in pattern.finditer(text):
        try:
            val = float(match.group(1))
            if val > 50.0:
                return val, match.group(0)
        except ValueError:
            continue
    return None


def find_relevant_vendor_text(
    clause: ComplianceClauseBase,
    vendor_doc_id: str,
    vendor_doc_ids: Optional[List[str]] = None,
    standard_doc_ids: Optional[List[str]] = None,
    max_chunks: int = 5
) -> Tuple[str, List[str], str]:
    """
    Find relevant text from vendor document and reference standards for a clause.
    
    Uses RAG to retrieve chunks that match the clause requirements.
    
    Args:
        clause: The SOTR clause to match against
        vendor_doc_id: Document ID of vendor submission
        vendor_doc_ids: Optional list of all vendor document IDs
        standard_doc_ids: Optional list of standard document IDs
        max_chunks: Maximum chunks to retrieve
        
    Returns:
        (combined_vendor_text, chunk_ids, combined_standards_text)
    """
    combined = ""
    chunk_ids = []
    standards_text = ""
    try:
        store = get_store()
        
        # Build search query from clause
        search_terms = f"{clause.clause_title or ''} {clause.clause_text}"
        if clause.acceptance_criteria:
            search_terms += f" {clause.acceptance_criteria}"
        
        # Search vendor documents
        filter_vendor_ids = vendor_doc_ids if vendor_doc_ids else ([vendor_doc_id] if vendor_doc_id else [])
        if filter_vendor_ids:
            results = store.search(
                query=search_terms,
                top_k=max_chunks,
                doc_filter=filter_vendor_ids
            )
            if results:
                texts = []
                for result in results:
                    chunk_text = result.get("text", "")
                    chunk_id = result.get("chunk_id", "")
                    if chunk_text:
                        texts.append(chunk_text)
                        chunk_ids.append(chunk_id)
                combined = "\n\n---\n\n".join(texts)
        
        # Search standard documents
        if standard_doc_ids:
            std_results = store.search(
                query=search_terms,
                top_k=max_chunks,
                doc_filter=standard_doc_ids
            )
            if std_results:
                std_texts = []
                for r in std_results:
                    txt = r.get("text", "")
                    if txt:
                        fname = r.get("metadata", {}).get("filename", "Standard")
                        std_texts.append(f"[{fname}]: {txt}")
                standards_text = "\n\n---\n\n".join(std_texts)
        
    except Exception as e:
        logger.warning(f"Failed to retrieve vendor/standards text for clause {clause.clause_number}: {e}")
        
    return combined, chunk_ids, standards_text


def find_all_vendor_text(vendor_doc_id: str) -> str:
    """
    Retrieve all text from vendor document.
    Use for batch processing when clause-specific search fails.
    """
    try:
        store = get_store()
        chunks = store.get_chunks_by_doc(vendor_doc_id)
        
        texts = [c.get("text", "") for c in chunks if c.get("text")]
        return "\n\n".join(texts[:50])  # Limit to first 50 chunks
    
    except Exception as e:
        logger.error(f"Failed to retrieve all vendor text: {e}")
        return ""


# ═══════════════════════════════════════════════════════════════
#  LLM SCORING
# ═══════════════════════════════════════════════════════════════

def score_single_clause(
    clause: ComplianceClauseBase,
    vendor_text: str,
    standards_text: str = "",
    use_batch: bool = False
) -> ScoringResult:
    """
    Score a single clause using LLM.
    
    Args:
        clause: The SOTR clause
        vendor_text: Relevant text from vendor submission
        standards_text: Reference standard text
        use_batch: If True, uses batch-optimized prompt
        
    Returns:
        ScoringResult with status, confidence, and analysis
    """
    # Build prompt
    prompt = _CLAUSE_SCORING_PROMPT.format(
        clause_number=clause.clause_number,
        clause_title=clause.clause_title or "Untitled",
        clause_text=clause.clause_text,
        category=clause.category.value,
        is_mandatory="Yes" if clause.is_mandatory else "No",
        is_critical="Yes" if clause.is_critical else "No",
        acceptance_criteria=clause.acceptance_criteria or "Not specified",
        standards_text=standards_text if standards_text else "[No relevant standards found in database]",
        vendor_text=vendor_text if vendor_text else "[No relevant text found in vendor submission]"
    )
    
    messages = [
        {
            "role": "system",
            "content": "You are a military compliance officer. Return only valid JSON with exact schema specified."
        },
        {
            "role": "user",
            "content": prompt
        }
    ]
    
    try:
        # Call LLM
        raw_response = llm_engine.generate(messages, max_tokens=600, temperature=0.1)
        
        # Parse JSON
        parsed = _parse_llm_json(raw_response)
        
        if not parsed:
            return ScoringResult(
                clause_number=clause.clause_number,
                status=ClauseStatus.PENDING,
                confidence=0.0,
                vendor_response_summary="Failed to parse LLM response",
                evidence_text="",
                gaps_identified="LLM parsing error",
                recommendation="review",
                llm_raw_response=raw_response
            )
        
        # Map status string to enum
        status_str = parsed.get("status", "pending").lower()
        status_map = {
            "compliant": ClauseStatus.COMPLIANT,
            "partial": ClauseStatus.PARTIAL,
            "non_compliant": ClauseStatus.NON_COMPLIANT,
            "non-compliant": ClauseStatus.NON_COMPLIANT,
            "not_applicable": ClauseStatus.NOT_APPLICABLE,
            "not-applicable": ClauseStatus.NOT_APPLICABLE,
            "pending": ClauseStatus.PENDING,
        }
        status = status_map.get(status_str, ClauseStatus.PENDING)
        
        # Validate and cap confidence
        confidence = float(parsed.get("confidence", 0.0))
        confidence = max(0.0, min(1.0, confidence))
        
        return ScoringResult(
            clause_number=clause.clause_number,
            status=status,
            confidence=confidence,
            vendor_response_summary=parsed.get("vendor_response_summary", ""),
            evidence_text=parsed.get("evidence", ""),
            gaps_identified=parsed.get("gaps"),
            recommendation=parsed.get("recommendation", "review"),
            llm_raw_response=raw_response
        )
    
    except Exception as e:
        logger.error(f"LLM scoring failed for clause {clause.clause_number}: {e}")
        return ScoringResult(
            clause_number=clause.clause_number,
            status=ClauseStatus.PENDING,
            confidence=0.0,
            vendor_response_summary=f"Scoring error: {str(e)}",
            evidence_text="",
            gaps_identified="System error",
            recommendation="review",
            llm_raw_response=""
        )


def _parse_llm_json(raw: str) -> Optional[Dict]:
    """Parse JSON from LLM response, handling common formatting issues."""
    try:
        # Remove markdown code blocks
        cleaned = re.sub(r'^```(?:json)?\s*', '', raw.strip(), flags=re.MULTILINE)
        cleaned = re.sub(r'```\s*$', '', cleaned.strip(), flags=re.MULTILINE)
        
        # Find JSON object
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        
        if start == -1 or end == 0:
            # Try array format
            start = cleaned.find("[")
            end = cleaned.rfind("]") + 1
        
        if start == -1 or end == 0:
            return None
        
        json_str = cleaned[start:end]
        return json.loads(json_str)
    
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse LLM JSON: {raw[:200]}...")
        return None
    
    except Exception as e:
        logger.error(f"JSON parsing error: {e}")
        return None


# ═══════════════════════════════════════════════════════════════
#  BATCH SCORING
# ═══════════════════════════════════════════════════════════════

def score_clauses_batch(
    clauses: List[ComplianceClauseBase],
    vendor_doc_id: str,
    batch_size: int = 5
) -> List[ScoringResult]:
    """
    Score multiple clauses in batches for efficiency.
    
    Args:
        clauses: List of SOTR clauses to score
        vendor_doc_id: Vendor document ID
        batch_size: Number of clauses per LLM call
        
    Returns:
        List of ScoringResult (one per clause)
    """
    # Get full vendor text once
    vendor_full_text = find_all_vendor_text(vendor_doc_id)
    
    if not vendor_full_text:
        logger.error("No vendor text found for batch scoring")
        return [
            ScoringResult(
                clause_number=c.clause_number,
                status=ClauseStatus.PENDING,
                confidence=0.0,
                vendor_response_summary="No vendor submission text found",
                evidence_text="",
                gaps_identified="Missing vendor document",
                recommendation="review",
                llm_raw_response=""
            )
            for c in clauses
        ]
    
    results = []
    
    # Process in batches
    for i in range(0, len(clauses), batch_size):
        batch = clauses[i:i + batch_size]
        
        # Build batch prompt
        clauses_text = "\n\n".join([
            f"CLAUSE {c.clause_number}: {c.clause_title or 'Untitled'}\n"
            f"Requirement: {c.clause_text[:200]}...\n"
            f"Acceptance Criteria: {c.acceptance_criteria or 'N/A'}"
            for c in batch
        ])
        
        prompt = _BATCH_CLAUSE_PROMPT.format(
            vendor_full_text=vendor_full_text[:3000],  # Limit context
            clauses_text=clauses_text
        )
        
        messages = [
            {
                "role": "system",
                "content": "You are a compliance officer. Return only valid JSON array with one result per clause."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
        
        try:
            raw_response = llm_engine.generate(messages, max_tokens=1000, temperature=0.1)
            parsed = _parse_llm_json(raw_response)
            
            if isinstance(parsed, list):
                # Map results to clauses
                for j, clause in enumerate(batch):
                    if j < len(parsed):
                        result = _map_batch_result(parsed[j], clause, raw_response)
                    else:
                        result = _create_error_result(clause, "Missing in batch response")
                    results.append(result)
            else:
                # Single object response or parse error
                logger.warning("Batch scoring returned non-array, falling back to individual")
                for clause in batch:
                    result = score_single_clause(clause, vendor_full_text)
                    results.append(result)
        
        except Exception as e:
            logger.error(f"Batch scoring failed: {e}")
            for clause in batch:
                result = _create_error_result(clause, f"Batch error: {str(e)}")
                results.append(result)
    
    return results


def _map_batch_result(
    parsed: Dict,
    clause: ComplianceClauseBase,
    raw_response: str
) -> ScoringResult:
    """Map a single result from batch response to ScoringResult."""
    status_str = parsed.get("status", "pending").lower()
    status_map = {
        "compliant": ClauseStatus.COMPLIANT,
        "partial": ClauseStatus.PARTIAL,
        "non_compliant": ClauseStatus.NON_COMPLIANT,
        "non-compliant": ClauseStatus.NON_COMPLIANT,
        "not_applicable": ClauseStatus.NOT_APPLICABLE,
        "not-applicable": ClauseStatus.NOT_APPLICABLE,
        "pending": ClauseStatus.PENDING,
    }
    status = status_map.get(status_str, ClauseStatus.PENDING)
    
    confidence = float(parsed.get("confidence", 0.0))
    confidence = max(0.0, min(1.0, confidence))
    
    return ScoringResult(
        clause_number=clause.clause_number,
        status=status,
        confidence=confidence,
        vendor_response_summary=parsed.get("vendor_response_summary", ""),
        evidence_text=parsed.get("evidence", ""),
        gaps_identified=parsed.get("gaps"),
        recommendation=parsed.get("recommendation", "review"),
        llm_raw_response=raw_response
    )


def _create_error_result(clause: ComplianceClauseBase, error: str) -> ScoringResult:
    """Create an error ScoringResult."""
    return ScoringResult(
        clause_number=clause.clause_number,
        status=ClauseStatus.PENDING,
        confidence=0.0,
        vendor_response_summary=f"Error: {error}",
        evidence_text="",
        gaps_identified=error,
        recommendation="review",
        llm_raw_response=""
    )


# ═══════════════════════════════════════════════════════════════
#  CONFIDENCE CALCULATION
# ═══════════════════════════════════════════════════════════════

def calculate_confidence_factors(
    result: ScoringResult,
    clause: ComplianceClauseBase
) -> Dict[str, float]:
    """
    Calculate detailed confidence factors for a scoring result.
    
    Returns dict with breakdown of confidence components.
    """
    factors = {
        "llm_confidence": result.confidence,
        "evidence_strength": 0.0,
        "direct_reference": 0.0,
        "completeness": 0.0,
    }
    
    # Evidence strength
    if result.evidence_text:
        evidence_len = len(result.evidence_text)
        if evidence_len > 200:
            factors["evidence_strength"] = 0.95
        elif evidence_len > 100:
            factors["evidence_strength"] = 0.75
        elif evidence_len > 50:
            factors["evidence_strength"] = 0.50
        else:
            factors["evidence_strength"] = 0.30
    
    # Direct reference check
    if result.evidence_text and clause.clause_number in result.evidence_text:
        factors["direct_reference"] = 0.95
    elif result.evidence_text and any(
        kw in result.evidence_text.lower()
        for kw in (clause.clause_title or "").lower().split()
        if len(kw) > 4
    ):
        factors["direct_reference"] = 0.70
    else:
        factors["direct_reference"] = 0.40
    
    # Completeness
    if result.vendor_response_summary and result.evidence_text and result.gaps_identified is not None:
        factors["completeness"] = 0.95
    elif result.vendor_response_summary and result.evidence_text:
        factors["completeness"] = 0.75
    elif result.vendor_response_summary:
        factors["completeness"] = 0.50
    else:
        factors["completeness"] = 0.20
    
    # Recalculate weighted confidence
    weighted = (
        factors["llm_confidence"] * 0.4 +
        factors["evidence_strength"] * 0.3 +
        factors["direct_reference"] * 0.2 +
        factors["completeness"] * 0.1
    )
    
    factors["final_confidence"] = round(weighted, 2)
    
    return factors


# ═══════════════════════════════════════════════════════════════
#  MAIN ENTRY POINTS
# ═══════════════════════════════════════════════════════════════

def score_clause_against_vendor(
    clause: ComplianceClauseBase,
    vendor_doc_id: str,
    vendor_doc_ids: Optional[List[str]] = None,
    standard_doc_ids: Optional[List[str]] = None,
    evaluation_context: Optional[Dict] = None
) -> ClauseScoreBase:
    """
    Main entry point: Score a single clause against vendor submission.
    
    Args:
        clause: SOTR clause to evaluate
        vendor_doc_id: Vendor document ID
        vendor_doc_ids: Optional list of all vendor document IDs
        standard_doc_ids: Optional list of standard document IDs
        evaluation_context: Optional context (project name, vessel, etc.)
        
    Returns:
        ClauseScoreBase with scoring result
    """
    # Find relevant vendor text and standards text
    vendor_text, chunk_ids, standards_text = find_relevant_vendor_text(
        clause, vendor_doc_id, vendor_doc_ids=vendor_doc_ids, standard_doc_ids=standard_doc_ids
    )
    
    # ── Speed Compliance Rule Override ──
    # If the vendor text specifies a vessel speed exceeding ICG maximum limit of 50.0 knots
    speed_violation = check_speed_compliance(vendor_text)
    if speed_violation:
        speed_val, matched_str = speed_violation
        logger.warning(
            "SPEED LIMIT VIOLATION DETECTED: %s (%s) — specified speed %f knots exceeds 50.0 knots limit",
            clause.clause_number, clause.clause_title or "Untitled", speed_val
        )
        return ClauseScoreBase(
            status=ClauseStatus.NON_COMPLIANT,
            confidence=1.0,
            vendor_response_summary=f"Vendor submission specifies a speed of {speed_val} knots ({matched_str}).",
            evidence_text=matched_str,
            gaps_identified=f"VIOLATION: Specified vessel speed of {speed_val} knots exceeds the Indian Coast Guard (ICG) maximum limit of 50.0 knots.",
            deviation_notes="reject",
            is_missing=False,
        )
        
    # ── Missing Clause Detection ──
    # If no vendor text found and clause is mandatory/critical, flag immediately
    if not vendor_text.strip():
        if clause.is_mandatory or clause.is_critical:
            logger.warning(
                "MISSING CLAUSE DETECTED: %s (%s) — vendor submission has no relevant text",
                clause.clause_number, clause.clause_title or "Untitled"
            )
            return ClauseScoreBase(
                status=ClauseStatus.NON_COMPLIANT,
                confidence=0.95,
                vendor_response_summary="MISSING: Vendor submission does not address this requirement.",
                evidence_text="",
                gaps_identified=(
                    f"Clause {clause.clause_number} ('{clause.clause_title or 'Untitled'}') "
                    f"is {'CRITICAL and ' if clause.is_critical else ''}mandatory but the vendor "
                    f"submission contains no text addressing this requirement. "
                    f"This clause has been silently skipped by the vendor."
                ),
                deviation_notes="reject",
                is_missing=True,
            )
        else:
            # Non-mandatory clause with no vendor text — NOT_APPLICABLE
            return ClauseScoreBase(
                status=ClauseStatus.NOT_APPLICABLE,
                confidence=0.80,
                vendor_response_summary="No relevant vendor text found; clause may not apply to this scope.",
                evidence_text="",
                gaps_identified=None,
                deviation_notes=None,
                is_missing=True,
            )
    
    # Score with LLM
    result = score_single_clause(clause, vendor_text, standards_text)
    
    # Calculate detailed confidence
    confidence_factors = calculate_confidence_factors(result, clause)
    final_confidence = confidence_factors["final_confidence"]
    
    return ClauseScoreBase(
        status=result.status,
        confidence=final_confidence,
        vendor_response_summary=result.vendor_response_summary,
        evidence_text=result.evidence_text,
        gaps_identified=result.gaps_identified,
        deviation_notes=result.recommendation if result.recommendation != "review" else None,
        is_missing=False,
    )


def score_all_clauses(
    clauses: List[ComplianceClauseBase],
    vendor_doc_id: str,
    vendor_doc_ids: Optional[List[str]] = None,
    standard_doc_ids: Optional[List[str]] = None,
    use_batch: bool = True,
    progress_callback: Optional[callable] = None
) -> List[Tuple[ComplianceClauseBase, ClauseScoreBase]]:
    """
    Score all clauses against vendor submission.
    
    Args:
        clauses: List of SOTR clauses
        vendor_doc_id: Vendor document ID
        vendor_doc_ids: Optional list of all vendor document IDs
        standard_doc_ids: Optional list of standard document IDs
        use_batch: Use batch processing for efficiency
        progress_callback: Optional callback(clause_number, status, progress_percent)
        
    Returns:
        List of (clause, score) tuples
    """
    results = []
    total = len(clauses)
    
    # If multiple vendor documents or standard references are provided,
    # force individual scoring to allow clause-level RAG search across them.
    if (vendor_doc_ids and len(vendor_doc_ids) > 1) or standard_doc_ids:
        use_batch = False
        
    if use_batch and total > 3:
        # ── Pre-check: Detect missing clauses before batch scoring ──
        # For each clause, check if vendor has relevant text. If not, flag as missing.
        clauses_to_batch = []
        missing_indices = {}  # index -> ClauseScoreBase for missing clauses
        
        for i, clause in enumerate(clauses):
            vendor_text, _, standards_text = find_relevant_vendor_text(
                clause, vendor_doc_id, vendor_doc_ids=vendor_doc_ids, standard_doc_ids=standard_doc_ids
            )
            # Speed violation check
            speed_violation = check_speed_compliance(vendor_text)
            if speed_violation:
                speed_val, matched_str = speed_violation
                score = ClauseScoreBase(
                    status=ClauseStatus.NON_COMPLIANT,
                    confidence=1.0,
                    vendor_response_summary=f"Vendor specified speed of {speed_val} knots ({matched_str}).",
                    evidence_text=matched_str,
                    gaps_identified=f"VIOLATION: Specified vessel speed of {speed_val} knots exceeds the Indian Coast Guard (ICG) maximum limit of 50.0 knots.",
                    deviation_notes="reject",
                    is_missing=False,
                )
                missing_indices[i] = score
                logger.warning(
                    "SPEED LIMIT VIOLATION (batch precheck): %s (%s)",
                    clause.clause_number, clause.clause_title or "Untitled"
                )
            elif not vendor_text.strip():
                # Missing clause — handle without LLM
                if clause.is_mandatory or clause.is_critical:
                    score = ClauseScoreBase(
                        status=ClauseStatus.NON_COMPLIANT,
                        confidence=0.95,
                        vendor_response_summary="MISSING: Vendor submission does not address this requirement.",
                        evidence_text="",
                        gaps_identified=(
                            f"Clause {clause.clause_number} ('{clause.clause_title or 'Untitled'}') "
                            f"is {'CRITICAL and ' if clause.is_critical else ''}mandatory but the vendor "
                            f"submission contains no text addressing this requirement. "
                            f"This clause has been silently skipped by the vendor."
                        ),
                        deviation_notes="reject",
                        is_missing=True,
                    )
                else:
                    score = ClauseScoreBase(
                        status=ClauseStatus.NOT_APPLICABLE,
                        confidence=0.80,
                        vendor_response_summary="No relevant vendor text found; clause may not apply to this scope.",
                        evidence_text="",
                        gaps_identified=None,
                        deviation_notes=None,
                        is_missing=True,
                    )
                missing_indices[i] = score
                logger.warning(
                    "MISSING CLAUSE (batch): %s (%s)",
                    clause.clause_number, clause.clause_title or "Untitled"
                )
            else:
                clauses_to_batch.append(clause)
        
        # Batch-score only clauses that have vendor text
        if clauses_to_batch:
            batch_results = score_clauses_batch(clauses_to_batch, vendor_doc_id)
        else:
            batch_results = []
        
        # Merge results in original order
        batch_idx = 0
        for i, clause in enumerate(clauses):
            if i in missing_indices:
                results.append((clause, missing_indices[i]))
            else:
                result = batch_results[batch_idx]
                batch_idx += 1
                confidence_factors = calculate_confidence_factors(result, clause)
                final_confidence = confidence_factors["final_confidence"]
                
                score = ClauseScoreBase(
                    status=result.status,
                    confidence=final_confidence,
                    vendor_response_summary=result.vendor_response_summary,
                    evidence_text=result.evidence_text,
                    gaps_identified=result.gaps_identified,
                    deviation_notes=result.recommendation if result.recommendation != "review" else None,
                    is_missing=False,
                )
                results.append((clause, score))
            
            if progress_callback:
                progress_percent = int(len(results) / total * 100)
                progress_callback(clause.clause_number, results[-1][1].status.value if hasattr(results[-1][1].status, 'value') else str(results[-1][1].status), progress_percent)
        
        if missing_indices:
            logger.info(
                "Missing/Violated clause detection (batch): %d/%d clauses handled by rule filters",
                len(missing_indices), total
            )
    else:
        # Individual scoring (already has missing clause detection via score_clause_against_vendor)
        for i, clause in enumerate(clauses):
            score = score_clause_against_vendor(
                clause,
                vendor_doc_id,
                vendor_doc_ids=vendor_doc_ids,
                standard_doc_ids=standard_doc_ids
            )
            results.append((clause, score))
            
            if progress_callback:
                progress_percent = int((i + 1) / total * 100)
                progress_callback(clause.clause_number, score.status, progress_percent)
    
    return results


def generate_evaluation_summary(
    scored_clauses: List[Tuple[ComplianceClauseBase, ClauseScoreBase]]
) -> Dict[str, Any]:
    """
    Generate summary statistics from scored clauses.
    
    Returns:
        Dict with counts, percentages, recommendation, and missing clause alerts
    """
    total = len(scored_clauses)
    
    counts = {
        "compliant": 0,
        "partial": 0,
        "non_compliant": 0,
        "not_applicable": 0,
        "pending": 0,
    }
    
    category_breakdown = {}
    total_confidence = 0.0
    missing_clauses = []  # Track clauses vendor silently skipped
    
    for clause, score in scored_clauses:
        counts[score.status.value] += 1
        total_confidence += score.confidence
        
        # Track missing clauses
        if getattr(score, 'is_missing', False):
            missing_clauses.append({
                "clause_number": clause.clause_number,
                "clause_title": clause.clause_title or "Untitled",
                "is_mandatory": clause.is_mandatory,
                "is_critical": clause.is_critical,
                "category": clause.category.value,
            })
        
        cat = clause.category.value
        if cat not in category_breakdown:
            category_breakdown[cat] = {"compliant": 0, "partial": 0, "non_compliant": 0, "total": 0}
        category_breakdown[cat]["total"] += 1
        if score.status == ClauseStatus.COMPLIANT:
            category_breakdown[cat]["compliant"] += 1
        elif score.status == ClauseStatus.PARTIAL:
            category_breakdown[cat]["partial"] += 1
        elif score.status == ClauseStatus.NON_COMPLIANT:
            category_breakdown[cat]["non_compliant"] += 1
    
    # Calculate compliance percentage
    scored = counts["compliant"] + counts["partial"] + counts["non_compliant"]
    if scored > 0:
        compliance_percentage = (counts["compliant"] + counts["partial"] * 0.5) / scored * 100
    else:
        compliance_percentage = 0.0
    
    # Determine recommendation — missing critical clauses automatically trigger reject
    critical_missing = [m for m in missing_clauses if m["is_critical"]]
    mandatory_missing = [m for m in missing_clauses if m["is_mandatory"]]
    
    if critical_missing:
        recommendation = "reject"
    elif counts["non_compliant"] == 0 and counts["compliant"] >= counts["partial"]:
        recommendation = "accept"
    elif counts["non_compliant"] <= 2 and counts["compliant"] > counts["non_compliant"]:
        recommendation = "conditional"
    else:
        recommendation = "reject"
    
    return {
        "total_clauses": total,
        "counts": counts,
        "compliance_percentage": round(compliance_percentage, 1),
        "average_confidence": round(total_confidence / total, 2) if total > 0 else 0.0,
        "category_breakdown": category_breakdown,
        "recommendation": recommendation,
        "missing_clauses": missing_clauses,
        "missing_clause_count": len(missing_clauses),
        "critical_missing_count": len(critical_missing),
        "mandatory_missing_count": len(mandatory_missing),
    }


# ═══════════════════════════════════════════════════════════════
#  TESTING
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Test with sample data
    test_clause = ComplianceClauseBase(
        clause_number="1.1",
        clause_title="Hull Construction",
        clause_text="The hull shall be constructed of steel to IRS Grade A.",
        category="technical",
        is_mandatory=True,
        is_critical=True,
        acceptance_criteria="IRS Class approval certificate"
    )
    
    test_vendor_text = """
    We confirm that the hull will be constructed using IRS Grade A steel plates.
    All construction will be supervised by IRS surveyors and will comply with
    IRS Rules and Regulations. Class approval certificate will be provided.
    """
    
    print("Clause Scorer Test")
    print("=" * 60)
    print(f"Clause: {test_clause.clause_number} - {test_clause.clause_title}")
    print(f"Text: {test_clause.clause_text}")
    print(f"\nVendor Text: {test_vendor_text}")
    print("-" * 60)
    
    result = score_single_clause(test_clause, test_vendor_text)
    
    print(f"Status: {result.status.value}")
    print(f"Confidence: {result.confidence:.2%}")
    print(f"Summary: {result.vendor_response_summary}")
    print(f"Evidence: {result.evidence_text[:100]}...")
    print(f"Gaps: {result.gaps_identified or 'None'}")
    print(f"Recommendation: {result.recommendation}")

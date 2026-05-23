"""
AGRA Compliance Module — Agent-Side Compliance Engine Router

Endpoints for SOTR parsing and clause scoring, called by the backend
during compliance evaluations.

Endpoints:
  POST /api/compliance/parse-sotr     — Parse SOTR document, extract clauses
  POST /api/compliance/score-clause   — Score a single clause against vendor doc
  POST /api/compliance/score-all      — Score all clauses (batch)
  GET  /api/compliance/doc-text/{id}  — Get full document text from vector store
"""

import logging
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException

from api.utils.auth_check import get_current_user

logger = logging.getLogger("agra.compliance_engine")
router = APIRouter()


# ═══════════════════════════════════════════════════════════════
#  REQUEST / RESPONSE MODELS
# ═══════════════════════════════════════════════════════════════

class ParseSOTRRequest(BaseModel):
    doc_id: str = Field(..., description="Document ID in vector store")
    filename: str = Field(default="", description="Original filename for SOTR detection")


class ParsedClauseResponse(BaseModel):
    clause_number: str
    clause_title: Optional[str] = None
    clause_text: str
    category: str = "general"
    subcategory: Optional[str] = None
    is_mandatory: bool = True
    is_critical: bool = False
    acceptance_criteria: Optional[str] = None
    page_number: Optional[int] = None
    extraction_confidence: float = 0.0


class ParseSOTRResponse(BaseModel):
    is_sotr: bool
    confidence: float
    total_clauses: int
    clauses: List[ParsedClauseResponse]
    metadata: Dict[str, Any] = {}


class ScoreClauseRequest(BaseModel):
    clause_number: str
    clause_title: Optional[str] = None
    clause_text: str
    category: str = "general"
    is_mandatory: bool = True
    is_critical: bool = False
    acceptance_criteria: Optional[str] = None
    vendor_doc_id: str = Field(..., description="Vendor document ID in vector store")


class ScoreClauseResponse(BaseModel):
    clause_number: str
    status: str  # compliant, partial, non_compliant, not_applicable, pending
    confidence: float
    vendor_response_summary: str = ""
    evidence_text: str = ""
    gaps_identified: Optional[str] = None
    recommendation: str = "review"


class ScoreAllRequest(BaseModel):
    clauses: List[ScoreClauseRequest]
    vendor_doc_id: str = Field(..., description="Vendor document ID in vector store")
    use_batch: bool = Field(default=True, description="Use batch processing for efficiency")


class ScoreAllResponse(BaseModel):
    scores: List[ScoreClauseResponse]
    summary: Dict[str, Any]


class DocTextResponse(BaseModel):
    doc_id: str
    total_chunks: int
    full_text: str


# ═══════════════════════════════════════════════════════════════
#  ENDPOINT 1: PARSE SOTR DOCUMENT
# ═══════════════════════════════════════════════════════════════

@router.post("/parse-sotr", response_model=ParseSOTRResponse)
async def parse_sotr(
    request: ParseSOTRRequest,
    user: dict = Depends(get_current_user),
):
    """
    Parse a SOTR document from the vector store and extract clauses.
    Returns structured clause data ready for compliance evaluation.
    """
    from api.rag.vector_store import get_store
    from api.rag.sotr_parser import parse_sotr_document

    store = get_store()

    # Retrieve all chunks for the document
    chunks = store.get_chunks_by_doc(request.doc_id)
    if not chunks:
        raise HTTPException(
            status_code=404,
            detail=f"No chunks found for document '{request.doc_id}' in vector store"
        )

    # Reconstruct full document text
    full_text = "\n\n".join(c.get("text", "") for c in chunks if c.get("text"))

    if not full_text.strip():
        raise HTTPException(
            status_code=400,
            detail="Document has no extractable text content"
        )

    # Parse SOTR
    result = parse_sotr_document(
        text=full_text,
        filename=request.filename,
        sotr_doc_id=0  # Not needed for parsing
    )

    # Convert parsed clauses to response format
    clauses_out = []
    raw_clauses = result.get("clauses", [])

    for clause in raw_clauses:
        if isinstance(clause, dict):
            cat = clause.get("category", "general")
            clauses_out.append(ParsedClauseResponse(
                clause_number=clause.get("clause_number", ""),
                clause_title=clause.get("clause_title"),
                clause_text=clause.get("clause_text", ""),
                category=cat.value if hasattr(cat, 'value') else str(cat),
                subcategory=clause.get("subcategory"),
                is_mandatory=clause.get("is_mandatory", True),
                is_critical=clause.get("is_critical", False),
                acceptance_criteria=clause.get("acceptance_criteria"),
                page_number=clause.get("page_number"),
                extraction_confidence=clause.get("extraction_confidence", 0.0),
            ))
        elif hasattr(clause, 'clause_number'):
            # ComplianceClauseBase Pydantic model from sotr_parser
            cat = clause.category
            clauses_out.append(ParsedClauseResponse(
                clause_number=clause.clause_number,
                clause_title=getattr(clause, 'clause_title', None),
                clause_text=clause.clause_text,
                category=cat.value if hasattr(cat, 'value') else str(cat),
                subcategory=getattr(clause, 'subcategory', None),
                is_mandatory=getattr(clause, 'is_mandatory', True),
                is_critical=getattr(clause, 'is_critical', False),
                acceptance_criteria=getattr(clause, 'acceptance_criteria', None),
                page_number=getattr(clause, 'page_number', None),
                extraction_confidence=getattr(clause, 'extraction_confidence', 0.0),
            ))
        else:
            # ParsedClause dataclass from sotr_parser
            clauses_out.append(ParsedClauseResponse(
                clause_number=clause.clause_number,
                clause_title=getattr(clause, 'title', None),
                clause_text=getattr(clause, 'text', ''),
                category=getattr(clause, 'category', 'general'),
                subcategory=getattr(clause, 'subcategory', None),
                is_mandatory=getattr(clause, 'is_mandatory', True),
                is_critical=getattr(clause, 'is_critical', False),
                acceptance_criteria=getattr(clause, 'acceptance_criteria', None),
                page_number=getattr(clause, 'page_number', None),
                extraction_confidence=getattr(clause, 'confidence', 0.0),
            ))

    logger.info(
        "Parsed SOTR doc '%s': is_sotr=%s, %d clauses extracted",
        request.doc_id, result.get("is_sotr"), len(clauses_out)
    )

    return ParseSOTRResponse(
        is_sotr=result.get("is_sotr", False),
        confidence=result.get("confidence", 0.0),
        total_clauses=len(clauses_out),
        clauses=clauses_out,
        metadata=result.get("metadata", {}),
    )


# ═══════════════════════════════════════════════════════════════
#  ENDPOINT 2: SCORE SINGLE CLAUSE
# ═══════════════════════════════════════════════════════════════

@router.post("/score-clause", response_model=ScoreClauseResponse)
async def score_clause(
    request: ScoreClauseRequest,
    user: dict = Depends(get_current_user),
):
    """
    Score a single SOTR clause against a vendor submission document.
    Uses RAG to find relevant vendor text, then LLM to evaluate compliance.
    """
    from api.models.compliance_models import ComplianceClauseBase, ClauseCategory
    from api.rag.clause_scorer import score_clause_against_vendor

    # Convert request to internal model
    category_map = {
        "technical": ClauseCategory.TECHNICAL,
        "commercial": ClauseCategory.COMMERCIAL,
        "safety": ClauseCategory.SAFETY,
        "general": ClauseCategory.GENERAL,
        "quality": ClauseCategory.QUALITY,
        "environmental": ClauseCategory.ENVIRONMENTAL,
    }

    clause = ComplianceClauseBase(
        clause_number=request.clause_number,
        clause_title=request.clause_title,
        clause_text=request.clause_text,
        category=category_map.get(request.category, ClauseCategory.GENERAL),
        is_mandatory=request.is_mandatory,
        is_critical=request.is_critical,
        acceptance_criteria=request.acceptance_criteria,
    )

    # Score
    score = score_clause_against_vendor(
        clause=clause,
        vendor_doc_id=request.vendor_doc_id,
    )

    return ScoreClauseResponse(
        clause_number=request.clause_number,
        status=score.status.value,
        confidence=score.confidence,
        vendor_response_summary=score.vendor_response_summary or "",
        evidence_text=score.evidence_text or "",
        gaps_identified=score.gaps_identified,
        recommendation=score.deviation_notes or "review",
    )


# ═══════════════════════════════════════════════════════════════
#  ENDPOINT 3: SCORE ALL CLAUSES (BATCH)
# ═══════════════════════════════════════════════════════════════

@router.post("/score-all", response_model=ScoreAllResponse)
async def score_all_clauses_endpoint(
    request: ScoreAllRequest,
    user: dict = Depends(get_current_user),
):
    """
    Score all clauses in batch against a vendor submission.
    Returns individual scores and an aggregate summary.
    """
    from api.models.compliance_models import ComplianceClauseBase, ClauseCategory
    from api.rag.clause_scorer import score_all_clauses, generate_evaluation_summary

    category_map = {
        "technical": ClauseCategory.TECHNICAL,
        "commercial": ClauseCategory.COMMERCIAL,
        "safety": ClauseCategory.SAFETY,
        "general": ClauseCategory.GENERAL,
        "quality": ClauseCategory.QUALITY,
        "environmental": ClauseCategory.ENVIRONMENTAL,
    }

    # Convert requests to internal models
    clauses = []
    for req_clause in request.clauses:
        clauses.append(ComplianceClauseBase(
            clause_number=req_clause.clause_number,
            clause_title=req_clause.clause_title,
            clause_text=req_clause.clause_text,
            category=category_map.get(req_clause.category, ClauseCategory.GENERAL),
            is_mandatory=req_clause.is_mandatory,
            is_critical=req_clause.is_critical,
            acceptance_criteria=req_clause.acceptance_criteria,
        ))

    if not clauses:
        raise HTTPException(status_code=400, detail="No clauses provided")

    # Score all
    logger.info("Scoring %d clauses against vendor doc '%s'", len(clauses), request.vendor_doc_id)

    scored_results = score_all_clauses(
        clauses=clauses,
        vendor_doc_id=request.vendor_doc_id,
        use_batch=request.use_batch,
    )

    # Build response
    scores_out = []
    for clause, score in scored_results:
        scores_out.append(ScoreClauseResponse(
            clause_number=clause.clause_number,
            status=score.status.value,
            confidence=score.confidence,
            vendor_response_summary=score.vendor_response_summary or "",
            evidence_text=score.evidence_text or "",
            gaps_identified=score.gaps_identified,
            recommendation=score.deviation_notes or "review",
        ))

    # Generate summary
    summary = generate_evaluation_summary(scored_results)

    logger.info(
        "Scoring complete: %d clauses, %.1f%% compliance, recommendation=%s",
        len(scores_out),
        summary.get("compliance_percentage", 0),
        summary.get("recommendation", "unknown"),
    )

    return ScoreAllResponse(scores=scores_out, summary=summary)


# ═══════════════════════════════════════════════════════════════
#  ENDPOINT 4: GET DOCUMENT TEXT
# ═══════════════════════════════════════════════════════════════

@router.get("/doc-text/{doc_id}", response_model=DocTextResponse)
async def get_document_text(
    doc_id: str,
    user: dict = Depends(get_current_user),
):
    """
    Retrieve full document text from vector store by reconstructing chunks.
    Useful for SOTR parsing when text isn't stored elsewhere.
    """
    from api.rag.vector_store import get_store

    store = get_store()
    chunks = store.get_chunks_by_doc(doc_id)

    if not chunks:
        raise HTTPException(
            status_code=404,
            detail=f"No chunks found for document '{doc_id}'"
        )

    full_text = "\n\n".join(c.get("text", "") for c in chunks if c.get("text"))

    return DocTextResponse(
        doc_id=doc_id,
        total_chunks=len(chunks),
        full_text=full_text,
    )

"""
AGRA Chat Enhancement Phase 1 — Chat Drawing Query Endpoint
Natural language Q&A about drawings with RAG context search.

Offline/Local: Uses llama-server @ localhost:8080, Qdrant vector store
"""

import json
import logging
import time
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.models.models import AsyncJob, get_agent_db, SessionLocal
from api.models.drawing_models import DrawingAnalysisResult
from api.utils.auth_check import get_current_user
from api.utils.usage_logger import log_usage
from api.rag.vector_store import get_store
from api.rag import llm as llm_engine

# Import drawing pipeline
from api.routers.drawing_enhanced import run_drawing_analysis_pipeline

# Phase 2: Intent Router
from api.rag.drawing_query_router import (
    classify_intent, classify_intent_fast, get_query_plan, route_query,
    QueryIntent, QueryPlan, ProcessingStep
)

# Phase 3: Context Search
from api.rag.drawing_context_search import (
    search_drawing_context,
    quick_vessel_search,
    SearchResult,
    ContextAssembly
)

# Phase 4: Suggestion Engine
from api.rag.drawing_suggestion_engine import (
    generate_suggestions as generate_suggestion_set,
    SuggestionSet,
    SuggestionType,
    quick_quality_suggestion,
    quick_vessel_suggestion
)

logger = logging.getLogger("agra.chat_drawing_query")
router = APIRouter()


# ═══════════════════════════════════════════════════════════════
#  REQUEST/RESPONSE MODELS
# ═══════════════════════════════════════════════════════════════

class DrawingQueryRequest(BaseModel):
    """Request for drawing analysis with natural language query."""
    query: str = Field(..., min_length=1, max_length=2000, description="Natural language question about the drawing")
    session_id: Optional[str] = Field(None, description="Chat session ID for context")


class RAGSource(BaseModel):
    """A single RAG source document retrieved for context."""
    document_id: str
    document_name: str
    document_type: str
    relevance_score: float
    excerpt: str
    vessel_name: Optional[str] = None


class ConfidenceBreakdown(BaseModel):
    """Detailed confidence scoring breakdown."""
    overall: float = Field(..., ge=0.0, le=1.0, description="Overall confidence 0-1")
    vlm: float = Field(..., ge=0.0, le=1.0, description="VLM analysis confidence")
    ocr: float = Field(..., ge=0.0, le=1.0, description="OCR extraction confidence")
    rag: float = Field(..., ge=0.0, le=1.0, description="RAG context relevance")
    query_clarity: float = Field(..., ge=0.0, le=1.0, description="Query understanding confidence")
    quality_label: str = Field(..., description="High/Medium/Low quality label")


class SuggestionItem(BaseModel):
    """AI-generated suggestion based on cross-reference."""
    type: str = Field(..., description="match|upgrade|cross_reference|gap_analysis|advancement")
    text: str
    confidence: float
    action: Optional[str] = None


class DrawingQueryResponse(BaseModel):
    """Response for chat drawing query."""
    job_id: str
    status: str
    query: str
    answer: Optional[str] = None
    drawing_summary: Optional[Dict[str, Any]] = None
    rag_sources: List[RAGSource] = []
    confidence: Optional[ConfidenceBreakdown] = None
    suggestions: List[SuggestionItem] = []
    processing_time_ms: Optional[float] = None
    created_at: datetime
    completed_at: Optional[datetime] = None


class DrawingQueryStatusResponse(BaseModel):
    """Status check response for async drawing query."""
    job_id: str
    status: str  # pending, processing, completed, failed
    progress: int = Field(..., ge=0, le=100)
    result: Optional[DrawingQueryResponse] = None
    error_message: Optional[str] = None


# Note: Intent classification handled by drawing_query_router
# Note: RAG Context Search handled by drawing_context_search (Phase 3)


def search_rag_context(drawing_data: Dict[str, Any]) -> List[RAGSource]:
    """
    Phase 3: Search RAG context using drawing_context_search module.
    Wrapper to convert SearchResult to RAGSource format.
    """
    try:
        # Use Phase 3 context search
        context = search_drawing_context(
            drawing_data=drawing_data,
            include_vessels=True,
            include_drawings=True,
            include_equipment=True,
            include_compliance=True,
            top_k=5
        )
        
        # Convert all results to RAGSource format
        all_results = []
        all_results.extend(context.vessel_matches)
        all_results.extend(context.similar_drawings)
        all_results.extend(context.matching_parts)
        all_results.extend(context.related_sotrs)
        
        # Convert to RAGSource
        sources = []
        for result in all_results:
            source = RAGSource(
                document_id=result.document_id,
                document_name=result.document_name,
                document_type=result.document_type,
                relevance_score=result.relevance_score,
                excerpt=result.excerpt,
                vessel_name=result.vessel_name
            )
            sources.append(source)
        
        # Sort by relevance
        sources.sort(key=lambda x: x.relevance_score, reverse=True)
        
        logger.info(f"RAG search found {len(sources)} sources (highest relevance: {context.highest_relevance:.2f})")
        
        return sources[:10]
        
    except Exception as e:
        logger.error(f"Phase 3 context search failed: {e}")
        return []  # Return empty on failure


# ═══════════════════════════════════════════════════════════════
#  ANSWER GENERATION
# ═══════════════════════════════════════════════════════════════

ANSWER_PROMPT_TEMPLATE = """You are an expert maritime engineering assistant analyzing a technical drawing.

USER QUERY: {query}
INTENT: {intent}

DRAWING ANALYSIS RESULTS:
- Drawing Type: {drawing_type}
- Drawing Number: {drawing_number}
- Vessel Name: {vessel_name}
- Project: {project_name}
- Dimensions: {dimensions_summary}
- Equipment Tags: {equipment_summary}

RELEVANT DATABASE CONTEXT:
{rag_context}

INSTRUCTIONS:
1. Answer the user's query directly and concisely
2. Use specific data from the drawing analysis
3. Reference relevant database context when applicable
4. If suggesting advancement potential, be specific about compatibility
5. If confidence is low, recommend manual verification

Provide your answer in clear, professional language suitable for ICG (Indian Coast Guard) officers."""


def generate_answer(
    query: str,
    intent: str,
    drawing_data: Dict[str, Any],
    rag_sources: List[RAGSource]
) -> str:
    """Generate natural language answer using LLM."""
    
    # Build drawing summary
    title_block = drawing_data.get("title_block", {})
    dimensions = drawing_data.get("dimensions", [])
    equipment = drawing_data.get("equipment_tags", [])
    
    # Format dimensions summary
    dims_summary = ""
    if dimensions:
        dims = []
        for d in dimensions[:5]:
            if isinstance(d, dict):
                name = d.get("name", "")
                value = d.get("value", "")
                unit = d.get("unit", "")
                dims.append(f"{name}: {value} {unit}")
        dims_summary = "; ".join(dims) if dims else "No dimensions extracted"
    else:
        dims_summary = "No dimensions extracted"
    
    # Format equipment summary
    equip_summary = ""
    if equipment:
        tags = []
        for e in equipment[:5]:
            if isinstance(e, dict):
                tag = e.get("tag_number", "") or e.get("description", "")
                if tag:
                    tags.append(tag)
        equip_summary = "; ".join(tags) if tags else "No equipment tags found"
    else:
        equip_summary = "No equipment tags found"
    
    # Format RAG context
    rag_context = ""
    if rag_sources:
        context_lines = []
        for src in rag_sources[:5]:
            context_lines.append(f"- {src.document_name} (relevance: {src.relevance_score:.2f}): {src.excerpt[:150]}")
        rag_context = "\n".join(context_lines)
    else:
        rag_context = "No relevant documents found in database."
    
    # Build prompt
    prompt = ANSWER_PROMPT_TEMPLATE.format(
        query=query,
        intent=intent,
        drawing_type=drawing_data.get("drawing_type", "unknown"),
        drawing_number=title_block.get("drawing_number", "N/A"),
        vessel_name=title_block.get("vessel_name", "Unknown"),
        project_name=title_block.get("project_name", "Unknown"),
        dimensions_summary=dims_summary,
        equipment_summary=equip_summary,
        rag_context=rag_context
    )
    
    # Generate answer
    try:
        answer = llm_engine.llm_complete(
            prompt=prompt,
            max_tokens=800,
            temperature=0.3
        )
        return answer.strip()
    except Exception as e:
        logger.error(f"Answer generation failed: {e}")
        return "I apologize, but I was unable to generate an answer due to a processing error. Please try again or contact support."


# ═══════════════════════════════════════════════════════════════
#  SUGGESTION ENGINE
# ═══════════════════════════════════════════════════════════════

def generate_suggestions(
    drawing_data: Dict[str, Any],
    rag_sources: List[RAGSource],
    query: str,
    intent: str
) -> List[SuggestionItem]:
    """
    Phase 4: Generate AI suggestions using suggestion engine.
    Wrapper that converts SuggestionSet to list of SuggestionItem.
    """
    try:
        # Get analysis confidence
        confidence = drawing_data.get("confidence", {})
        if isinstance(confidence, dict):
            overall_conf = confidence.get("overall_confidence", 0.7)
        else:
            overall_conf = getattr(confidence, 'overall_confidence', 0.7)
        
        # Convert RAGSource list to SearchResult list for context assembly
        search_results = []
        for src in rag_sources:
            sr = SearchResult(
                document_id=src.document_id,
                document_name=src.document_name,
                document_type=src.document_type,
                relevance_score=src.relevance_score,
                excerpt=src.excerpt,
                vessel_name=src.vessel_name
            )
            search_results.append(sr)
        
        # Build context assembly from search results
        # Categorize based on document type
        vessel_matches = [r for r in search_results if "vessel" in r.document_type.lower() or r.vessel_name]
        similar_drawings = [r for r in search_results if "drawing" in r.document_type.lower() or "blueprint" in r.document_type.lower()]
        matching_parts = [r for r in search_results if "part" in r.document_type.lower() or "equipment" in r.document_type.lower()]
        related_sotrs = [r for r in search_results if "sotr" in r.document_type.lower()]
        
        # Get highest relevance
        highest_rel = max((r.relevance_score for r in search_results), default=0.0)
        
        context = ContextAssembly(
            vessel_matches=vessel_matches,
            similar_drawings=similar_drawings,
            matching_parts=matching_parts,
            related_sotrs=related_sotrs,
            raw_context_text="",  # Not used by suggestion engine
            total_sources=len(search_results),
            highest_relevance=highest_rel
        )
        
        # Use Phase 4 suggestion engine
        suggestion_set = generate_suggestion_set(
            drawing_data=drawing_data,
            context=context,
            query=query,
            analysis_confidence=overall_conf,
            use_llm_enhancement=False  # Skip LLM for speed, can enable later
        )
        
        # Convert SuggestionSet to list of SuggestionItem
        items = []
        for sug in suggestion_set.suggestions:
            items.append(SuggestionItem(
                type=sug.type.value,
                text=sug.title + ": " + sug.description,
                confidence=sug.confidence,
                action=sug.action
            ))
        
        logger.info(f"Generated {len(items)} suggestions via Phase 4 engine")
        
        return items
        
    except Exception as e:
        logger.error(f"Phase 4 suggestion generation failed: {e}")
        # Fallback to basic suggestions
        return _fallback_suggestions(drawing_data, rag_sources, intent)


def _fallback_suggestions(
    drawing_data: Dict[str, Any],
    rag_sources: List[RAGSource],
    intent: str
) -> List[SuggestionItem]:
    """Fallback suggestion generator if Phase 4 engine fails."""
    suggestions = []
    
    title_block = drawing_data.get("title_block", {})
    vessel_name = title_block.get("vessel_name")
    confidence = drawing_data.get("confidence", {})
    overall_conf = confidence.get("overall_confidence", 0.7) if isinstance(confidence, dict) else 0.7
    
    # Basic vessel match
    if vessel_name:
        matching = [s for s in rag_sources if s.vessel_name and s.vessel_name.lower() == vessel_name.lower()]
        if matching:
            best = max(matching, key=lambda x: x.relevance_score)
            suggestions.append(SuggestionItem(
                type="match",
                text=f"Vessel match: {vessel_name} ({best.relevance_score:.0%})",
                confidence=best.relevance_score,
                action="view_vessel"
            ))
    
    # Quality suggestion
    if overall_conf < 0.60:
        suggestions.append(SuggestionItem(
            type="gap_analysis",
            text="Low confidence - manual verification recommended",
            confidence=0.9,
            action="manual_review"
        ))
    
    return suggestions


# ═══════════════════════════════════════════════════════════════
#  CONFIDENCE CALCULATION
# ═══════════════════════════════════════════════════════════════

def calculate_query_confidence(
    drawing_data: Dict[str, Any],
    rag_sources: List[RAGSource],
    query: str,
    intent_str: str
) -> ConfidenceBreakdown:
    """
    Calculate multi-factor confidence score using QueryPlan weights.
    Phase 2: Uses weights from drawing_query_router module.
    """
    
    # Convert string intent to enum
    try:
        intent = QueryIntent(intent_str.lower())
    except ValueError:
        intent = QueryIntent.EXTRACT
    
    # Get query plan with weights
    plan = get_query_plan(intent)
    
    # Extract step weights from plan
    step_weights = {step.step_name: step.weight_in_confidence for step in plan.steps}
    
    # Extract base confidences
    confidence = drawing_data.get("confidence", {})
    if isinstance(confidence, dict):
        vlm_conf = confidence.get("vlm_confidence", 0.7)
        ocr_conf = confidence.get("ocr_confidence", 0.7)
        drawing_type_conf = confidence.get("drawing_type_confidence", 0.7)
    else:
        vlm_conf = getattr(confidence, 'vlm_confidence', 0.7)
        ocr_conf = getattr(confidence, 'ocr_confidence', 0.7)
        drawing_type_conf = getattr(confidence, 'drawing_type_confidence', 0.7)
    
    # Calculate RAG relevance (average of top sources)
    if rag_sources:
        rag_conf = sum(s.relevance_score for s in rag_sources[:3]) / min(len(rag_sources), 3)
    else:
        rag_conf = 0.3  # Low confidence if no context found
    
    # Query clarity score (based on specificity)
    query_lower = query.lower()
    specificity_keywords = ["dimension", "spec", "measurement", "equipment", "vessel", "drawing", "blueprint", "compliance"]
    matches = sum(1 for kw in specificity_keywords if kw in query_lower)
    query_clarity = min(0.5 + (matches * 0.1), 0.95)
    
    # Build weights from plan (using intent-based fallback if needed)
    intent_weights = {
        QueryIntent.EXTRACT: {"vlm": 0.45, "ocr": 0.25, "rag": 0.20, "query": 0.10},
        QueryIntent.IDENTIFY: {"vlm": 0.40, "ocr": 0.20, "rag": 0.25, "query": 0.15},
        QueryIntent.COMPARE: {"vlm": 0.30, "ocr": 0.15, "rag": 0.40, "query": 0.15},
        QueryIntent.SUGGEST: {"vlm": 0.25, "ocr": 0.15, "rag": 0.45, "query": 0.15},
        QueryIntent.VALIDATE: {"vlm": 0.30, "ocr": 0.30, "rag": 0.25, "query": 0.15},
    }
    
    w = intent_weights.get(intent, intent_weights[QueryIntent.EXTRACT])
    
    # Calculate weighted overall
    overall = (
        vlm_conf * w["vlm"] +
        ocr_conf * w["ocr"] +
        rag_conf * w["rag"] +
        query_clarity * w["query"]
    )
    
    # Determine quality label
    if overall >= 0.80:
        quality = "High"
    elif overall >= 0.60:
        quality = "Medium"
    else:
        quality = "Low"
    
    return ConfidenceBreakdown(
        overall=round(overall, 2),
        vlm=round(vlm_conf, 2),
        ocr=round(ocr_conf, 2),
        rag=round(rag_conf, 2),
        query_clarity=round(query_clarity, 2),
        quality_label=quality
    )


# ═══════════════════════════════════════════════════════════════
#  MAIN PIPELINE
# ═══════════════════════════════════════════════════════════════

def run_chat_drawing_query_pipeline(
    job_id: str,
    file_bytes: bytes,
    filename: str,
    content_type: str,
    query: str,
    db_session: Session
) -> DrawingQueryResponse:
    """
    Execute full chat drawing query pipeline:
    1. Analyze drawing (VLM + OCR)
    2. Classify query intent
    3. Search RAG for context
    4. Generate answer
    5. Build suggestions
    6. Calculate confidence
    """
    start_time = time.time()
    
    try:
        # Update job status
        job = db_session.query(AsyncJob).filter(AsyncJob.id == job_id).first()
        if job:
            job.status = "processing"
            job.progress = 10
            db_session.commit()
        
        # ── STEP 1: DRAWING ANALYSIS ──
        if job:
            job.progress = 30
            db_session.commit()
        
        from api.models.drawing_models import DrawingAnalysisRequest
        
        drawing_result = run_drawing_analysis_pipeline(
            job_id=job_id,
            file_bytes=file_bytes,
            filename=filename,
            content_type=content_type,
            db_session=db_session,
            request_options=DrawingAnalysisRequest(extract_measurements=True)
        )
        
        # Convert to dict for easier handling
        drawing_data = drawing_result.dict() if hasattr(drawing_result, 'dict') else drawing_result
        
        # ── STEP 2: INTENT CLASSIFICATION (Phase 2: Using Router) ──
        if job:
            job.progress = 50
            db_session.commit()
        
        # Get full query plan from router
        query_plan = route_query(query)
        intent = query_plan.intent.value
        
        logger.info(f"Query routed: intent={intent}, priority={query_plan.priority}, requires_rag={query_plan.requires_rag}")
        
        # ── STEP 3: RAG CONTEXT SEARCH (Phase 3) ──
        if job:
            job.progress = 70
            db_session.commit()
        
        # Use Phase 3 context search (integrated vessel/drawing/equipment search)
        rag_sources = search_rag_context(drawing_data)
        
        # ── STEP 4: ANSWER GENERATION ──
        if job:
            job.progress = 85
            db_session.commit()
        
        answer = generate_answer(query, intent, drawing_data, rag_sources)
        
        # ── STEP 5: SUGGESTIONS (Phase 4) ──
        suggestions = generate_suggestions(drawing_data, rag_sources, query, intent)
        
        # ── STEP 6: CONFIDENCE CALCULATION ──
        confidence = calculate_query_confidence(drawing_data, rag_sources, query, intent)
        
        # Build drawing summary
        title_block = drawing_data.get("title_block", {})
        drawing_summary = {
            "drawing_type": drawing_data.get("drawing_type", "unknown"),
            "drawing_number": title_block.get("drawing_number"),
            "vessel_name": title_block.get("vessel_name"),
            "project_name": title_block.get("project_name"),
            "dimensions_count": len(drawing_data.get("dimensions", [])),
            "equipment_count": len(drawing_data.get("equipment_tags", [])),
        }
        
        # Update job
        processing_time = (time.time() - start_time) * 1000
        response = DrawingQueryResponse(
            job_id=job_id,
            status="completed",
            query=query,
            answer=answer,
            drawing_summary=drawing_summary,
            rag_sources=rag_sources,
            confidence=confidence,
            suggestions=suggestions,
            processing_time_ms=processing_time,
            created_at=job.created_at if job else datetime.utcnow(),
            completed_at=datetime.utcnow()
        )
        if job:
            job.status = "completed"
            job.progress = 100
            job.result_data = json.loads(response.json())
            db_session.commit()
        
        return response
        
    except Exception as e:
        logger.error(f"Chat drawing query failed for job {job_id}: {e}")
        
        job = db_session.query(AsyncJob).filter(AsyncJob.id == job_id).first()
        if job:
            job.status = "failed"
            job.error_message = str(e)
            db_session.commit()
        
        raise


# ═══════════════════════════════════════════════════════════════
#  API ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@router.post("/chat/drawing_query", response_model=DrawingQueryResponse)
async def submit_drawing_query(
    background_tasks: BackgroundTasks,
    query: str = Form(..., description="Natural language question about the drawing"),
    image: UploadFile = File(..., description="Drawing image or PDF"),
    session_id: Optional[str] = Form(None),
    db: Session = Depends(get_agent_db),
    user: dict = Depends(get_current_user)
):
    """
    Submit a drawing with a natural language query for analysis.
    Returns immediately with job_id - poll /chat/drawing_query/{job_id} for results.
    """
    username = user.get("sub", "unknown")
    job_id = str(uuid.uuid4())
    
    # Validate file type
    content_type = image.content_type or ""
    allowed_types = ["image/png", "image/jpeg", "image/jpg", "application/pdf"]
    
    if content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type: {content_type}. Allowed: {', '.join(allowed_types)}"
        )
    
    # Read file bytes
    file_bytes = await image.read()
    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty file uploaded")
    
    # Create async job
    job = AsyncJob(
        id=job_id,
        job_type="chat_drawing_query",
        status="pending",
        progress=0,
        filename=image.filename,
        username=username,
        parameters=json.dumps({"query": query, "session_id": session_id})
    )
    db.add(job)
    db.commit()
    
    # Queue pipeline — wrap in helper that closes the DB session after use
    def _run_and_close_session():
        session = SessionLocal()
        try:
            run_chat_drawing_query_pipeline(
                job_id, file_bytes, image.filename, content_type, query, session
            )
        finally:
            session.close()

    background_tasks.add_task(_run_and_close_session)
    
    log_usage(
        action_type="chat_drawing_query",
        module="drawing",
        token=user.get("token", ""),
        metadata_=f"Query: {query[:50]}... | File: {image.filename}"
    )
    
    return DrawingQueryResponse(
        job_id=job_id,
        status="pending",
        query=query,
        created_at=datetime.utcnow()
    )


@router.get("/chat/drawing_query/{job_id}", response_model=DrawingQueryStatusResponse)
async def get_drawing_query_status(
    job_id: str,
    db: Session = Depends(get_agent_db),
    user: dict = Depends(get_current_user)
):
    """Check status of a drawing query job and retrieve results if complete."""
    job = db.query(AsyncJob).filter(AsyncJob.id == job_id).first()
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Parse result if completed
    result = None
    if job.status == "completed" and job.result_data:
        try:
            result_data = json.loads(job.result_data) if isinstance(job.result_data, str) else job.result_data
            result = DrawingQueryResponse(**result_data)
        except Exception as e:
            logger.warning(f"Failed to parse job result: {e}")
    
    return DrawingQueryStatusResponse(
        job_id=job_id,
        status=job.status,
        progress=job.progress or 0,
        result=result,
        error_message=job.error_message
    )


# ═══════════════════════════════════════════════════════════════
#  TEST BLOCK
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("Chat Drawing Query Endpoint - Phase 1")
    print("=" * 50)
    print("Models defined:")
    print(f"  - DrawingQueryRequest: {DrawingQueryRequest.__name__}")
    print(f"  - DrawingQueryResponse: {DrawingQueryResponse.__name__}")
    print(f"  - ConfidenceBreakdown: {ConfidenceBreakdown.__name__}")
    print(f"  - RAGSource: {RAGSource.__name__}")
    print(f"  - SuggestionItem: {SuggestionItem.__name__}")
    print("\nEndpoints:")
    print("  POST /chat/drawing_query - Submit query")
    print("  GET  /chat/drawing_query/{job_id} - Check status")
    print("\nPipeline functions:")
    print("  - run_chat_drawing_query_pipeline")
    print("  - classify_intent")
    print("  - search_rag_context")
    print("  - generate_answer")
    print("  - generate_suggestions")
    print("  - calculate_query_confidence")

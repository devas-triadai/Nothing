"""
AGRA Phase 2 — Router: Chat / Document Q&A
SSE-streamed conversational Q&A with RAG citations.
"""

import json
import logging
import asyncio
import time
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.utils.auth_check import get_current_user
from api.utils.usage_logger import log_usage
from api.rag.pipeline import query_pipeline

# Phase 5: Drawing Analysis integration
from api.models.models import AsyncJob, get_agent_db
from api.models.drawing_models import DrawingAnalysisResult, ChatDrawingAnalysis
from api.routers.drawing_enhanced import run_drawing_analysis_pipeline

logger = logging.getLogger("agra.chat")

router = APIRouter()


class ChatMessage(BaseModel):
    role: str = Field(..., description="'user' or 'assistant'")
    content: str


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=5000)
    session_id: Optional[str] = None
    history: List[ChatMessage] = Field(default_factory=list)
    doc_ids: Optional[List[str]] = Field(None, description="Filter to specific documents")


@router.post("/chat")
async def chat(
    body: ChatRequest,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Conversational Q&A with RAG.
    Returns an SSE stream:
      - {"token": "..."} for each generated token
      - {"done": true, "sources": [...]} as the final event
    """
    username = user.get("sub", "unknown")
    logger.info("Chat from %s: %s", username, body.question[:100])

    # Extract raw token for downstream API calls
    auth_header = request.headers.get("authorization", "")
    raw_token = auth_header.replace("Bearer ", "") if auth_header else ""

    history = [{"role": m.role, "content": m.content} for m in body.history]

    async def event_stream():
        start_time = time.time()
        token_count = 0
        try:
            async for event in _async_query_wrapper(
                question=body.question,
                session_history=history,
                user_id=0,
                token=raw_token,
                doc_ids_filter=body.doc_ids,
            ):
                if 'token' in event:
                    token_count += 1
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            logger.error("Chat stream error: %s", e, exc_info=True)
            yield f"data: {json.dumps({'error': str(e), 'done': True})}\n\n"
        finally:
            elapsed_ms = (time.time() - start_time) * 1000
            log_usage(
                action_type="chat",
                module="rag",
                token=raw_token,
                response_time_ms=elapsed_ms,
                output_tokens=token_count,
                metadata_=body.question,
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def _async_query_wrapper(
    question: str,
    session_history: list,
    user_id: int,
    token: str,
    doc_ids_filter: Optional[List[str]],
):
    """
    Wraps and iterates over the async generator returned by query_pipeline.
    """
    async for event in query_pipeline(
        question=question,
        session_history=session_history,
        user_id=user_id,
        token=token,
        doc_ids_filter=doc_ids_filter,
    ):
        yield event
        # Yield control to event loop between tokens
        await asyncio.sleep(0)


# ═══════════════════════════════════════════════════════════════════
#  PHASE 5: CHAT DRAWING ANALYSIS
# ═══════════════════════════════════════════════════════════════════

class ChatDrawingResponse(BaseModel):
    """Response for chat drawing analysis."""
    job_id: str
    status: str
    message: str
    preview: Optional[ChatDrawingAnalysis] = None


def _format_drawing_for_chat(result: DrawingAnalysisResult) -> ChatDrawingAnalysis:
    """
    Format DrawingAnalysisResult into ChatDrawingAnalysis for chat display.
    """
    # Build key dimensions list (max 5)
    key_dims = []
    for dim in result.dimensions[:5]:
        key_dims.append({
            "name": dim.name,
            "value": dim.value,
            "unit": dim.unit.value,
            "confidence": dim.confidence
        })
    
    # Build summary text in markdown format
    summary_lines = [
        f"📐 **Drawing Analysis: {result.title_block.drawing_number or result.filename}**",
        f"",
        f"- **Type**: {result.drawing_type.value.replace('_', ' ').title()} (confidence: {result.drawing_type_confidence:.0%})",
    ]
    
    if result.title_block.vessel_name:
        summary_lines.append(f"- **Vessel**: {result.title_block.vessel_name}")
    
    if result.title_block.project_name:
        summary_lines.append(f"- **Project**: {result.title_block.project_name}")
    
    if key_dims:
        summary_lines.append(f"- **Key Dimensions**:")
        for dim in key_dims:
            conf_pct = dim['confidence'] * 100
            summary_lines.append(f"  - {dim['name']}: {dim['value']} {dim['unit']} (confidence: {conf_pct:.0f}%)")
    
    if result.equipment_tags:
        summary_lines.append(f"- **Equipment Tags Found**: {len(result.equipment_tags)}")
    
    summary_lines.append(f"- **Overall Analysis Confidence**: {result.confidence.overall_confidence:.0%}")
    
    # Add quality indicator
    quality = result.confidence.get_quality_label()
    color = result.confidence.get_color_code()
    summary_lines.append(f"- **Quality**: <span style='color:{color}'>{quality}</span>")
    
    # Add recommendations if low confidence
    if result.confidence.overall_confidence < 0.70:
        summary_lines.append(f"")
        summary_lines.append(f"⚠️ *Manual review recommended — some extracted values may need verification.*")
    
    summary_text = "\n".join(summary_lines)
    
    return ChatDrawingAnalysis(
        drawing_type=result.drawing_type.value,
        type_confidence=result.drawing_type_confidence,
        vessel_name=result.title_block.vessel_name,
        drawing_number=result.title_block.drawing_number,
        key_dimensions=key_dims,
        equipment_count=len(result.equipment_tags),
        overall_confidence=result.confidence.overall_confidence,
        quality_label=result.confidence.get_quality_label(),
        summary_text=summary_text
    )


@router.post("/chat/analyze_drawing", response_model=ChatDrawingResponse)
async def chat_analyze_drawing(
    background_tasks: BackgroundTasks,
    image: UploadFile = File(...),
    db: Session = Depends(get_agent_db),
    user: dict = Depends(get_current_user),
):
    """
    Analyze a drawing from chat interface.
    Returns job ID for polling. Results formatted for chat display.
    """
    # Validate input
    is_pdf = image.content_type == "application/pdf"
    if not image.content_type.startswith("image/") and not is_pdf:
        raise HTTPException(status_code=400, detail="File must be an image or PDF")
    
    file_bytes = await image.read()
    if len(file_bytes) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File size exceeds 20MB limit")
    
    # Create job
    job = AsyncJob(
        job_type="chat_drawing_analysis",
        input_data={
            "filename": image.filename,
            "content_type": image.content_type,
            "requested_by": user.get("sub", "unknown")
        }
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    
    # Queue pipeline
    from api.models.models import SessionLocal
    background_tasks.add_task(
        run_drawing_analysis_pipeline,
        job.id,
        file_bytes,
        image.filename,
        image.content_type,
        SessionLocal()
    )
    
    logger.info(f"Chat drawing analysis started: job_id={job.id}, filename={image.filename}")
    
    return ChatDrawingResponse(
        job_id=job.id,
        status="pending",
        message=f"Analyzing {image.filename}... This typically takes 20-30 seconds.",
        preview=None
    )


@router.get("/chat/drawing_status/{job_id}", response_model=ChatDrawingResponse)
async def chat_drawing_status(
    job_id: str,
    db: Session = Depends(get_agent_db),
    user: dict = Depends(get_current_user),
):
    """
    Get status of chat drawing analysis job.
    Returns formatted result for chat display when complete.
    """
    job = db.query(AsyncJob).filter(AsyncJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # If completed, format for chat
    if job.status == "completed" and job.result_data:
        try:
            result = DrawingAnalysisResult(**job.result_data)
            chat_analysis = _format_drawing_for_chat(result)
            
            return ChatDrawingResponse(
                job_id=job.id,
                status="completed",
                message="Analysis complete",
                preview=chat_analysis
            )
        except Exception as e:
            logger.error(f"Failed to format drawing result for chat: {e}")
            return ChatDrawingResponse(
                job_id=job.id,
                status="error",
                message=f"Failed to format result: {str(e)}",
                preview=None
            )
    
    elif job.status == "failed":
        return ChatDrawingResponse(
            job_id=job.id,
            status="failed",
            message=f"Analysis failed: {job.error_message or 'Unknown error'}",
            preview=None
        )
    
    # Still processing
    return ChatDrawingResponse(
        job_id=job.id,
        status=job.status,
        message="Analysis in progress...",
        preview=None
    )

"""
AGRA Phase 2 — Router: Chat / Document Q&A
SSE-streamed conversational Q&A with RAG citations.
"""

import json
import logging
import asyncio
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.utils.auth_check import get_current_user
from api.rag.pipeline import query_pipeline

logger = logging.getLogger("agra.chat")

router = APIRouter()


class ChatMessage(BaseModel):
    role: str = Field(..., description="'user' or 'assistant'")
    content: str


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=5000)
    session_id: Optional[str] = None
    history: List[ChatMessage] = Field(default_factory=list)
    doc_id: Optional[str] = Field(None, description="Filter to a specific document")


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
        try:
            async for event in _async_query_wrapper(
                question=body.question,
                session_history=history,
                user_id=0,
                token=raw_token,
                doc_id_filter=body.doc_id,
            ):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            logger.error("Chat stream error: %s", e, exc_info=True)
            yield f"data: {json.dumps({'error': str(e), 'done': True})}\n\n"

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
    doc_id_filter: Optional[str],
):
    """
    Wraps and iterates over the async generator returned by query_pipeline.
    """
    async for event in query_pipeline(
        question=question,
        session_history=session_history,
        user_id=user_id,
        token=token,
        doc_id_filter=doc_id_filter,
    ):
        yield event
        # Yield control to event loop between tokens
        await asyncio.sleep(0)

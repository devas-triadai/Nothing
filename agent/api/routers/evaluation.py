"""
AGRA Module 2 — Evaluation API Router
REST endpoints for metrics, feedback, and query logging.
"""

from typing import List, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Query

from api.rag.evaluation_store import get_store, EvaluationStore

router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════════════
#  REQUEST/RESPONSE MODELS
# ═══════════════════════════════════════════════════════════════════════════════

class FeedbackRequest(BaseModel):
    query_id: str
    chunk_id: str
    relevance_score: int = Field(ge=0, le=2, description="0=not relevant, 1=partially relevant, 2=highly relevant")
    feedback_text: Optional[str] = None


class FeedbackResponse(BaseModel):
    id: str
    message: str = "Feedback recorded"


class MetricsResponse(BaseModel):
    period_days: int
    total_queries: int
    avg_response_time_ms: float
    
    # Retrieval metrics
    precision_at_5: float
    precision_at_10: float
    recall_at_5: float
    recall_at_10: float
    ndcg_at_10: float
    mrr: float
    queries_evaluated: int
    
    # Generation quality metrics
    avg_citation_accuracy: float
    avg_hallucination_rate: float
    
    # Confidence distribution
    high_confidence_pct: float
    medium_confidence_pct: float
    low_confidence_pct: float


class QueryWithChunks(BaseModel):
    id: str
    query_text: str
    user_id: int
    timestamp: str
    final_confidence_score: Optional[float]
    chunk_count: int


class ChunkWithFeedback(BaseModel):
    id: str
    chunk_id: str
    rank: int
    combined_score: float
    rerank_score: Optional[float]
    text_excerpt: str
    user_relevance: Optional[int] = None  # User feedback if exists


# ═══════════════════════════════════════════════════════════════════════════════
#  API ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/feedback", response_model=FeedbackResponse)
def submit_feedback(
    request: FeedbackRequest,
    store: EvaluationStore = Depends(get_store)
):
    """
    Submit user relevance feedback for a retrieved chunk.
    
    - **relevance_score**: 0=not relevant, 1=partially relevant, 2=highly relevant
    """
    try:
        feedback_id = store.add_feedback(
            query_id=request.query_id,
            chunk_id=request.chunk_id,
            relevance_score=request.relevance_score,
            feedback_text=request.feedback_text
        )
        return FeedbackResponse(id=feedback_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to record feedback: {str(e)}")


@router.get("/metrics", response_model=MetricsResponse)
def get_metrics(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to aggregate"),
    store: EvaluationStore = Depends(get_store)
):
    """
    Get aggregated evaluation metrics for the specified time period.
    
    Returns:
    - Retrieval metrics: Precision@k, Recall@k, NDCG@10, MRR
    - Generation metrics: Citation accuracy, Hallucination rate
    - Confidence distribution: High/Medium/Low percentages
    """
    try:
        metrics = store.get_metrics(days=days)
        return MetricsResponse(**metrics)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to compute metrics: {str(e)}")


@router.get("/queries")
def get_recent_queries(
    limit: int = Query(default=50, ge=1, le=100, description="Number of recent queries to return"),
    store: EvaluationStore = Depends(get_store)
):
    """
    Get recent queries with their metadata.
    """
    try:
        queries = store.get_recent_queries(limit=limit)
        return {"queries": queries, "total": len(queries)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch queries: {str(e)}")


@router.get("/queries/{query_id}/chunks")
def get_query_chunks(
    query_id: str,
    store: EvaluationStore = Depends(get_store)
):
    """
    Get all retrieved chunks for a specific query, including any user feedback.
    """
    try:
        # This would need a method in evaluation_store.py
        # For now, return placeholder
        return {
            "query_id": query_id,
            "chunks": [],
            "message": "Chunk retrieval not yet implemented"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch chunks: {str(e)}")


@router.get("/health")
def evaluation_health():
    """Health check for evaluation system."""
    try:
        store = get_store()
        # Try a simple query to verify DB is accessible
        metrics = store.get_metrics(days=1)
        return {
            "status": "healthy",
            "database": "connected",
            "recent_queries": metrics.get("total_queries", 0)
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }

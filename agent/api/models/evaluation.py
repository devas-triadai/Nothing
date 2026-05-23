"""
AGRA Module 2 — Evaluation Data Models
Query logging, feedback, and metrics tracking for RAG evaluation.
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class QueryLog(BaseModel):
    """Log of a user query for evaluation metrics."""
    id: Optional[str] = None
    query_text: str
    user_id: int
    session_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    doc_filter: Optional[List[str]] = None  # Filtered doc IDs if any
    category_filter: Optional[str] = None
    response_time_ms: Optional[float] = None
    final_confidence_score: Optional[float] = None
    

class RetrievedChunkLog(BaseModel):
    """Log of a retrieved chunk for a specific query."""
    id: Optional[str] = None
    query_id: str  # Foreign key to QueryLog
    chunk_id: str
    rank: int  # Position in retrieval results (1-indexed)
    dense_score: float
    bm25_score: float
    rerank_score: Optional[float] = None
    combined_score: float
    text_excerpt: str = Field(max_length=500)
    metadata: dict = Field(default_factory=dict)
    

class UserFeedback(BaseModel):
    """User relevance feedback for a retrieved chunk."""
    id: Optional[str] = None
    query_id: str
    chunk_id: str
    relevance_score: int = Field(ge=0, le=2, description="0=not relevant, 1=partially relevant, 2=highly relevant")
    feedback_text: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    

class CitationValidationLog(BaseModel):
    """Log of citation validation results."""
    id: Optional[str] = None
    query_id: str
    response_text: str = Field(max_length=10000)
    total_citations: int
    valid_citations: int
    invalid_citations: int
    unverified_claims: int
    citation_accuracy: float  # percentage
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    

class HallucinationDetectionLog(BaseModel):
    """Log of hallucination detection results."""
    id: Optional[str] = None
    query_id: str
    total_claims: int
    supported_claims: int
    unsupported_claims: int
    contradicted_claims: int
    hallucination_rate: float  # percentage
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    

class EvaluationMetricsSummary(BaseModel):
    """Aggregated evaluation metrics response."""
    period_days: int = 30
    total_queries: int
    avg_response_time_ms: float
    
    # Retrieval metrics
    precision_at_5: float
    precision_at_10: float
    recall_at_5: float
    recall_at_10: float
    ndcg_at_10: float
    mrr: float
    
    # Generation quality metrics
    avg_citation_accuracy: float
    avg_hallucination_rate: float
    
    # Confidence distribution
    high_confidence_pct: float  # score >= 0.7
    medium_confidence_pct: float  # 0.4 <= score < 0.7
    low_confidence_pct: float  # score < 0.4

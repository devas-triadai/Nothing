"""
AGRA Compliance Module Phase 1 — Pydantic Models
API request/response schemas for compliance endpoints.
"""

from datetime import datetime
from typing import Optional, List, Literal
from enum import Enum
from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════
#  ENUMS
# ═══════════════════════════════════════════════════════════════

class ComplianceStatus(str, Enum):
    """Status of a compliance evaluation."""
    CREATED = "created"
    PARSING_SOTR = "parsing_sotr"
    SCORING = "scoring"
    COMPLETED = "completed"
    FAILED = "failed"


class ClauseStatus(str, Enum):
    """Status of individual clause evaluation."""
    COMPLIANT = "compliant"
    PARTIAL = "partial"
    NON_COMPLIANT = "non_compliant"
    NOT_APPLICABLE = "not_applicable"
    PENDING = "pending"


class Recommendation(str, Enum):
    """Overall compliance recommendation."""
    ACCEPT = "accept"
    CONDITIONAL = "conditional"
    REJECT = "reject"


class ClauseCategory(str, Enum):
    """Category of SOTR clause."""
    TECHNICAL = "technical"
    COMMERCIAL = "commercial"
    SAFETY = "safety"
    GENERAL = "general"
    QUALITY = "quality"
    ENVIRONMENTAL = "environmental"


# ═══════════════════════════════════════════════════════════════
#  REQUEST MODELS
# ═══════════════════════════════════════════════════════════════

class ComplianceEvaluationRequest(BaseModel):
    """Request to create a new compliance evaluation."""
    sotr_doc_id: int = Field(..., description="Document ID of the SOTR")
    vendor_doc_id: int = Field(..., description="Document ID of the vendor submission")
    project_name: Optional[str] = Field(None, description="Project name")
    vessel_name: Optional[str] = Field(None, description="Vessel name")
    vendor_name: Optional[str] = Field(None, description="Vendor/supplier name")
    auto_start: bool = Field(default=False, description="Start evaluation immediately after creation")
    
    class Config:
        json_schema_extra = {
            "example": {
                "sotr_doc_id": 123,
                "vendor_doc_id": 456,
                "project_name": "OPV Construction Project",
                "vessel_name": "ICGS Sarthi",
                "vendor_name": "ABC Shipyard Ltd",
                "auto_start": True
            }
        }


class ClauseScoreRequest(BaseModel):
    """Request to update/override a clause score."""
    clause_id: int = Field(..., description="ID of the clause being scored")
    status: ClauseStatus = Field(..., description="Compliance status for this clause")
    notes: Optional[str] = Field(None, description="Reviewer notes")
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="Confidence in this score")
    
    class Config:
        json_schema_extra = {
            "example": {
                "clause_id": 789,
                "status": "compliant",
                "notes": "Vendor meets all requirements",
                "confidence": 0.95
            }
        }


class ComplianceReportRequest(BaseModel):
    """Request to generate a compliance report."""
    report_type: Literal["full", "summary", "technical_only", "commercial_only"] = Field(
        default="full",
        description="Type of report to generate"
    )
    include_appendix: bool = Field(default=True, description="Include full SOTR text in appendix")
    
    class Config:
        json_schema_extra = {
            "example": {
                "report_type": "full",
                "include_appendix": True
            }
        }


# ═══════════════════════════════════════════════════════════════
#  CLAUSE MODELS
# ═══════════════════════════════════════════════════════════════

class ComplianceClauseBase(BaseModel):
    """Base model for SOTR clause."""
    clause_number: str = Field(..., description="Clause number (e.g., '1.1', '2.3.1')")
    clause_title: Optional[str] = Field(None, description="Clause title")
    clause_text: str = Field(..., description="Full clause text")
    category: ClauseCategory = Field(default=ClauseCategory.GENERAL)
    subcategory: Optional[str] = Field(None)
    is_mandatory: bool = Field(default=True)
    is_critical: bool = Field(default=False)
    acceptance_criteria: Optional[str] = Field(None)
    
    class Config:
        json_schema_extra = {
            "example": {
                "clause_number": "1.2.1",
                "clause_title": "Hull Construction Standards",
                "clause_text": "The vessel hull shall be constructed...",
                "category": "technical",
                "is_mandatory": True,
                "is_critical": True,
                "acceptance_criteria": "Compliance with IRS rules"
            }
        }


class ComplianceClauseResponse(ComplianceClauseBase):
    """Full clause response with IDs and metadata."""
    id: int
    sotr_doc_id: int
    page_number: Optional[int] = None
    extraction_confidence: float = 0.0
    extracted_at: datetime
    
    class Config:
        from_attributes = True


# ═══════════════════════════════════════════════════════════════
#  CLAUSE SCORE MODELS
# ═══════════════════════════════════════════════════════════════

class ClauseScoreBase(BaseModel):
    """Base model for clause score."""
    status: ClauseStatus = Field(default=ClauseStatus.PENDING)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    vendor_response_summary: Optional[str] = None
    evidence_text: Optional[str] = None
    gaps_identified: Optional[str] = None
    deviation_notes: Optional[str] = None


class ClauseScoreResponse(ClauseScoreBase):
    """Full clause score response with clause details."""
    id: int
    evaluation_id: int
    clause_id: int
    clause: Optional[ComplianceClauseResponse] = None
    
    # Manual review
    manually_reviewed: bool = False
    reviewed_by: Optional[int] = None
    reviewed_at: Optional[datetime] = None
    reviewer_notes: Optional[str] = None
    
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# ═══════════════════════════════════════════════════════════════
#  EVALUATION RESPONSE MODELS
# ═══════════════════════════════════════════════════════════════

class ComplianceSummary(BaseModel):
    """Summary of compliance evaluation results."""
    total_clauses: int = 0
    compliant_count: int = 0
    partial_count: int = 0
    non_compliant_count: int = 0
    not_applicable_count: int = 0
    
    # Percentages
    compliance_percentage: float = Field(default=0.0, ge=0.0, le=100.0)
    
    @property
    def scored_clauses(self) -> int:
        return self.compliant_count + self.partial_count + self.non_compliant_count
    
    def get_category_breakdown(self) -> dict:
        """Return breakdown by category (populated dynamically)."""
        return {}


class ComplianceEvaluationResponse(BaseModel):
    """Full compliance evaluation response."""
    id: int
    sotr_doc_id: int
    vendor_doc_id: int
    status: ComplianceStatus
    
    # Metadata
    project_name: Optional[str] = None
    vessel_name: Optional[str] = None
    vendor_name: Optional[str] = None
    created_by: int
    
    # Results
    overall_score: Optional[float] = None
    recommendation: Optional[Recommendation] = None
    recommendation_notes: Optional[str] = None
    summary: ComplianceSummary
    
    # Clause scores (optional, for detailed view)
    clause_scores: Optional[List[ClauseScoreResponse]] = None
    
    # Timestamps
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class ComplianceListResponse(BaseModel):
    """List of evaluations with pagination."""
    evaluations: List[ComplianceEvaluationResponse]
    total: int
    page: int
    page_size: int


# ═══════════════════════════════════════════════════════════════
#  REPORT MODELS
# ═══════════════════════════════════════════════════════════════

class ComplianceReportResponse(BaseModel):
    """Compliance report metadata and download info."""
    id: int
    evaluation_id: int
    report_type: str
    
    # File info
    file_name: Optional[str] = None
    file_size_bytes: Optional[int] = None
    download_url: Optional[str] = None
    
    # Content
    summary_text: Optional[str] = None
    key_findings: Optional[List[str]] = None
    
    # Generation info
    generated_by: int
    generated_at: datetime
    version: int
    is_latest: bool
    
    class Config:
        from_attributes = True


# ═══════════════════════════════════════════════════════════════
#  SMART DETECTION MODELS
# ═══════════════════════════════════════════════════════════════

class SmartComplianceSuggestion(BaseModel):
    """Smart suggestion for compliance workflow."""
    detected_doc_type: str
    confidence: float
    suggested_action: str
    suggested_sotr_id: Optional[int] = None
    suggested_sotr_name: Optional[str] = None
    message: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "detected_doc_type": "bid_document",
                "confidence": 0.92,
                "suggested_action": "select_sotr",
                "suggested_sotr_id": 123,
                "suggested_sotr_name": "SOTR_OPV_Construction.pdf",
                "message": "Bid document detected. Select SOTR to check compliance."
            }
        }


# ═══════════════════════════════════════════════════════════════
#  WEBSOCKET/SSE MODELS (for real-time updates)
# ═══════════════════════════════════════════════════════════════

class ComplianceProgressUpdate(BaseModel):
    """Real-time progress update during evaluation."""
    evaluation_id: int
    status: ComplianceStatus
    progress_percent: int = Field(ge=0, le=100)
    current_action: str
    clauses_scored: int = 0
    total_clauses: int = 0
    estimated_seconds_remaining: Optional[int] = None


# ═══════════════════════════════════════════════════════════════
#  LEGACY/COMPATIBILITY MODELS
# ═══════════════════════════════════════════════════════════════

class SimpleComplianceResult(BaseModel):
    """Simplified result for quick checks."""
    compliant: bool
    score: float = Field(ge=0.0, le=1.0)
    key_issues: List[str]
    recommendation: str

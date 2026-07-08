from datetime import datetime
from typing import Optional, List, Literal
from enum import Enum
from pydantic import BaseModel, Field


class VerdictEnum(str, Enum):
    COMPLIANT = "COMPLIANT"
    PARTIAL = "PARTIAL"
    NON_COMPLIANT = "NON_COMPLIANT"
    UNVERIFIABLE = "UNVERIFIABLE"


class SeverityEnum(str, Enum):
    CRITICAL = "Critical"
    MAJOR = "Major"
    MINOR = "Minor"


class RecommendationEnum(str, Enum):
    APPROVE = "APPROVE"
    APPROVE_WITH_CONDITIONS = "APPROVE WITH CONDITIONS"
    REVISE_AND_RESUBMIT = "REVISE AND RESUBMIT"
    REJECT = "REJECT"


class Citation(BaseModel):
    doc_name: str = ""
    version: str = ""
    page: int = 0
    excerpt: str = ""


class HouseRuleFlag(BaseModel):
    violated: bool = False
    rule_reference: str = ""
    note: str = ""


class Contradiction(BaseModel):
    between: List[str] = []
    statement_a: str = ""
    statement_b: str = ""
    note: str = ""


class HistoricalNote(BaseModel):
    run_id: int = 0
    reference_name: str = ""
    previous_verdict: Optional[str] = None
    note: str = ""


class ClauseResultData(BaseModel):
    clause_id: str = ""
    source_file: str = ""
    source_doc_id: str = ""
    requirement_text: str = ""
    applicable_standards: List[str] = []
    technical_parameters: Optional[str] = None
    acceptance_criterion: str = ""
    verdict: Optional[VerdictEnum] = None
    finding: str = ""
    house_rule_flag: HouseRuleFlag = Field(default_factory=HouseRuleFlag)
    recommendation: Optional[RecommendationEnum] = None
    severity: Optional[SeverityEnum] = None
    citations: List[Citation] = []
    contradictions: List[Contradiction] = []
    is_missing: bool = False
    historical_notes: List[HistoricalNote] = []


class RunStatusEnum(str, Enum):
    QUEUED = "queued"
    INGESTING = "ingesting"
    PARSING_CLAUSES = "parsing_clauses"
    EVALUATING = "evaluating"
    AGGREGATING = "aggregating"
    GENERATING_REPORT = "generating_report"
    COMPLETE = "complete"
    FAILED = "failed"


class ProgressUpdate(BaseModel):
    stage: str = ""
    current: int = 0
    total: int = 0
    message: str = ""


class IngestBundleRequest(BaseModel):
    sotr_commercial_path: str
    sotr_technical_path: Optional[str] = None
    vendor_commercial_path: Optional[str] = None
    vendor_dpr_path: Optional[str] = None
    run_id: int = 0


class IngestBundleResponse(BaseModel):
    doc_id_sotr_com: str
    doc_id_sotr_tech: Optional[str] = None
    doc_id_vendor_com: Optional[str] = None
    doc_id_vendor_dpr: Optional[str] = None


class RunPipelineRequest(BaseModel):
    run_id: int = 0
    doc_id_sotr_com: str = ""
    doc_id_sotr_tech: Optional[str] = None
    doc_id_vendor_com: Optional[str] = None
    doc_id_vendor_dpr: Optional[str] = None
    selected_standards: List[str] = []
    reference_name: str = ""


class PipelineResult(BaseModel):
    clauses: List[ClauseResultData] = []
    total_clauses: int = 0
    compliant_count: int = 0
    partial_count: int = 0
    non_compliant_count: int = 0
    unverifiable_count: int = 0
    overall_score: float = 0.0
    recommendation: Optional[RecommendationEnum] = None
    missing_clause_count: int = 0
    contradiction_count: int = 0
    house_rule_violation_count: int = 0


class StandardsDocument(BaseModel):
    doc_id: str
    filename: str
    category: str = ""
    description: str = ""


# ═══════════════════════════════════════════════════════════════
#  Backward-compatible aliases for Phase 1 models (legacy RAG
#  import chain still references them via clause_scorer.py).
#  These are stub classes so the import resolves at startup.
#  The old evaluation code path is no longer used.
# ═══════════════════════════════════════════════════════════════

import typing as _typing


class ClauseStatus(str, Enum):
    PENDING = "pending"
    COMPLIANT = "compliant"
    PARTIAL = "partial"
    NON_COMPLIANT = "non_compliant"
    NOT_APPLICABLE = "not_applicable"


class ClauseCategory(str, Enum):
    GENERAL = "General"
    TECHNICAL = "Technical"
    COMMERCIAL = "Commercial"
    SAFETY = "Safety"
    QUALITY = "Quality"
    ENVIRONMENTAL = "Environmental"


class ClauseScoreBase(BaseModel):
    status: ClauseStatus = ClauseStatus.PENDING
    confidence: float = 0.0
    finding: str = ""
    severity: Optional[str] = None
    evidence_text: str = ""
    vendor_response_summary: str = ""
    gaps_identified: Optional[str] = None
    deviation_notes: Optional[str] = None
    is_missing: bool = False
    citation: str = ""
    recommendation: str = ""


class ComplianceClauseBase(BaseModel):
    clause_number: str = ""
    clause_title: str = ""
    clause_text: str = ""
    category: ClauseCategory = ClauseCategory.GENERAL
    is_mandatory: bool = False
    is_critical: bool = False
    acceptance_criteria: str = ""


class ComplianceEvaluationResponse(BaseModel):
    summary: str = ""
    total_clauses: int = 0
    compliant_count: int = 0
    partial_count: int = 0
    non_compliant_count: int = 0
    not_applicable_count: int = 0
    overall_score: float = 0.0
    clauses: _typing.List["ClauseScoreResponse"] = []


class ClauseScoreResponse(BaseModel):
    clause: "ComplianceClauseBase" = Field(default_factory=lambda: ComplianceClauseBase())
    score: "ClauseScoreBase" = Field(default_factory=lambda: ClauseScoreBase())

ClauseScoreResponse.model_rebuild()
ComplianceEvaluationResponse.model_rebuild()

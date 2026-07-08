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
    sotr_technical_path: str
    vendor_commercial_path: str
    vendor_dpr_path: str
    run_id: int = 0


class IngestBundleResponse(BaseModel):
    doc_id_sotr_com: str
    doc_id_sotr_tech: str
    doc_id_vendor_com: str
    doc_id_vendor_dpr: str


class RunPipelineRequest(BaseModel):
    run_id: int = 0
    doc_id_sotr_com: str
    doc_id_sotr_tech: str
    doc_id_vendor_com: str
    doc_id_vendor_dpr: str
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

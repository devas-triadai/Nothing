from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, Text, ForeignKey, Enum
from sqlalchemy.orm import relationship, backref
from datetime import datetime
import enum
from app.database import Base

class UserRole(str, enum.Enum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    OFFICER = "officer"
    VIEWER = "viewer"

class UserStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    full_name = Column(String(100), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), default=UserRole.VIEWER)
    status = Column(String(20), default=UserStatus.ACTIVE)
    department = Column(String(100), nullable=True)
    rank = Column(String(50), nullable=True)
    service_number = Column(String(50), nullable=True, unique=True)
    clearance_level = Column(Integer, default=1)  # 1: Unclassified, 2: Confidential, 3: Secret, 4: Top Secret
    is_superadmin = Column(Boolean, default=False)
    last_login = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")
    usage_logs = relationship("UsageLog", back_populates="user", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="user", cascade="all, delete-orphan")

class UserSession(Base):
    __tablename__ = "user_sessions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    session_token = Column(String(500), unique=True, nullable=False)
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    user = relationship("User", back_populates="sessions")

class UsageLog(Base):
    __tablename__ = "usage_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    action_type = Column(String(50), nullable=False)
    module = Column(String(50), nullable=True)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    response_time_ms = Column(Float, default=0.0)
    status = Column(String(20), default="success")
    metadata_ = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="usage_logs")

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String(100), nullable=False)
    resource_type = Column(String(50), nullable=True)
    resource_id = Column(String(50), nullable=True)
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    ip_address = Column(String(50), nullable=True)
    status = Column(String(20), default="success")
    created_at = Column(DateTime, default=datetime.utcnow)
    prev_hash = Column(String(64), nullable=True)  # Hash of the previous log
    curr_hash = Column(String(64), nullable=True)  # Hash of this log + prev_hash
    user = relationship("User", back_populates="audit_logs")

import hashlib
from sqlalchemy import event

@event.listens_for(AuditLog, 'before_insert')
def generate_audit_hash(mapper, connection, target):
    # Fetch the previous log's hash
    prev_log = connection.execute(
        target.__table__.select().order_by(target.__table__.c.id.desc()).limit(1)
    ).first()
    target.prev_hash = prev_log.curr_hash if prev_log else "0" * 64
    
    # Calculate current hash
    data_str = f"{target.user_id}{target.action}{target.resource_type}{target.resource_id}{target.new_value}{target.created_at}{target.prev_hash}"
    target.curr_hash = hashlib.sha256(data_str.encode()).hexdigest()

# Document model with lineage/versioning support
class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True, index=True)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_type = Column(String(20), nullable=False)  # pdf, docx, xlsx, pptx
    file_size = Column(Integer, default=0)  # bytes
    page_count = Column(Integer, default=0)
    status = Column(String(20), default="processing")  # processing, indexed, failed
    category = Column(String(100), nullable=True)
    sub_category = Column(String(100), nullable=True)  # fine-grained type
    tags = Column(Text, nullable=True)  # comma-separated auto-categorization tags
    description = Column(Text, nullable=True)
    sha256_hash = Column(String(64), nullable=True, index=True)  # SHA-256 for tamper detection & dedup
    source = Column(String(30), default="admin_upload")  # admin_upload, agent_upload, knowledge_base
    classification_confidence = Column(Float, default=0.0)  # auto-classification confidence (0-1)
    clearance_level = Column(Integer, default=1)  # Required clearance to read this document
    # --- Lineage / Version fields ---
    version = Column(Integer, default=1)          # version number within its group
    version_notes = Column(Text, nullable=True)   # what changed in this version
    doc_group_id = Column(String(64), nullable=True, index=True)  # UUID grouping all versions
    parent_doc_id = Column(Integer, ForeignKey("documents.id"), nullable=True)  # direct parent version
    qdrant_doc_id = Column(String(100), nullable=True, index=True)  # matching doc_id in Qdrant for cross-sync
    # --------------------------------
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # relationships
    child_versions = relationship("Document", foreign_keys=[parent_doc_id], backref=backref("parent_doc", remote_side=[id]), lazy="dynamic")

class DocEdgeType(str, enum.Enum):
    SUPERSEDES = "supersedes"
    DERIVED_FROM = "derived_from"
    INFORMED_BY = "informed_by"
    REFERENCES = "references"
    AMENDS = "amends"

class DocEdge(Base):
    __tablename__ = "doc_edges"
    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    target_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    edge_type = Column(String(50), nullable=False, default=DocEdgeType.REFERENCES)
    confidence = Column(Float, default=1.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    source_doc = relationship("Document", foreign_keys=[source_id], backref="outgoing_edges")
    target_doc = relationship("Document", foreign_keys=[target_id], backref="incoming_edges")


class ExtractedDocumentMetadata(Base):
    """Module 7: LLM-extracted metadata from document content."""
    __tablename__ = "extracted_document_metadata"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Core extracted fields (JSONB for flexibility)
    version_refs = Column(JSON, nullable=True)        # ["v1.0", "Rev 2", "Version 3.5"]
    cross_references = Column(JSON, nullable=True)    # [{"doc": "IMO SOLAS", "ref": "Ch II-2"}]
    amendment_dates = Column(JSON, nullable=True)   # ["2024-01-15", "2023-06-01"]
    effective_date = Column(Date, nullable=True)      # When this version takes effect
    supersession_info = Column(JSON, nullable=True)   # {"supersedes": "Doc A", "superseded_by": "Doc B"}
    
    # Technical entity extraction
    equipment_types = Column(JSON, nullable=True)     # ["fire pump", "smoke detector", "EPIRB"]
    ship_types = Column(JSON, nullable=True)          # ["cargo", "passenger", "tanker"]
    regulation_categories = Column(JSON, nullable=True) # ["safety", "environmental", "navigation"]
    
    # Extraction metadata
    extraction_confidence = Column(Float, default=0.0)  # 0.0-1.0 overall confidence
    extraction_metadata = Column(JSON, nullable=True)   # Extra extraction info (model version, etc.)
    extracted_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship
    document = relationship("Document", backref="extracted_metadata")


class DocumentChangeSummary(Base):
    """Module 7: LLM-generated change summary between document versions."""
    __tablename__ = "document_change_summaries"
    
    id = Column(Integer, primary_key=True, index=True)
    from_doc_id = Column(Integer, ForeignKey("documents.id"), nullable=False, index=True)
    to_doc_id = Column(Integer, ForeignKey("documents.id"), nullable=False, index=True)
    
    summary_text = Column(Text, nullable=False)       # One-paragraph executive summary
    major_changes = Column(JSON, nullable=True)       # ["Added Section 4.2", "Modified Table 3"]
    minor_changes = Column(JSON, nullable=True)       # ["Fixed typos in Section 1"]
    impact_assessment = Column(String(20), nullable=True)  # High, Medium, Low
    action_required = Column(Text, nullable=True)     # "Review new requirements before..."
    
    generated_by_llm = Column(Boolean, default=True)
    generated_at = Column(DateTime, default=datetime.utcnow)
    
    # For manual review/override
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)


class AgentConfig(Base):
    __tablename__ = "agent_configs"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    value = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class SystemMetric(Base):
    __tablename__ = "system_metrics"
    id = Column(Integer, primary_key=True, index=True)
    metric_name = Column(String(100), nullable=False)
    metric_value = Column(Float, default=0.0)
    unit = Column(String(20), nullable=True)
    recorded_at = Column(DateTime, default=datetime.utcnow)

class SystemSetting(Base):
    __tablename__ = "system_settings"
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ComplianceReport(Base):
    """SOTR Compliance evaluation reports for audit oversight"""
    __tablename__ = "compliance_reports"
    id = Column(Integer, primary_key=True, index=True)
    report_name = Column(String(255), nullable=False)
    sotr_doc_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    submission_doc_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    generated_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Compliance metrics
    total_clauses = Column(Integer, default=0)
    compliant_count = Column(Integer, default=0)
    partial_count = Column(Integer, default=0)
    non_compliant_count = Column(Integer, default=0)
    unverifiable_count = Column(Integer, default=0)
    compliance_score = Column(Float, default=0.0)  # 0-100%
    
    # Overall verdict
    verdict = Column(String(50), default="PENDING")  # APPROVE, APPROVE_WITH_CONDITIONS, REVISE_AND_RESUBMIT, REJECT
    
    # Report file path
    report_file_path = Column(String(500), nullable=True)
    
    status = Column(String(20), default="completed")  # pending, processing, completed, failed
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    sotr_doc = relationship("Document", foreign_keys=[sotr_doc_id])
    submission_doc = relationship("Document", foreign_keys=[submission_doc_id])
    generator = relationship("User", foreign_keys=[generated_by])


class HistoricalFeedback(Base):
    """Historical feedback entries for SOTR compliance audit trail"""
    __tablename__ = "historical_feedback"
    id = Column(Integer, primary_key=True, index=True)
    compliance_report_id = Column(Integer, ForeignKey("compliance_reports.id"), nullable=False)
    
    # Clause reference
    clause_id = Column(String(100), nullable=False)  # e.g., SOTR-7.4.1
    clause_reference = Column(Text, nullable=True)  # Full clause text
    
    # Feedback content
    feedback_text = Column(Text, nullable=False)  # The historical narrative
    
    # Referenced past documents
    referenced_sotr_id = Column(Integer, ForeignKey("documents.id"), nullable=True)
    referenced_evaluation_id = Column(Integer, ForeignKey("compliance_reports.id"), nullable=True)
    
    # Severity of the finding
    severity = Column(String(20), default="INFO")  # INFO, WARNING, CRITICAL
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    report = relationship("ComplianceReport", foreign_keys=[compliance_report_id], backref="feedback_entries")
    referenced_sotr = relationship("Document", foreign_keys=[referenced_sotr_id])


class DocumentEntity(Base):
    """Module 7 Phase 4: Extracted entities from documents for lineage tracking."""
    __tablename__ = "document_entities"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Entity classification
    entity_type = Column(String(50), nullable=False, index=True)  # equipment, ship_type, regulation, requirement, standard
    entity_name = Column(String(200), nullable=False)  # Original extracted name
    entity_normalized = Column(String(200), nullable=False, index=True)  # Normalized for matching
    
    # Context and location
    context = Column(Text, nullable=True)  # Surrounding text snippet
    chunk_index = Column(Integer, nullable=True)  # Which chunk this was found in
    page_number = Column(Integer, nullable=True)  # Page number if available
    
    # Extraction metadata
    extraction_confidence = Column(Float, default=0.0)  # 0.0-1.0
    extracted_by = Column(String(50), default="llm")  # llm, rule_based, manual
    extracted_at = Column(DateTime, default=datetime.utcnow)
    
    # For lineage tracking
    first_seen_in_version = Column(Integer, nullable=True)  # Document version where first seen
    evolves_from_entity_id = Column(Integer, ForeignKey("document_entities.id"), nullable=True)
    evolution_type = Column(String(50), nullable=True)  # renamed, redefined, deprecated, added
    
    # Semantic embedding for similarity search (optional, for advanced matching)
    embedding_vector = Column(JSON, nullable=True)  # Stored as JSON array
    
    # Relationships
    document = relationship("Document", backref="entities")
    evolves_from = relationship("DocumentEntity", remote_side=[id])
    
    def __repr__(self):
        return f"<DocumentEntity({self.entity_type}: {self.entity_name})>"


class EntitySearchLog(Base):
    """Module 7 Phase 4: Audit log for entity searches (security/compliance)."""
    __tablename__ = "entity_search_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    search_query = Column(String(200), nullable=False)
    entity_type_filter = Column(String(50), nullable=True)
    results_count = Column(Integer, default=0)
    
    # Search context
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    ip_address = Column(String(45), nullable=True)  # IPv6 compatible
    user_agent = Column(String(200), nullable=True)
    
    # For compliance
    cleared_entities = Column(JSON, nullable=True)  # List of entity IDs user had clearance to see


# Create GIN index for trigram search on entity_normalized
# Note: This is created via Alembic migration, not here directly


# ═══════════════════════════════════════════════════════════════
#  COMPLIANCE MODULE MODELS (Phase 1)
# ═══════════════════════════════════════════════════════════════

class ComplianceStatus(str, enum.Enum):
    """Status of a compliance evaluation."""
    CREATED = "created"
    PARSING_SOTR = "parsing_sotr"
    SCORING = "scoring"
    COMPLETED = "completed"
    FAILED = "failed"


class ClauseStatus(str, enum.Enum):
    """Status of individual clause evaluation."""
    COMPLIANT = "compliant"
    PARTIAL = "partial"
    NON_COMPLIANT = "non_compliant"
    NOT_APPLICABLE = "not_applicable"
    PENDING = "pending"


class ComplianceEvaluation(Base):
    """
    Compliance Module Phase 1: Main compliance evaluation session.
    Tracks SOTR vs vendor submission evaluation workflow.
    """
    __tablename__ = "compliance_evaluations"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Document references
    sotr_doc_id = Column(Integer, ForeignKey("documents.id"), nullable=False, index=True)
    vendor_doc_id = Column(Integer, ForeignKey("documents.id"), nullable=False, index=True)
    
    # Status tracking
    status = Column(String(20), default=ComplianceStatus.CREATED, nullable=False)
    
    # Metadata
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    project_name = Column(String(200), nullable=True)
    vessel_name = Column(String(100), nullable=True)
    vendor_name = Column(String(100), nullable=True)
    
    # Results summary (populated when completed)
    overall_score = Column(Float, nullable=True)  # 0.0-1.0 percentage
    compliant_count = Column(Integer, default=0)
    partial_count = Column(Integer, default=0)
    non_compliant_count = Column(Integer, default=0)
    not_applicable_count = Column(Integer, default=0)
    total_clauses = Column(Integer, default=0)
    
    # Recommendation
    recommendation = Column(String(20), nullable=True)  # accept, conditional, reject
    recommendation_notes = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    # Relationships
    sotr_document = relationship("Document", foreign_keys=[sotr_doc_id], backref="sotr_evaluations")
    vendor_document = relationship("Document", foreign_keys=[vendor_doc_id], backref="vendor_evaluations")
    creator = relationship("User", backref="compliance_evaluations")
    clause_scores = relationship("ClauseScore", back_populates="evaluation", cascade="all, delete-orphan")
    reports = relationship("ComplianceReport", back_populates="evaluation", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<ComplianceEvaluation({self.id}: {self.status})>"


class ComplianceClause(Base):
    """
    Compliance Module Phase 1: Extracted SOTR clause.
    Represents a single requirement from SOTR document.
    """
    __tablename__ = "compliance_clauses"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Link to SOTR document
    sotr_doc_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Clause identification
    clause_number = Column(String(20), nullable=False, index=True)  # e.g., "1.1", "1.2.1"
    clause_title = Column(String(200), nullable=True)
    clause_text = Column(Text, nullable=False)
    
    # Categorization
    category = Column(String(50), nullable=True, index=True)  # technical, commercial, safety, general
    subcategory = Column(String(50), nullable=True)
    
    # Requirement type
    is_mandatory = Column(Boolean, default=True)
    is_critical = Column(Boolean, default=False)  # Critical to safety/operation
    
    # Extraction metadata
    acceptance_criteria = Column(Text, nullable=True)
    extracted_at = Column(DateTime, default=datetime.utcnow)
    extraction_confidence = Column(Float, default=0.0)
    
    # Source location
    page_number = Column(Integer, nullable=True)
    chunk_index = Column(Integer, nullable=True)
    
    # Relationships
    sotr_document = relationship("Document", backref="extracted_clauses")
    scores = relationship("ClauseScore", back_populates="clause")
    
    def __repr__(self):
        return f"<ComplianceClause({self.clause_number}: {self.clause_title or 'Untitled'})>"


class ClauseScore(Base):
    """
    Compliance Module Phase 1: Evaluation result for a single clause.
    Links evaluation + clause + vendor response.
    """
    __tablename__ = "clause_scores"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Foreign keys
    evaluation_id = Column(Integer, ForeignKey("compliance_evaluations.id", ondelete="CASCADE"), nullable=False, index=True)
    clause_id = Column(Integer, ForeignKey("compliance_clauses.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Scoring
    status = Column(String(20), default=ClauseStatus.PENDING, nullable=False, index=True)
    confidence = Column(Float, default=0.0)  # 0.0-1.0 confidence in this score
    
    # Vendor response analysis
    vendor_response_summary = Column(Text, nullable=True)
    evidence_text = Column(Text, nullable=True)  # Excerpt from vendor doc
    evidence_chunk_id = Column(String(50), nullable=True)  # Reference to vector store chunk
    
    # Gap analysis
    gaps_identified = Column(Text, nullable=True)
    deviation_notes = Column(Text, nullable=True)
    
    # Missing clause detection — vendor silently skipped this requirement
    is_missing = Column(Boolean, default=False)
    
    # Manual review
    manually_reviewed = Column(Boolean, default=False)
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    reviewer_notes = Column(Text, nullable=True)
    
    # LLM analysis metadata
    llm_raw_response = Column(Text, nullable=True)  # Store full LLM output for audit
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    evaluation = relationship("ComplianceEvaluation", back_populates="clause_scores")
    clause = relationship("ComplianceClause", back_populates="scores")
    reviewer = relationship("User")
    
    def __repr__(self):
        return f"<ClauseScore(Eval:{self.evaluation_id}, Clause:{self.clause_id}, {self.status})>"


class ComplianceReport(Base):
    """
    Compliance Module Phase 1: Generated compliance report.
    Stores metadata about PDF/JSON reports.
    """
    __tablename__ = "compliance_reports"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Link to evaluation
    evaluation_id = Column(Integer, ForeignKey("compliance_evaluations.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Report metadata
    report_type = Column(String(20), default="full", nullable=False)  # full, summary, technical_only
    file_name = Column(String(255), nullable=True)
    file_path = Column(String(500), nullable=True)
    file_size_bytes = Column(Integer, nullable=True)
    
    # Report content summary
    summary_text = Column(Text, nullable=True)
    key_findings = Column(Text, nullable=True)  # JSON array as text
    
    # Generation metadata
    generated_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    generated_at = Column(DateTime, default=datetime.utcnow, index=True)
    generation_time_ms = Column(Float, nullable=True)
    
    # Versioning
    version = Column(Integer, default=1)
    is_latest = Column(Boolean, default=True, index=True)
    
    # Relationships
    evaluation = relationship("ComplianceEvaluation", back_populates="reports")
    generator = relationship("User")
    
    def __repr__(self):
        return f"<ComplianceReport({self.id}: Eval {self.evaluation_id}, v{self.version})>"


# Compliance indexes for performance
# Note: Additional indexes created via Alembic migrations

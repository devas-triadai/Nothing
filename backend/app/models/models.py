from sqlalchemy import Column, Integer, String, Boolean, DateTime, Date, Float, Text, ForeignKey, Enum, JSON
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
    # --- Enhanced fields ---
    ocr_status = Column(String(20), default="pending")  # pending, processing, completed, failed
    expiry_date = Column(DateTime, nullable=True)
    full_text = Column(Text, nullable=True)  # Extracted text content for full-text search
    folder_id = Column(Integer, ForeignKey("document_folders.id"), nullable=True, index=True)
    # --------------------------------
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # relationships
    child_versions = relationship("Document", foreign_keys=[parent_doc_id], backref=backref("parent_doc", remote_side=[id]), lazy="dynamic")

class DocumentFolder(Base):
    __tablename__ = "document_folders"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    parent_id = Column(Integer, ForeignKey("document_folders.id"), nullable=True)
    color = Column(String(20), default="#6b7280")
    icon = Column(String(50), default="folder")
    created_at = Column(DateTime, default=datetime.utcnow)
    children = relationship("DocumentFolder", backref=backref("parent", remote_side=[id]), lazy="dynamic")
    documents = relationship("Document", backref="folder", lazy="dynamic")


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


class ComplianceEvaluation(Base):
    """Compliance evaluation: SOTR vs Vendor Submission."""
    __tablename__ = "compliance_evaluations"

    id = Column(Integer, primary_key=True, index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    sotr_doc_id = Column(String(100), nullable=False)
    vendor_doc_id = Column(String(100), nullable=False)
    project_name = Column(String(200), nullable=True)
    vessel_name = Column(String(200), nullable=True)
    vendor_name = Column(String(200), nullable=True)
    status = Column(String(20), default="pending")
    overall_score = Column(Float, nullable=True)
    compliant_count = Column(Integer, default=0)
    partial_count = Column(Integer, default=0)
    non_compliant_count = Column(Integer, default=0)
    not_applicable_count = Column(Integer, default=0)
    total_clauses = Column(Integer, default=0)
    recommendation = Column(String(20), nullable=True)
    report_pdf_path = Column(String(500), nullable=True)
    agent_eval_id = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    scores = relationship("ClauseScore", back_populates="evaluation", cascade="all, delete-orphan")


class ClauseScore(Base):
    """Individual clause scoring result within a compliance evaluation."""
    __tablename__ = "clause_scores"

    id = Column(Integer, primary_key=True, index=True)
    evaluation_id = Column(Integer, ForeignKey("compliance_evaluations.id", ondelete="CASCADE"), nullable=False)
    clause_number = Column(String(50), nullable=True)
    clause_title = Column(String(200), nullable=True)
    clause_text = Column(Text, nullable=True)
    category = Column(String(50), nullable=True)
    subcategory = Column(String(50), nullable=True)
    is_mandatory = Column(Boolean, default=True)
    is_critical = Column(Boolean, default=False)
    status = Column(String(20), default="pending")
    confidence = Column(Float, nullable=True)
    evidence_text = Column(Text, nullable=True)
    gaps_identified = Column(Text, nullable=True)
    vendor_response_summary = Column(Text, nullable=True)
    recommendation = Column(String(50), nullable=True)
    ai_notes = Column(Text, nullable=True)
    manually_overridden = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    evaluation = relationship("ComplianceEvaluation", back_populates="scores")


# Create GIN index for trigram search on entity_normalized
# Note: This is created via Alembic migration, not here directly



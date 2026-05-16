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

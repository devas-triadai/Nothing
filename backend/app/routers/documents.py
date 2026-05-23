from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime
import hashlib
import logging
import uuid
import os
import re
import httpx

from app.database import get_db
from app.models.models import User, Document, AuditLog, DocEdge
from app.routers.auth import require_superadmin, require_admin, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()

# Directory for uploaded files — persistent across pod restarts
# Uses same agra_data dir as the database
from pathlib import Path as _Path
_DATA_DIR = _Path(os.environ.get("AGRA_DATA_DIR", "/workspace/agra_data"))
if not _DATA_DIR.exists():
    _DATA_DIR = _Path(__file__).resolve().parent.parent.parent / "agra_data"
UPLOAD_DIR = str(_DATA_DIR / "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Agent API endpoint for ingestion
_AGENT_BASE = os.getenv("AGENT_BASE_URL", "http://localhost:8005")


class DocumentUpdate(BaseModel):
    category: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    version_notes: Optional[str] = None


def _doc_to_dict(doc: Document, db: Session) -> dict:
    """Serialize a Document ORM object to dict."""
    uploader = db.query(User).filter(User.id == doc.uploaded_by).first()
    return {
        "id": doc.id,
        "filename": doc.filename,
        "original_filename": doc.original_filename,
        "file_type": doc.file_type,
        "file_size": doc.file_size,
        "page_count": doc.page_count,
        "status": doc.status,
        "category": doc.category,
        "sub_category": doc.sub_category,
        "tags": doc.tags,
        "description": doc.description,
        "sha256_hash": doc.sha256_hash,
        "source": doc.source,
        "classification_confidence": doc.classification_confidence,
        "version": doc.version,
        "version_notes": doc.version_notes,
        "doc_group_id": doc.doc_group_id,
        "parent_doc_id": doc.parent_doc_id,
        "qdrant_doc_id": doc.qdrant_doc_id,
        "uploaded_by": uploader.username if uploader else "unknown",
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
        "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
    }


# ─── List documents ──────────────────────────────────────────────────────────
@router.get("/")
def list_documents(
    skip: int = 0,
    limit: int = 50,
    status: Optional[str] = None,
    file_type: Optional[str] = None,
    category: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin)
):
    query = db.query(Document)
    if status:
        query = query.filter(Document.status == status)
    if file_type:
        query = query.filter(Document.file_type == file_type)
    if category:
        query = query.filter(Document.category == category)
    total = query.count()
    docs = query.order_by(Document.created_at.desc()).offset(skip).limit(limit).all()
    return {"total": total, "documents": [_doc_to_dict(d, db) for d in docs]}


# ─── Upload new document (or new version of existing) ────────────────────────
@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    category: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    version_notes: Optional[str] = Form(None),
    parent_doc_id: Optional[int] = Form(None),
    source: Optional[str] = Form("admin_upload"),
    qdrant_doc_id: Optional[str] = Form(None),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin)
):
    # Determine file type from extension
    ext = os.path.splitext(file.filename)[1].lower().lstrip(".")
    allowed = {"pdf", "docx", "doc", "txt", "xlsx", "pptx", "png", "jpg", "jpeg"}
    if ext not in allowed:
        raise HTTPException(status_code=400, detail=f"File type '.{ext}' not allowed")

    # Read file content
    content = await file.read()
    file_size = len(content)

    # SHA-256 hash for tamper detection and dedup
    sha256 = hashlib.sha256(content).hexdigest()

    # Dedup check — skip if identical hash already exists
    existing = db.query(Document).filter(Document.sha256_hash == sha256).first()
    if existing and not parent_doc_id:
        return {"message": "Duplicate detected", "duplicate_of": _doc_to_dict(existing, db), "sha256": sha256}

    # Auto-classification — no mandatory category dropdown
    detected_category = category
    detected_sub = ""
    detected_tags = ""
    detected_conf = 0.0
    detected_summary = description or ""

    if not category:
        # Try to read text preview for content-based classification
        content_preview = ""
        try:
            if ext == "txt":
                content_preview = content.decode("utf-8", errors="replace")[:3000]
            elif ext in ("pdf", "docx"):
                # For binary files, use filename-only classification (Tier 1)
                # Full content classification happens after ingestion
                pass
        except Exception:
            pass
        detected_category, detected_tags = _auto_detect_category(file.filename, ext)
        detected_conf = 0.75 if detected_category != "General" else 0.30

    # Determine doc_group_id and version number
    if parent_doc_id:
        parent = db.query(Document).filter(Document.id == parent_doc_id).first()
        if not parent:
            raise HTTPException(status_code=404, detail="Parent document not found")
        doc_group_id = parent.doc_group_id or str(parent.id)
        latest = (
            db.query(Document)
            .filter(Document.doc_group_id == doc_group_id)
            .order_by(Document.version.desc())
            .first()
        )
        version = (latest.version if latest else 1) + 1
    else:
        doc_group_id = str(uuid.uuid4())
        version = 1

    # Save to disk
    safe_name = f"{doc_group_id}_v{version}_{file.filename}"
    file_path = os.path.join(UPLOAD_DIR, safe_name)
    with open(file_path, "wb") as f:
        f.write(content)

    # Create DB record
    doc = Document(
        uploaded_by=current_user.id,
        filename=safe_name,
        original_filename=file.filename,
        file_type=ext,
        file_size=file_size,
        status="indexed",
        category=detected_category or category,
        sub_category=detected_sub,
        tags=detected_tags,
        description=detected_summary or description,
        sha256_hash=sha256,
        source=source or "admin_upload",
        classification_confidence=detected_conf,
        version=version,
        version_notes=version_notes,
        doc_group_id=doc_group_id,
        parent_doc_id=parent_doc_id,
        qdrant_doc_id=qdrant_doc_id,
    )
    db.add(doc)

    audit = AuditLog(
        user_id=current_user.id,
        action="UPLOAD_DOCUMENT",
        resource_type="document",
        new_value=file.filename,
        status="success"
    )
    db.add(audit)
    db.commit()
    db.refresh(doc)

    # ── Trigger Agent ingestion in background (Single Source of Truth) ──
    async def _call_agent_ingest():
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{_AGENT_BASE}/api/agent/admin/ingest",
                    data={
                        "file_path": file_path,
                        "filename": file.filename,
                        "doc_id": doc.qdrant_doc_id or str(doc.id),
                        "category": doc.category,
                        "description": doc.description,
                        "parent_doc_id": str(parent_doc_id) if parent_doc_id else None,
                        "version_notes": version_notes,
                    },
                )
                resp.raise_for_status()
                logger.info("Triggered agent ingestion for %s (doc_id=%s)", file.filename, doc.qdrant_doc_id)
        except Exception as e:
            logger.error("Failed to trigger agent ingestion for %s: %s", file.filename, e)

    background_tasks.add_task(_call_agent_ingest)

    return {"message": "Document uploaded", "document": _doc_to_dict(doc, db)}


# ─── All lineage trees (for the full lineage graph view) ─────────────────────
# MUST be defined BEFORE parameterized routes like /{doc_id} so FastAPI
# does not try to parse "lineage" as an integer doc_id.
@router.get("/lineage/all")
def get_all_lineage(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin)
):
    all_docs = db.query(Document).order_by(Document.created_at.asc()).all()
    nodes = [_doc_to_dict(d, db) for d in all_docs]
    edges = [
        {"from": d.parent_doc_id, "to": d.id}
        for d in all_docs
        if d.parent_doc_id is not None
    ]
    return {"nodes": nodes, "edges": edges}


# ─── Check superseded documents ──────────────────────────────────────────────
# MUST be defined BEFORE parameterized routes like /{doc_id} so FastAPI
# does not try to parse "check-superseded" as an integer doc_id.
@router.get("/check-superseded")
def check_superseded(
    doc_ids: List[str] = Query([]),
    db: Session = Depends(get_db)
):
    """Check if any of the provided Qdrant doc_ids have been superseded."""
    if not doc_ids:
        return {"superseded": {}}

    # Find matching PostgreSQL documents
    docs = db.query(Document).filter(Document.qdrant_doc_id.in_(doc_ids)).all()

    result = {}
    for d in docs:
        # Check if there is a child version
        child = db.query(Document).filter(Document.parent_doc_id == d.id).first()
        if child:
            result[d.qdrant_doc_id] = {
                "superseded_by_id": child.id,
                "superseded_by_name": child.original_filename
            }
            continue

        # Check explicit edges
        edge = db.query(DocEdge).filter(
            DocEdge.source_id == d.id,
            DocEdge.edge_type == DocEdgeType.SUPERSEDES
        ).first()

        if edge:
            target = db.query(Document).filter(Document.id == edge.target_id).first()
            if target:
                result[d.qdrant_doc_id] = {
                    "superseded_by_id": target.id,
                    "superseded_by_name": target.original_filename
                }

    return {"superseded": result}


# ─── Get single document ──────────────────────────────────────────────────────
@router.get("/{doc_id}")
def get_document(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin)
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return _doc_to_dict(doc, db)


# ─── Version history for a doc group ─────────────────────────────────────────
@router.get("/{doc_id}/versions")
def get_version_history(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin)
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    group_id = doc.doc_group_id
    if not group_id:
        # Standalone document with no group
        return {"versions": [_doc_to_dict(doc, db)]}
    versions = (
        db.query(Document)
        .filter(Document.doc_group_id == group_id)
        .order_by(Document.version.asc())
        .all()
    )
    return {"group_id": group_id, "versions": [_doc_to_dict(v, db) for v in versions]}


# ─── Full lineage tree (ancestor + descendants) for a document ────────────────
@router.get("/{doc_id}/lineage")
def get_lineage_tree(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin)
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    group_id = doc.doc_group_id
    if not group_id:
        return {"nodes": [_doc_to_dict(doc, db)], "edges": []}

    all_docs = (
        db.query(Document)
        .filter(Document.doc_group_id == group_id)
        .order_by(Document.version.asc())
        .all()
    )

    nodes = [_doc_to_dict(d, db) for d in all_docs]
    edges = [
        {"from": d.parent_doc_id, "to": d.id}
        for d in all_docs
        if d.parent_doc_id is not None
    ]
    return {"group_id": group_id, "nodes": nodes, "edges": edges}


# ─── Update document metadata ─────────────────────────────────────────────────
@router.put("/{doc_id}")
def update_document(
    doc_id: int,
    doc_data: DocumentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin)
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    update_data = doc_data.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(doc, key, value)
    doc.updated_at = datetime.utcnow()
    db.commit()
    return {"message": "Document updated", "document": _doc_to_dict(doc, db)}


# ─── Delete document ──────────────────────────────────────────────────────────
@router.delete("/{doc_id}")
def delete_document(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin)
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    original_name = doc.original_filename
    # Remove children references
    db.query(Document).filter(Document.parent_doc_id == doc_id).update(
        {"parent_doc_id": None}
    )
    db.delete(doc)
    audit = AuditLog(
        user_id=current_user.id,
        action="DELETE_DOCUMENT",
        resource_type="document",
        resource_id=str(doc_id),
        old_value=original_name,
        status="success"
    )
    db.add(audit)
    db.commit()
    return {"message": "Document deleted"}


# ─── Download document file ───────────────────────────────────────────────────
@router.get("/{doc_id}/download")
def download_document(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    file_path = os.path.join(UPLOAD_DIR, doc.filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found on disk")
    return FileResponse(
        path=file_path,
        filename=doc.original_filename,
        media_type="application/octet-stream"
    )


# ─── Bulk upload multiple documents ──────────────────────────────────────────
@router.post("/upload/bulk")
async def bulk_upload_documents(
    files: List[UploadFile] = File(...),
    category: Optional[str] = Form(None),
    auto_categorize: bool = Form(True),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin)
):
    allowed = {"pdf", "docx", "doc", "txt", "xlsx", "pptx", "png", "jpg", "jpeg"}
    results = []
    for file in files:
        ext = os.path.splitext(file.filename)[1].lower().lstrip(".")
        if ext not in allowed:
            results.append({"filename": file.filename, "status": "skipped", "reason": f"Type '.{ext}' not allowed"})
            continue
        content = await file.read()
        file_size = len(content)

        # SHA-256 dedup
        sha256 = hashlib.sha256(content).hexdigest()
        existing = db.query(Document).filter(Document.sha256_hash == sha256).first()
        if existing:
            results.append({"filename": file.filename, "status": "duplicate", "duplicate_of": existing.id})
            continue

        doc_group_id = str(uuid.uuid4())
        safe_name = f"{doc_group_id}_v1_{file.filename}"
        file_path = os.path.join(UPLOAD_DIR, safe_name)
        with open(file_path, "wb") as f:
            f.write(content)

        # Auto-categorize based on filename + extension patterns
        detected_category = category
        detected_tags = ""
        detected_conf = 0.0
        if auto_categorize and not category:
            detected_category, detected_tags = _auto_detect_category(file.filename, ext)
            detected_conf = 0.75 if detected_category != "General" else 0.30

        doc = Document(
            uploaded_by=current_user.id,
            filename=safe_name,
            original_filename=file.filename,
            file_type=ext,
            file_size=file_size,
            status="indexed",
            category=detected_category,
            tags=detected_tags,
            sha256_hash=sha256,
            source="admin_upload",
            classification_confidence=detected_conf,
            version=1,
            doc_group_id=doc_group_id,
        )
        db.add(doc)
        db.flush()  # Get doc.id without committing yet
        results.append({"filename": file.filename, "status": "uploaded", "category": detected_category, "tags": detected_tags, "confidence": detected_conf, "doc_id": doc.id})

        # ── Trigger Agent ingestion for this file (Single Source of Truth) ──
        async def _call_agent_ingest_one():
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(
                        f"{_AGENT_BASE}/api/agent/admin/ingest",
                        data={
                            "file_path": file_path,
                            "filename": file.filename,
                            "doc_id": doc.qdrant_doc_id or str(doc.id),
                            "category": doc.category,
                            "description": doc.description,
                            "parent_doc_id": None,
                            "version_notes": None,
                        },
                    )
                    resp.raise_for_status()
                    logger.info("Triggered agent ingestion for bulk file %s (doc_id=%s)", file.filename, doc.qdrant_doc_id)
            except Exception as e:
                logger.error("Failed to trigger agent ingestion for bulk file %s: %s", file.filename, e)

        background_tasks.add_task(_call_agent_ingest_one)

    audit = AuditLog(
        user_id=current_user.id,
        action="BULK_UPLOAD",
        resource_type="document",
        new_value=f"{len(results)} files",
        status="success"
    )
    db.add(audit)
    db.commit()
    return {"message": f"{len(results)} files processed", "results": results}


# ─── Auto-categorize a single existing document ─────────────────────────────
@router.post("/{doc_id}/auto-categorize")
def auto_categorize_document(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin)
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    detected_category, detected_tags = _auto_detect_category(doc.original_filename, doc.file_type)
    doc.category = detected_category
    doc.tags = detected_tags
    doc.updated_at = datetime.utcnow()
    db.commit()
    return {"message": "Auto-categorized", "category": detected_category, "tags": detected_tags, "document": _doc_to_dict(doc, db)}


# ─── Auto-categorize ALL uncategorized documents ────────────────────────────
@router.post("/auto-categorize/all")
def auto_categorize_all(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin)
):
    uncategorized = db.query(Document).filter(
        (Document.category == None) | (Document.category == "") | (Document.category == "Uncategorised")
    ).all()
    count = 0
    for doc in uncategorized:
        cat, tags = _auto_detect_category(doc.original_filename, doc.file_type)
        doc.category = cat
        doc.tags = tags
        doc.updated_at = datetime.utcnow()
        count += 1
    db.commit()
    return {"message": f"Auto-categorized {count} documents", "processed": count}


# ═══════════════════════════════════════════════════════════════════════════════
#  AUTO-CATEGORIZATION ENGINE (Pattern-based, offline, no LLM required)
# ═══════════════════════════════════════════════════════════════════════════════

_CATEGORY_PATTERNS = [
    # Standards & Specifications
    (r"(?i)(SOTR|SOR|specification|standard|requirement|norm|ISO|BIS|MIL-STD|ABS|LR|DNV|IRS|IACS)", "Standard", "specification,requirements"),
    # Blueprints & Engineering Drawings
    (r"(?i)(blueprint|drawing|GA|general.arrangement|piping|schematic|diagram|layout|assembly|cross.section|structural)", "Blueprint", "engineering,drawing"),
    # Operational Documents
    (r"(?i)(SOP|operational|procedure|manual|guideline|protocol|instruction|checklist)", "SOP", "operational,procedure"),
    # Reports
    (r"(?i)(report|analysis|assessment|survey|inspection|audit|finding|observation|review)", "Report", "report,assessment"),
    # Compliance & Regulatory
    (r"(?i)(compliance|regulation|rule|act|policy|circular|notification|amendment|addendum)", "Compliance", "regulatory,compliance"),
    # Technical Proposals & Bids
    (r"(?i)(proposal|bid|tender|quotation|RFP|RFQ|techno.commercial|price.bid|commercial)", "Bid Document", "procurement,tender"),
    # Imagery & Visual
    (r"(?i)(image|photo|picture|screenshot|scan)", "Imagery", "visual,scan"),
    # Missile / Weapon Systems (defense-specific)
    (r"(?i)(missile|weapon|torpedo|gun|armament|munition|ordnance|warhead)", "Weapon System", "defense,armament"),
    # Ship / Vessel
    (r"(?i)(ship|vessel|OPV|patrol|frigate|corvette|hull|propulsion|engine|machinery)", "Vessel Document", "naval,ship"),
    # Training & HR
    (r"(?i)(training|course|syllabus|HR|human.resource|personnel|roster|leave)", "Training", "training,personnel"),
]


def _auto_detect_category(filename: str, file_type: str) -> tuple:
    """Detect category and tags from filename patterns. Returns (category, tags_csv)."""
    # Image files → Imagery
    if file_type in ("png", "jpg", "jpeg"):
        return "Imagery", "visual,scan,image"

    # Spreadsheet → likely data/report
    if file_type in ("xlsx", "xls", "csv"):
        return "Report", "data,spreadsheet"

    # Presentation
    if file_type in ("pptx", "ppt"):
        return "Presentation", "slides,briefing"

    # Check filename against pattern library
    for pattern, category, tags in _CATEGORY_PATTERNS:
        if re.search(pattern, filename):
            return category, tags

    # Fallback
    return "General", "uncategorized"


# ═══════════════════════════════════════════════════════════════════════════════
#  AGENT → ADMIN REGISTRATION (for unified doc visibility)
# ═══════════════════════════════════════════════════════════════════════════════

class AgentDocRegistration(BaseModel):
    filename: str
    file_type: str
    file_size: int = 0
    category: Optional[str] = None
    sub_category: Optional[str] = None
    tags: Optional[str] = None
    description: Optional[str] = None
    sha256_hash: Optional[str] = None
    source: str = "knowledge_base"
    classification_confidence: float = 0.0
    qdrant_doc_id: Optional[str] = None


@router.post("/register-agent-doc")
def register_agent_doc(
    body: AgentDocRegistration,
    db: Session = Depends(get_db),
):
    """
    Register a document ingested by the agent service into admin PostgreSQL.
    Used by auto_ingest and agent upload to maintain unified visibility.
    No auth required — internal service-to-service call.
    """
    # Dedup by qdrant_doc_id or sha256
    if body.qdrant_doc_id:
        existing = db.query(Document).filter(Document.qdrant_doc_id == body.qdrant_doc_id).first()
        if existing:
            return {"message": "Already registered", "document_id": existing.id}

    if body.sha256_hash:
        existing = db.query(Document).filter(Document.sha256_hash == body.sha256_hash).first()
        if existing:
            # Update qdrant_doc_id if not set
            if body.qdrant_doc_id and not existing.qdrant_doc_id:
                existing.qdrant_doc_id = body.qdrant_doc_id
                db.commit()
            return {"message": "Already registered (hash match)", "document_id": existing.id}

    # Get the first superadmin user as the uploader (system upload)
    system_user = db.query(User).filter(User.is_superadmin == True).first()
    uploader_id = system_user.id if system_user else 1

    doc = Document(
        uploaded_by=uploader_id,
        filename=body.filename,
        original_filename=body.filename,
        file_type=body.file_type,
        file_size=body.file_size,
        status="indexed",
        category=body.category or "General",
        sub_category=body.sub_category or "",
        tags=body.tags or "",
        description=body.description or "",
        sha256_hash=body.sha256_hash or "",
        source=body.source,
        classification_confidence=body.classification_confidence,
        version=1,
        doc_group_id=str(uuid.uuid4()),
        qdrant_doc_id=body.qdrant_doc_id or "",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    
    # Process Lineage Data
    try:
        # 1. Semantic Derivation (from cosine similarity)
        if hasattr(body, 'derived_from') and body.derived_from:
            parent_doc = db.query(Document).filter(Document.qdrant_doc_id == body.derived_from).first()
            if parent_doc:
                edge = DocEdge(
                    source_id=doc.id,
                    target_id=parent_doc.id,
                    edge_type=DocEdgeType.DERIVED_FROM,
                    confidence=0.9
                )
                db.add(edge)
                
        # 2. LLM Extracted Cross-References
        if hasattr(body, 'references') and body.references:
            for ref in body.references:
                # Find doc with similar filename
                ref_doc = db.query(Document).filter(Document.original_filename.ilike(f"%{ref}%")).first()
                if ref_doc:
                    edge = DocEdge(
                        source_id=doc.id,
                        target_id=ref_doc.id,
                        edge_type=DocEdgeType.REFERENCES,
                        confidence=0.7
                    )
                    db.add(edge)
        db.commit()
    except Exception as e:
        db.rollback()

    return {"message": "Registered", "document_id": doc.id}

# ═══════════════════════════════════════════════════════════════════════════════
#  PHASE 4: DOCUMENT GENEALOGY & LINEAGE
# ═══════════════════════════════════════════════════════════════════════════════

class DocLinkRequest(BaseModel):
    target_id: int
    edge_type: str  # supersedes, derived_from, references, amends

@router.post("/{doc_id}/link")
def link_documents(
    doc_id: int,
    body: DocLinkRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Manually link two documents (create an edge)."""
    source_doc = db.query(Document).filter(Document.id == doc_id).first()
    target_doc = db.query(Document).filter(Document.id == body.target_id).first()
    if not source_doc or not target_doc:
        raise HTTPException(status_code=404, detail="Source or target document not found")

    # Check if edge already exists
    existing = db.query(DocEdge).filter(
        DocEdge.source_id == doc_id,
        DocEdge.target_id == body.target_id,
        DocEdge.edge_type == body.edge_type
    ).first()
    
    if existing:
        return {"message": "Link already exists"}

    edge = DocEdge(
        source_id=doc_id,
        target_id=body.target_id,
        edge_type=body.edge_type
    )
    db.add(edge)
    
    # Audit log
    audit = AuditLog(
        user_id=current_user.id,
        action="LINK_DOCUMENT",
        resource_type="document",
        resource_id=str(doc_id),
        new_value=f"Linked to {body.target_id} via {body.edge_type}",
        status="success"
    )
    db.add(audit)
    db.commit()
    
    return {"message": "Documents linked successfully", "edge_id": edge.id}

@router.get("/lineage/all")
def get_all_lineage(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get the full document DAG for the D3.js Genealogy visualization."""
    docs = db.query(Document).all()
    edges = db.query(DocEdge).all()
    
    nodes_data = []
    for d in docs:
        nodes_data.append({
            "id": str(d.id),
            "filename": d.original_filename,
            "category": d.category or "General",
            "version": d.version,
            "group": d.doc_group_id,
            "status": d.status,
            "source": d.source,
            "created_at": d.created_at.isoformat(),
            "sha256": d.sha256_hash
        })
        
    edges_data = []
    # 1. Add explicit edges
    for e in edges:
        edges_data.append({
            "source": str(e.source_id),
            "target": str(e.target_id),
            "type": e.edge_type,
            "confidence": e.confidence
        })
        
    # 2. Add implicit version edges (parent -> child)
    for d in docs:
        if d.parent_doc_id:
            edges_data.append({
                "source": str(d.parent_doc_id),
                "target": str(d.id),
                "type": "supersedes",
                "confidence": 1.0
            })
            
    return {
        "nodes": nodes_data,
        "edges": edges_data
    }

@router.get("/lineage/export")
def export_lineage(
    format: str = Query("json-ld", description="Export format: json-ld or graphml"),
    db: Session = Depends(get_db)
):
    """Export the document DAG in industry-standard formats."""
    docs = db.query(Document).all()
    edges = db.query(DocEdge).all()
    
    if format == "json-ld":
        context = {
            "@context": {
                "schema": "http://schema.org/",
                "name": "schema:name",
                "description": "schema:description",
                "dateCreated": "schema:dateCreated",
                "supersedes": "schema:supersedes",
                "citation": "schema:citation"
            },
            "@graph": []
        }
        
        for d in docs:
            node = {
                "@id": f"urn:agra:doc:{d.id}",
                "@type": "schema:DigitalDocument",
                "name": d.original_filename,
                "dateCreated": d.created_at.isoformat()
            }
            # Add explicit edges
            related = []
            for e in edges:
                if e.source_id == d.id:
                    if e.edge_type == "supersedes":
                        node["supersedes"] = f"urn:agra:doc:{e.target_id}"
                    else:
                        related.append(f"urn:agra:doc:{e.target_id}")
            if related:
                node["citation"] = related
                
            # Add implicit parent
            if d.parent_doc_id:
                node["supersedes"] = f"urn:agra:doc:{d.parent_doc_id}"
                
            context["@graph"].append(node)
            
        return context
        
    elif format == "graphml":
        from fastapi.responses import Response
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">',
            '  <key id="name" for="node" attr.name="name" attr.type="string"/>',
            '  <graph id="G" edgedefault="directed">'
        ]
        for d in docs:
            lines.append(f'    <node id="{d.id}">')
            lines.append(f'      <data key="name">{d.original_filename}</data>')
            lines.append(f'    </node>')
            
        for e in edges:
            lines.append(f'    <edge source="{e.source_id}" target="{e.target_id}" label="{e.edge_type}"/>')
            
        for d in docs:
            if d.parent_doc_id:
                lines.append(f'    <edge source="{d.parent_doc_id}" target="{d.id}" label="supersedes"/>')
                
        lines.append('  </graph>\n</graphml>')
        return Response(content="\n".join(lines), media_type="application/xml")
        
    raise HTTPException(status_code=400, detail="Unsupported format. Use 'json-ld' or 'graphml'.")


@router.get("/{id1}/diff/{id2}")
def get_document_diff(
    id1: int,
    id2: int,
    db: Session = Depends(get_db)
):
    """Generate a text diff between two documents."""
    import difflib
    
    doc1 = db.query(Document).filter(Document.id == id1).first()
    doc2 = db.query(Document).filter(Document.id == id2).first()
    
    if not doc1 or not doc2:
        raise HTTPException(status_code=404, detail="One or both documents not found")
        
    path1 = os.path.join(UPLOAD_DIR, doc1.filename)
    path2 = os.path.join(UPLOAD_DIR, doc2.filename)
    
    # Simple extraction for diff (assuming text or extracting via a basic util if needed)
    # In a full production system this would use the Agent's OCR pipeline or cached text
    text1 = ""
    text2 = ""
    
    try:
        if doc1.file_type == "txt":
            with open(path1, "r", encoding="utf-8", errors="ignore") as f:
                text1 = f.read()
        if doc2.file_type == "txt":
            with open(path2, "r", encoding="utf-8", errors="ignore") as f:
                text2 = f.read()
    except Exception as e:
        pass
        
    diff = list(difflib.unified_diff(
        text1.splitlines(),
        text2.splitlines(),
        fromfile=doc1.original_filename,
        tofile=doc2.original_filename,
        lineterm=""
    ))
    
    return {"diff": diff}


# ═══════════════════════════════════════════════════════════════════════════════
#  MODULE 7: AUTOMATED METADATA EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════════

class ExtractedMetadataRequest(BaseModel):
    """Request body for storing LLM-extracted document metadata."""
    version_refs: Optional[List[str]] = Field(default_factory=list, max_length=50)
    cross_references: Optional[List[Dict[str, str]]] = Field(default_factory=list, max_length=100)
    amendment_dates: Optional[List[str]] = Field(default_factory=list, max_length=20)
    effective_date: Optional[str] = None
    supersession_info: Optional[Dict[str, str]] = Field(default_factory=dict)
    equipment_types: Optional[List[str]] = Field(default_factory=list, max_length=100)
    ship_types: Optional[List[str]] = Field(default_factory=list, max_length=50)
    regulation_categories: Optional[List[str]] = Field(default_factory=list, max_length=20)
    extraction_confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    extraction_metadata: Optional[Dict[str, Any]] = None


class ExtractedMetadataResponse(BaseModel):
    """Response model for extracted metadata."""
    document_id: int
    version_refs: List[str]
    cross_references: List[Dict[str, str]]
    amendment_dates: List[str]
    effective_date: Optional[str]
    supersession_info: Dict[str, str]
    equipment_types: List[str]
    ship_types: List[str]
    regulation_categories: List[str]
    extraction_confidence: float
    extracted_at: str


@router.post("/{doc_id}/metadata/extracted")
def store_extracted_metadata(
    doc_id: int,
    metadata: ExtractedMetadataRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Store LLM-extracted metadata for a document.
    Called by the Agent after metadata extraction.
    """
    # Check if document exists
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Check for existing metadata
    existing = db.query(ExtractedDocumentMetadata).filter(
        ExtractedDocumentMetadata.document_id == doc_id
    ).first()
    
    if existing:
        # Update existing record
        existing.version_refs = metadata.version_refs if metadata.version_refs else []
        existing.cross_references = metadata.cross_references if metadata.cross_references else []
        existing.amendment_dates = metadata.amendment_dates if metadata.amendment_dates else []
        existing.effective_date = _parse_date(metadata.effective_date) if metadata.effective_date else None
        existing.supersession_info = metadata.supersession_info if metadata.supersession_info else {}
        existing.equipment_types = metadata.equipment_types if metadata.equipment_types else []
        existing.ship_types = metadata.ship_types if metadata.ship_types else []
        existing.regulation_categories = metadata.regulation_categories if metadata.regulation_categories else []
        existing.extraction_confidence = metadata.extraction_confidence
        existing.extraction_metadata = metadata.extraction_metadata
        existing.extracted_at = datetime.utcnow()
    else:
        # Create new record
        new_metadata = ExtractedDocumentMetadata(
            document_id=doc_id,
            version_refs=metadata.version_refs if metadata.version_refs else [],
            cross_references=metadata.cross_references if metadata.cross_references else [],
            amendment_dates=metadata.amendment_dates if metadata.amendment_dates else [],
            effective_date=_parse_date(metadata.effective_date) if metadata.effective_date else None,
            supersession_info=metadata.supersession_info if metadata.supersession_info else {},
            equipment_types=metadata.equipment_types if metadata.equipment_types else [],
            ship_types=metadata.ship_types if metadata.ship_types else [],
            regulation_categories=metadata.regulation_categories if metadata.regulation_categories else [],
            extraction_confidence=metadata.extraction_confidence,
            extraction_metadata=metadata.extraction_metadata
        )
        db.add(new_metadata)
    
    # Also update document fields if confidence is high enough
    if metadata.extraction_confidence >= 0.7:
        # Update supersession info in version_notes if available
        if metadata.supersession_info:
            supersession_text = []
            if metadata.supersession_info.get("supersedes"):
                supersession_text.append(f"Supersedes: {metadata.supersession_info['supersedes']}")
            if metadata.supersession_info.get("superseded_by"):
                supersession_text.append(f"Superseded by: {metadata.supersession_info['superseded_by']}")
            if supersession_text:
                current_notes = doc.version_notes or ""
                doc.version_notes = current_notes + "\n" + "; ".join(supersession_text)
        
        # Update category if regulation_categories found and document has no category
        if metadata.regulation_categories and not doc.category:
            doc.category = metadata.regulation_categories[0]
    
    db.commit()
    
    logger.info("Stored extracted metadata for document %s (confidence: %.2f)", 
                doc_id, metadata.extraction_confidence)
    
    return {
        "message": "Metadata stored successfully",
        "document_id": doc_id,
        "extraction_confidence": metadata.extraction_confidence
    }


@router.get("/{doc_id}/metadata/extracted", response_model=ExtractedMetadataResponse)
def get_extracted_metadata(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Retrieve LLM-extracted metadata for a document.
    Admin/superadmin only.
    """
    # Check if document exists
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Get extracted metadata
    metadata = db.query(ExtractedDocumentMetadata).filter(
        ExtractedDocumentMetadata.document_id == doc_id
    ).first()
    
    if not metadata:
        raise HTTPException(status_code=404, detail="No extracted metadata found for this document")
    
    return ExtractedMetadataResponse(
        document_id=metadata.document_id,
        version_refs=metadata.version_refs or [],
        cross_references=metadata.cross_references or [],
        amendment_dates=metadata.amendment_dates or [],
        effective_date=metadata.effective_date.isoformat() if metadata.effective_date else None,
        supersession_info=metadata.supersession_info or {},
        equipment_types=metadata.equipment_types or [],
        ship_types=metadata.ship_types or [],
        regulation_categories=metadata.regulation_categories or [],
        extraction_confidence=metadata.extraction_confidence,
        extracted_at=metadata.extracted_at.isoformat() if metadata.extracted_at else None
    )


def _parse_date(date_str: Optional[str]) -> Optional[datetime]:
    """Parse date string to datetime object."""
    if not date_str:
        return None
    
    try:
        # Try ISO format first (YYYY-MM-DD)
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        try:
            # Try with time component
            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except ValueError:
            return None


@router.post("/{doc_id}/lineage/detected")
def accept_detected_lineage(
    doc_id: int,
    candidates: List[Dict[str, Any]],
    auto_accept: bool = Query(False, description="Auto-accept high-confidence candidates"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Accept or review auto-detected lineage candidates from agent.
    Creates DocEdge records for confirmed relationships.
    """
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    created_edges = []
    pending_review = []
    
    for candidate in candidates:
        candidate_id = candidate.get("doc_id")
        similarity = candidate.get("similarity", 0.0)
        suggested_rel = candidate.get("suggested_relationship", "related")
        
        # Auto-accept if similarity very high and auto_accept enabled
        if auto_accept and similarity >= 0.92:
            # Check for existing edge
            existing = db.query(DocEdge).filter(
                DocEdge.source_id == doc_id,
                DocEdge.target_id == candidate_id
            ).first()
            
            if not existing:
                edge = DocEdge(
                    source_id=doc_id,
                    target_id=candidate_id,
                    edge_type=suggested_rel if suggested_rel in [e.value for e in DocEdgeType] else DocEdgeType.REFERENCES.value,
                    confidence=similarity
                )
                db.add(edge)
                created_edges.append({
                    "target_id": candidate_id,
                    "relationship": suggested_rel,
                    "similarity": similarity,
                    "status": "auto_accepted"
                })
        else:
            # Flag for manual review
            pending_review.append({
                "target_id": candidate_id,
                "target_filename": candidate.get("filename", "Unknown"),
                "suggested_relationship": suggested_rel,
                "similarity": similarity,
                "confidence": candidate.get("confidence", similarity)
            })
    
    db.commit()
    
    return {
        "message": "Lineage candidates processed",
        "document_id": doc_id,
        "auto_accepted": len(created_edges),
        "pending_review": len(pending_review),
        "created_edges": created_edges,
        "review_queue": pending_review
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  MODULE 7 PHASE 4: ENTITY STORAGE
# ═══════════════════════════════════════════════════════════════════════════════

from typing import List as TypingList

class EntityItem(BaseModel):
    """Single extracted entity for storage."""
    entity_type: str
    name: str
    normalized_name: str
    context: Optional[str] = None
    chunk_index: Optional[int] = None
    page_number: Optional[int] = None
    extraction_confidence: float = Field(ge=0.0, le=1.0, default=0.7)


@router.post("/{doc_id}/entities")
def store_document_entities(
    doc_id: int,
    entities: TypingList[EntityItem],
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Store extracted entities for a document.
    Called by the Agent after entity extraction.
    """
    # Check document exists
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    stored_count = 0
    
    for entity_data in entities:
        try:
            # Check for existing duplicate
            existing = db.query(DocumentEntity).filter(
                DocumentEntity.document_id == doc_id,
                DocumentEntity.entity_type == entity_data.entity_type,
                DocumentEntity.entity_normalized == entity_data.normalized_name
            ).first()
            
            if existing:
                # Update context if new one is more detailed
                if entity_data.context and len(entity_data.context) > len(existing.context or ""):
                    existing.context = entity_data.context
                    existing.extraction_confidence = max(
                        existing.extraction_confidence, 
                        entity_data.extraction_confidence
                    )
            else:
                # Create new entity
                new_entity = DocumentEntity(
                    document_id=doc_id,
                    entity_type=entity_data.entity_type,
                    entity_name=entity_data.name,
                    entity_normalized=entity_data.normalized_name,
                    context=entity_data.context,
                    chunk_index=entity_data.chunk_index,
                    page_number=entity_data.page_number,
                    extraction_confidence=entity_data.extraction_confidence,
                    extracted_by="llm",
                    first_seen_in_version=doc.version
                )
                db.add(new_entity)
                stored_count += 1
                
        except Exception as e:
            logger.warning("Failed to store entity %s: %s", entity_data.name, e)
            continue
    
    db.commit()
    
    logger.info("Stored %d new entities for document %s", stored_count, doc_id)
    
    return {
        "message": "Entities stored successfully",
        "document_id": doc_id,
        "entities_stored": stored_count,
        "total_received": len(entities)
    }


@router.get("/lineage/export/docx")
def export_lineage_docx(
    doc_id: int = Query(..., description="Document ID to export"),
    include_entities: bool = Query(True, description="Include entity summary"),
    include_changes: bool = Query(True, description="Include change summaries"),
    classification: str = Query("UNCLASSIFIED", description="Classification level"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Export document genealogy as Word document with tables.
    """
    from app.utils.genealogy_docx_export import generate_genealogy_docx
    
    # Check document exists and user has access
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Generate DOCX
    try:
        output_path = generate_genealogy_docx(
            doc_id=doc_id,
            db=db,
            include_entities=include_entities,
            include_changes=include_changes,
            classification=classification
        )
        
        return FileResponse(
            output_path,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename=f"genealogy_{doc.original_filename}_{datetime.now().strftime('%Y%m%d')}.docx"
        )
    except Exception as e:
        logger.error("Failed to generate genealogy DOCX: %s", e)
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


@router.post("/{doc_id}/changes")
def store_change_summary(
    doc_id: int,
    from_doc_id: int = Query(..., description="Previous version document ID"),
    summary_data: dict = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Store LLM-generated change summary between document versions.
    """
    # Validate documents exist
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    from_doc = db.query(Document).filter(Document.id == from_doc_id).first()
    if not from_doc:
        raise HTTPException(status_code=404, detail="From document not found")
    
    # Check for existing summary
    existing = db.query(DocumentChangeSummary).filter(
        DocumentChangeSummary.from_doc_id == from_doc_id,
        DocumentChangeSummary.to_doc_id == doc_id
    ).first()
    
    if existing:
        # Update existing
        existing.summary_text = summary_data.get("summary_text", existing.summary_text)
        existing.major_changes = summary_data.get("major_changes", [])
        existing.minor_changes = summary_data.get("minor_changes", [])
        existing.impact_assessment = summary_data.get("impact_assessment", "Medium")
        existing.action_required = summary_data.get("action_required", "")
        existing.generated_at = datetime.utcnow()
    else:
        # Create new
        new_summary = DocumentChangeSummary(
            from_doc_id=from_doc_id,
            to_doc_id=doc_id,
            summary_text=summary_data.get("summary_text", ""),
            major_changes=summary_data.get("major_changes", []),
            minor_changes=summary_data.get("minor_changes", []),
            impact_assessment=summary_data.get("impact_assessment", "Medium"),
            action_required=summary_data.get("action_required", ""),
            generated_by_llm=True,
            generated_at=datetime.utcnow()
        )
        db.add(new_summary)
    
    db.commit()
    
    return {
        "message": "Change summary stored successfully",
        "from_doc_id": from_doc_id,
        "to_doc_id": doc_id,
        "impact": summary_data.get("impact_assessment", "Medium")
    }


@router.get("/{doc_id}/changes")
def get_change_summaries(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get all change summaries for a document.
    """
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Get summaries where this doc is source or target
    summaries = db.query(DocumentChangeSummary).filter(
        (DocumentChangeSummary.from_doc_id == doc_id) |
        (DocumentChangeSummary.to_doc_id == doc_id)
    ).order_by(DocumentChangeSummary.generated_at.desc()).all()
    
    result = []
    for summary in summaries:
        other_id = summary.to_doc_id if summary.from_doc_id == doc_id else summary.from_doc_id
        other_doc = db.query(Document).filter(Document.id == other_id).first()
        
        result.append({
            "id": summary.id,
            "direction": "outgoing" if summary.from_doc_id == doc_id else "incoming",
            "other_version": other_doc.version if other_doc else '?',
            "other_filename": other_doc.original_filename if other_doc else 'Unknown',
            "summary": summary.summary_text,
            "impact": summary.impact_assessment,
            "action_required": summary.action_required,
            "major_changes": summary.major_changes,
            "generated_at": summary.generated_at.isoformat() if summary.generated_at else None
        })
    
    return {
        "document_id": doc_id,
        "total_summaries": len(result),
        "summaries": result
    }


@router.get("/{doc_id}/entities/stats")
def get_document_entity_stats(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get entity statistics for a document.
    """
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Aggregate stats
    stats = db.query(
        DocumentEntity.entity_type,
        func.count(DocumentEntity.id).label("count")
    ).filter(
        DocumentEntity.document_id == doc_id
    ).group_by(DocumentEntity.entity_type).all()
    
    total_entities = db.query(DocumentEntity).filter(
        DocumentEntity.document_id == doc_id
    ).count()
    
    return {
        "document_id": doc_id,
        "document_filename": doc.original_filename,
        "total_entities": total_entities,
        "by_type": [{"type": t, "count": c} for t, c in stats]
    }

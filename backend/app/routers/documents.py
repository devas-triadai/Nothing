from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime
import hashlib
import uuid
import os
import re

from app.database import get_db
from app.models.models import User, Document, AuditLog
from app.routers.auth import require_superadmin

router = APIRouter()

# Directory for uploaded files — persistent across pod restarts
# Uses same agra_data dir as the database
from pathlib import Path as _Path
_DATA_DIR = _Path(os.environ.get("AGRA_DATA_DIR", "/workspace/agra_data"))
if not _DATA_DIR.exists():
    _DATA_DIR = _Path(__file__).resolve().parent.parent.parent / "agra_data"
UPLOAD_DIR = str(_DATA_DIR / "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


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
    return {"message": "Document uploaded", "document": _doc_to_dict(doc, db)}


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


# ─── All lineage trees (for the full lineage graph view) ─────────────────────
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
    current_user: User = Depends(require_superadmin)
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
        results.append({"filename": file.filename, "status": "uploaded", "category": detected_category, "tags": detected_tags, "confidence": detected_conf})

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

    return {"message": "Registered", "document_id": doc.id}

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime
import uuid
import os

from app.database import get_db
from app.models.models import User, Document, AuditLog
from app.routers.auth import require_superadmin

router = APIRouter()

# Directory for uploaded files (in air-gapped env, use a mounted volume)
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/tmp/agra_uploads")
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
        "description": doc.description,
        "version": doc.version,
        "version_notes": doc.version_notes,
        "doc_group_id": doc.doc_group_id,
        "parent_doc_id": doc.parent_doc_id,
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

    # Determine doc_group_id and version number
    if parent_doc_id:
        parent = db.query(Document).filter(Document.id == parent_doc_id).first()
        if not parent:
            raise HTTPException(status_code=404, detail="Parent document not found")
        doc_group_id = parent.doc_group_id or str(parent.id)
        # Find max version in this group
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
        category=category,
        description=description,
        version=version,
        version_notes=version_notes,
        doc_group_id=doc_group_id,
        parent_doc_id=parent_doc_id,
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

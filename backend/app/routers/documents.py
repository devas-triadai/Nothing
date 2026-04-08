from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel
from datetime import datetime

from app.database import get_db
from app.models.models import User, Document, AuditLog
from app.routers.auth import require_superadmin

router = APIRouter()


class DocumentUpdate(BaseModel):
    category: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None


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

    result = []
    for doc in docs:
        uploader = db.query(User).filter(User.id == doc.uploaded_by).first()
        result.append({
            "id": doc.id,
            "filename": doc.filename,
            "original_filename": doc.original_filename,
            "file_type": doc.file_type,
            "file_size": doc.file_size,
            "page_count": doc.page_count,
            "status": doc.status,
            "category": doc.category,
            "description": doc.description,
            "uploaded_by": uploader.username if uploader else "unknown",
            "created_at": doc.created_at
        })
    return {"total": total, "documents": result}


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
    return {"message": "Document updated"}


@router.delete("/{doc_id}")
def delete_document(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin)
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    db.delete(doc)
    audit = AuditLog(
        user_id=current_user.id,
        action="DELETE_DOCUMENT",
        resource_type="document",
        resource_id=str(doc_id),
        old_value=doc.original_filename,
        status="success"
    )
    db.add(audit)
    db.commit()
    return {"message": "Document deleted"}

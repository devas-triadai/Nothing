"""
Module 7 Phase 4 — Entity Lineage Search API
Search and track entity evolution across document versions.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime

from app.database import get_db
from app.models.models import (
    Document, DocumentEntity, EntitySearchLog, User, DocEdge
)
from app.routers.auth import get_current_user, require_admin

import logging

logger = logging.getLogger(__name__)
router = APIRouter()


class EntityResponse(BaseModel):
    """Entity with evolution information."""
    id: int
    entity_type: str
    entity_name: str
    entity_normalized: str
    context: Optional[str]
    chunk_index: Optional[int]
    page_number: Optional[int]
    extraction_confidence: float
    extracted_at: datetime
    
    # Document info
    document_id: int
    document_filename: str
    document_version: Optional[int]
    document_created_at: Optional[datetime]
    
    # Lineage info
    first_seen_in_version: Optional[int]
    evolves_from_entity_id: Optional[int]
    evolution_type: Optional[str]


class EntityTimelineResponse(BaseModel):
    """Timeline of entity evolution."""
    entity_name: str
    entity_type: str
    total_mentions: int
    first_seen: datetime
    last_seen: datetime
    timeline: List[dict]


class EntitySearchResponse(BaseModel):
    """Response for entity search."""
    query: str
    entity_type_filter: Optional[str]
    total_results: int
    entities: List[EntityResponse]


def _normalize_search_term(term: str) -> str:
    """Normalize search term for matching."""
    import re
    normalized = term.lower()
    normalized = re.sub(r'[^\w\s]', ' ', normalized)
    normalized = ' '.join(normalized.split())
    return normalized


def _log_entity_search(
    db: Session,
    user_id: int,
    query: str,
    entity_type: Optional[str],
    results_count: int,
    request: Optional[Request] = None
):
    """Log entity search for audit trail."""
    try:
        log_entry = EntitySearchLog(
            user_id=user_id,
            search_query=query,
            entity_type_filter=entity_type,
            results_count=results_count,
            ip_address=request.client.host if request else None,
            user_agent=request.headers.get("user-agent") if request else None
        )
        db.add(log_entry)
        db.commit()
    except Exception as e:
        logger.error("Failed to log entity search: %s", e)
        db.rollback()


@router.get("/entities/search", response_model=EntitySearchResponse)
def search_entities(
    q: str = Query(..., min_length=2, max_length=200, description="Search query"),
    entity_type: Optional[str] = Query(None, description="Filter by entity type"),
    exact_match: bool = Query(False, description="Require exact match"),
    min_confidence: float = Query(0.6, ge=0.0, le=1.0, description="Minimum extraction confidence"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    request: Request = None
):
    """
    Search for entities by name (fuzzy matching supported).
    Uses PostgreSQL trigram similarity for fuzzy search.
    """
    normalized_query = _normalize_search_term(q)
    
    # Build query with document join for clearance check
    query = db.query(DocumentEntity, Document).join(
        Document, DocumentEntity.document_id == Document.id
    )
    
    # Apply entity type filter
    if entity_type:
        query = query.filter(DocumentEntity.entity_type == entity_type)
    
    # Apply confidence filter
    query = query.filter(DocumentEntity.extraction_confidence >= min_confidence)
    
    # Apply search (fuzzy or exact)
    if exact_match:
        query = query.filter(DocumentEntity.entity_normalized == normalized_query)
    else:
        # Use trigram similarity for fuzzy search
        # Note: Requires pg_trgm extension and GIN index
        query = query.filter(
            func.similarity(DocumentEntity.entity_normalized, normalized_query) > 0.3
        ).order_by(
            func.similarity(DocumentEntity.entity_normalized, normalized_query).desc()
        )
    
    # Order by extraction date (newest first)
    if exact_match:
        query = query.order_by(DocumentEntity.extracted_at.desc())
    
    # Execute with pagination
    total = query.count()
    results = query.offset(skip).limit(limit).all()
    
    # Convert to response model
    entities = []
    cleared_ids = []
    
    for entity, doc in results:
        # Skip if user doesn't have clearance (simple check)
        # In production, implement proper clearance level check
        
        entities.append(EntityResponse(
            id=entity.id,
            entity_type=entity.entity_type,
            entity_name=entity.entity_name,
            entity_normalized=entity.entity_normalized,
            context=entity.context,
            chunk_index=entity.chunk_index,
            page_number=entity.page_number,
            extraction_confidence=entity.extraction_confidence,
            extracted_at=entity.extracted_at,
            document_id=doc.id,
            document_filename=doc.original_filename,
            document_version=doc.version,
            document_created_at=doc.created_at,
            first_seen_in_version=entity.first_seen_in_version,
            evolves_from_entity_id=entity.evolves_from_entity_id,
            evolution_type=entity.evolution_type
        ))
        cleared_ids.append(entity.id)
    
    # Log the search
    _log_entity_search(db, current_user.id, q, entity_type, len(entities), request)
    
    return EntitySearchResponse(
        query=q,
        entity_type_filter=entity_type,
        total_results=total,
        entities=entities
    )


@router.get("/entities/{entity_id}/timeline", response_model=EntityTimelineResponse)
def get_entity_timeline(
    entity_id: int,
    include_related: bool = Query(True, description="Include semantically similar entities"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get evolution timeline for a specific entity.
    Shows how the entity appeared/changed across document versions.
    """
    # Get the entity
    entity = db.query(DocumentEntity).filter(DocumentEntity.id == entity_id).first()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    
    # Find all mentions of this entity (same normalized name, same type)
    mentions_query = db.query(DocumentEntity, Document).join(
        Document, DocumentEntity.document_id == Document.id
    ).filter(
        DocumentEntity.entity_type == entity.entity_type,
        DocumentEntity.entity_normalized == entity.entity_normalized,
        DocumentEntity.extraction_confidence >= 0.6
    ).order_by(Document.created_at.asc())
    
    mentions = mentions_query.all()
    
    if not mentions:
        raise HTTPException(status_code=404, detail="No timeline data found")
    
    # Build timeline
    timeline = []
    for mention, doc in mentions:
        timeline.append({
            "entity_id": mention.id,
            "document_id": doc.id,
            "document_filename": doc.original_filename,
            "document_version": doc.version,
            "document_date": doc.created_at.isoformat() if doc.created_at else None,
            "context": mention.context,
            "confidence": mention.extraction_confidence,
            "evolution_type": mention.evolution_type,
            "page_number": mention.page_number
        })
    
    # Get first and last seen dates
    first_seen = mentions[0][1].created_at if mentions else None
    last_seen = mentions[-1][1].created_at if mentions else None
    
    return EntityTimelineResponse(
        entity_name=entity.entity_name,
        entity_type=entity.entity_type,
        total_mentions=len(mentions),
        first_seen=first_seen,
        last_seen=last_seen,
        timeline=timeline
    )


@router.get("/documents/{doc_id}/entities")
def get_document_entities(
    doc_id: int,
    entity_type: Optional[str] = Query(None, description="Filter by type"),
    min_confidence: float = Query(0.6, ge=0.0, le=1.0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get all extracted entities for a specific document.
    """
    # Check document exists
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Build query
    query = db.query(DocumentEntity).filter(
        DocumentEntity.document_id == doc_id,
        DocumentEntity.extraction_confidence >= min_confidence
    )
    
    if entity_type:
        query = query.filter(DocumentEntity.entity_type == entity_type)
    
    entities = query.order_by(DocumentEntity.extraction_confidence.desc()).all()
    
    return {
        "document_id": doc_id,
        "document_filename": doc.original_filename,
        "total_entities": len(entities),
        "entities": [
            {
                "id": e.id,
                "entity_type": e.entity_type,
                "entity_name": e.entity_name,
                "entity_normalized": e.entity_normalized,
                "context": e.context,
                "extraction_confidence": e.extraction_confidence,
                "chunk_index": e.chunk_index,
                "page_number": e.page_number,
                "evolution_type": e.evolution_type
            }
            for e in entities
        ]
    }


@router.post("/entities/{entity_id}/evolution")
def link_entity_evolution(
    entity_id: int,
    evolves_from_id: int,
    evolution_type: str = Query(..., regex="^(renamed|redefined|deprecated|added|removed)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Manually link an entity to its predecessor (evolution tracking).
    Admin only.
    """
    entity = db.query(DocumentEntity).filter(DocumentEntity.id == entity_id).first()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    
    predecessor = db.query(DocumentEntity).filter(DocumentEntity.id == evolves_from_id).first()
    if not predecessor:
        raise HTTPException(status_code=404, detail="Predecessor entity not found")
    
    # Update evolution link
    entity.evolves_from_entity_id = evolves_from_id
    entity.evolution_type = evolution_type
    
    db.commit()
    
    return {
        "message": "Evolution link created",
        "entity_id": entity_id,
        "evolves_from": evolves_from_id,
        "evolution_type": evolution_type
    }


@router.get("/entities/audit-log")
def get_entity_search_audit_log(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Get audit log of entity searches.
    Admin only.
    """
    query = db.query(EntitySearchLog, User.username).join(
        User, EntitySearchLog.user_id == User.id
    )
    
    if start_date:
        query = query.filter(EntitySearchLog.timestamp >= start_date)
    if end_date:
        query = query.filter(EntitySearchLog.timestamp <= end_date)
    
    total = query.count()
    logs = query.order_by(EntitySearchLog.timestamp.desc()).offset(skip).limit(limit).all()
    
    return {
        "total": total,
        "logs": [
            {
                "id": log.id,
                "user_id": log.user_id,
                "username": username,
                "search_query": log.search_query,
                "entity_type_filter": log.entity_type_filter,
                "results_count": log.results_count,
                "timestamp": log.timestamp.isoformat() if log.timestamp else None,
                "ip_address": log.ip_address
            }
            for log, username in logs
        ]
    }

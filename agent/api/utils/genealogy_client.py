"""
AGRA Module 5 & 10 — Genealogy Data Client
Fetches document genealogy and superseded status from admin backend.
"""

import logging
import time
from typing import Dict, List, Optional, Any
from datetime import datetime
import httpx

logger = logging.getLogger("agra.genealogy_client")

# Cache: {doc_id: (data, timestamp)}
_genealogy_cache: Dict[str, tuple] = {}
_CACHE_TTL_SECONDS = 300  # 5 minutes

_ADMIN_BASE = "http://localhost:8000"  # Will be overridden by env var


def _get_admin_base() -> str:
    """Get admin backend URL from environment or default."""
    import os
    return os.getenv("AGRA_BACKEND_URL", "http://localhost:8000")


def _get_cached(doc_id: str) -> Optional[Dict]:
    """Get cached genealogy data if not expired."""
    if doc_id in _genealogy_cache:
        data, timestamp = _genealogy_cache[doc_id]
        if time.time() - timestamp < _CACHE_TTL_SECONDS:
            return data
        # Expired, remove from cache
        del _genealogy_cache[doc_id]
    return None


def _set_cache(doc_id: str, data: Dict):
    """Cache genealogy data."""
    _genealogy_cache[doc_id] = (data, time.time())


async def check_superseded_status(
    doc_ids: List[str],
    token: str = ""
) -> Dict[str, Dict[str, Any]]:
    """
    Check superseded status for multiple documents.
    
    Args:
        doc_ids: List of document IDs to check
        token: Auth token for admin backend
    
    Returns:
        Dict mapping doc_id -> superseded info or None
        Format: {doc_id: {"superseded_by_id": str, "superseded_by_name": str, "date": str}}
    """
    if not doc_ids:
        return {}
    
    # Filter out builtin docs (they don't exist in backend)
    backend_doc_ids = [
        d for d in doc_ids
        if not d.startswith("builtin:")
    ]
    
    if not backend_doc_ids:
        return {}
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Build query params
            params = [("doc_ids", d) for d in backend_doc_ids]
            
            res = await client.get(
                f"{_get_admin_base()}/api/documents/check-superseded",
                params=params,
                headers={"Authorization": f"Bearer {token}"} if token else {}
            )
            
            if res.status_code == 200:
                data = res.json()
                return data.get("superseded", {})
            else:
                logger.warning("check-superseded returned %s: %s", res.status_code, res.text[:200])
                return {}
    except Exception as e:
        logger.warning("Failed to check superseded status: %s", e)
        return {}


async def get_document_lineage(
    doc_id: str,
    token: str = ""
) -> Optional[Dict[str, Any]]:
    """
    Get full genealogy/lineage info for a document.
    
    Args:
        doc_id: Document ID
        token: Auth token
    
    Returns:
        Dict with lineage info or None if not found:
        {
            "id": str,
            "filename": str,
            "version": int,
            "parent_doc_id": str or None,
            "parent_version": int or None,
            "superseded_by_id": str or None,
            "superseded_by_name": str or None,
            "created_at": str,
            "status": "current" | "superseded"
        }
    """
    # Check cache first
    cached = _get_cached(doc_id)
    if cached:
        return cached
    
    # Skip builtin docs
    if doc_id.startswith("builtin:"):
        return None
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Try to get full lineage from the graph
            res = await client.get(
                f"{_get_admin_base()}/api/documents/lineage/all",
                headers={"Authorization": f"Bearer {token}"} if token else {}
            )
            
            if res.status_code != 200:
                logger.warning("Failed to fetch lineage: %s", res.status_code)
                return None
            
            data = res.json()
            nodes = data.get("nodes", [])
            edges = data.get("edges", [])
            
            # Find the document node
            doc_node = None
            for node in nodes:
                if str(node.get("id")) == str(doc_id):
                    doc_node = node
                    break
            
            if not doc_node:
                return None
            
            # Build lineage info
            lineage = {
                "id": doc_id,
                "filename": doc_node.get("filename", "Unknown"),
                "version": doc_node.get("version", 1),
                "category": doc_node.get("category", "General"),
                "created_at": doc_node.get("created_at"),
                "status": doc_node.get("status", "unknown"),
                "parent_doc_id": doc_node.get("parent_doc_id"),
                "superseded_by_id": None,
                "superseded_by_name": None,
                "supersedes": [],  # List of docs this one supersedes
                "derived_from": [],  # List of docs this is derived from
            }
            
            # Find relationships from edges
            for edge in edges:
                source_id = str(edge.get("source", ""))
                target_id = str(edge.get("target", ""))
                edge_type = edge.get("type", "").lower()
                
                # If this doc is the target
                if target_id == str(doc_id):
                    if edge_type == "supersedes":
                        # Someone supersedes this doc
                        for node in nodes:
                            if str(node.get("id")) == source_id:
                                lineage["superseded_by_id"] = source_id
                                lineage["superseded_by_name"] = node.get("filename", "Unknown")
                                lineage["status"] = "superseded"
                                break
                    elif edge_type == "derived_from":
                        lineage["derived_from"].append(source_id)
                
                # If this doc is the source
                if source_id == str(doc_id):
                    if edge_type == "supersedes":
                        # This doc supersedes someone
                        for node in nodes:
                            if str(node.get("id")) == target_id:
                                lineage["supersedes"].append({
                                    "id": target_id,
                                    "filename": node.get("filename", "Unknown")
                                })
                                break
            
            # Cache and return
            _set_cache(doc_id, lineage)
            return lineage
            
    except Exception as e:
        logger.warning("Failed to get document lineage: %s", e)
        return None


def format_superseded_warning(superseded_docs: Dict[str, Dict]) -> str:
    """
    Format superseded document warnings for content generation.
    
    Args:
        superseded_docs: Dict from check_superseded_status()
    
    Returns:
        Formatted warning text
    """
    if not superseded_docs:
        return ""
    
    lines = [
        "⚠️ DOCUMENT STATUS WARNING:\n",
        "The following source documents have been superseded and may contain outdated information:\n"
    ]
    
    for doc_id, info in superseded_docs.items():
        old_name = info.get("superseded_by_name", "Unknown")
        new_name = info.get("superseded_by_name", "a newer version")
        lines.append(f'- "{old_name}" → Superseded by "{new_name}"')
    
    lines.append("\nExercise caution when using information from outdated documents. "
                "Consider referencing the newer versions for current requirements.")
    
    return "\n".join(lines)


def format_genealogy_provenance(lineage_info: List[Dict]) -> str:
    """
    Format genealogy/provenance section for content output.
    
    Args:
        lineage_info: List of document lineage dicts
    
    Returns:
        Formatted provenance text
    """
    if not lineage_info:
        return ""
    
    lines = [
        "## Document Genealogy & Provenance\n",
        "| Document | Version | Status | Relationship |",
        "|----------|---------|--------|--------------|"
    ]
    
    for info in lineage_info:
        filename = info.get("filename", "Unknown")
        version = info.get("version", "?")
        status = info.get("status", "unknown")
        
        # Build relationship string
        relationships = []
        if info.get("superseded_by_name"):
            relationships.append(f"Superseded by: {info['superseded_by_name']}")
        if info.get("supersedes"):
            supersedes_list = ", ".join(s.get("filename", "?") for s in info["supersedes"])
            relationships.append(f"Supersedes: {supersedes_list}")
        if info.get("derived_from"):
            relationships.append(f"Derived from {len(info['derived_from'])} document(s)")
        
        rel_str = "; ".join(relationships) if relationships else "None"
        
        lines.append(f"| {filename} | v{version} | {status} | {rel_str} |")
    
    return "\n".join(lines)


def format_multi_doc_citation(doc_index: int, doc_name: str, page: str = "?") -> str:
    """
    Format a citation for multi-document summaries.
    
    Returns format: [Doc A, p.5] or [Doc A, Section X]
    """
    # Extract short name (first word or first 10 chars)
    short_name = doc_name.split()[0] if doc_name else f"Doc{doc_index}"
    if len(short_name) > 15:
        short_name = short_name[:15]
    
    return f"[{short_name}, p.{page}]"


def should_include_genealogy(doc_ids: List[str]) -> bool:
    """
    Determine if genealogy info should be included based on doc types.
    
    Returns True if any doc is not builtin and may have lineage.
    """
    return any(not d.startswith("builtin:") for d in doc_ids)

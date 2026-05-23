"""
Module 7 Phase 6 — LLM-Generated Change Summary
Generates human-readable descriptions of differences between document versions.
"""

import logging
import json
import hashlib
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import datetime, timedelta

from api.rag import llm as llm_engine
from api.rag.delta_indexer import compute_chunk_diff, ChunkDiffResult

logger = logging.getLogger("agra.change_analyzer")

# Cache for change summaries (TTL: 1 hour for drafts)
_change_summary_cache: Dict[str, Dict] = {}
_CACHE_TTL_SECONDS = 3600


@dataclass
class ChangeSummary:
    """Structured change summary between document versions."""
    summary_text: str  # One-paragraph executive summary
    major_changes: List[str]  # Significant modifications
    minor_changes: List[str]  # Typos, formatting
    impact_assessment: str  # High, Medium, Low
    action_required: str  # What users should do
    confidence: float  # Summary accuracy confidence
    generated_at: datetime


def _compute_cache_key(doc_id_1: str, doc_id_2: str) -> str:
    """Compute cache key for document pair."""
    # Sort IDs to ensure consistent key regardless of order
    ids = sorted([doc_id_1, doc_id_2])
    return hashlib.sha256(f"{ids[0]}:{ids[1]}".encode()).hexdigest()[:16]


def _get_cached_summary(doc_id_1: str, doc_id_2: str) -> Optional[ChangeSummary]:
    """Get cached change summary if valid."""
    cache_key = _compute_cache_key(doc_id_1, doc_id_2)
    cached = _change_summary_cache.get(cache_key)
    
    if cached:
        age = (datetime.now() - cached["timestamp"]).total_seconds()
        if age < _CACHE_TTL_SECONDS:
            logger.debug("Using cached change summary for %s:%s", doc_id_1, doc_id_2)
            return cached["summary"]
        else:
            # Expired
            del _change_summary_cache[cache_key]
    
    return None


def _cache_summary(doc_id_1: str, doc_id_2: str, summary: ChangeSummary):
    """Cache change summary."""
    cache_key = _compute_cache_key(doc_id_1, doc_id_2)
    _change_summary_cache[cache_key] = {
        "summary": summary,
        "timestamp": datetime.now()
    }


def _build_structured_diff(
    old_chunks: List[Dict[str, Any]],
    new_chunks: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Build structured diff representation for LLM.
    
    Instead of sending full text, send:
    - Old structure (headings, section list)
    - New structure
    - Change categories (added/removed/modified sections)
    """
    # Compute chunk-level diff
    diff = compute_chunk_diff(old_chunks, new_chunks, use_similarity_fallback=True)
    
    # Extract structure from chunks (simple heuristic: first line or sentence)
    old_structure = []
    for chunk in old_chunks[:20]:  # Limit to first 20 chunks
        text = chunk.get("text", "")
        # Get first sentence or first 100 chars
        first_part = text.split('.')[0] if '.' in text else text[:100]
        old_structure.append(first_part[:150])
    
    new_structure = []
    for chunk in new_chunks[:20]:
        text = chunk.get("text", "")
        first_part = text.split('.')[0] if '.' in text else text[:100]
        new_structure.append(first_part[:150])
    
    # Identify changed sections
    added_sections = []
    removed_sections = []
    modified_sections = []
    
    for chunk in diff.to_add:
        text = chunk.get("text", "")[:150]
        added_sections.append(text)
    
    for chunk_id in diff.to_delete:
        # Find the old chunk text
        old_text = next((c.get("text", "")[:150] for c in old_chunks 
                        if (c.get("id") or c.get("chunk_id")) == chunk_id), "Unknown")
        removed_sections.append(old_text)
    
    for chunk in diff.to_update:
        text = chunk.get("text", "")[:150]
        modified_sections.append(text)
    
    return {
        "stats": {
            "total_old_chunks": len(old_chunks),
            "total_new_chunks": len(new_chunks),
            "unchanged": diff.unchanged,
            "added": len(diff.to_add),
            "removed": len(diff.to_delete),
            "modified": len(diff.to_update),
            "change_ratio": diff.stats.get("change_ratio", 0.0)
        },
        "old_structure": old_structure[:10],  # Limit to top 10
        "new_structure": new_structure[:10],
        "added_sections": added_sections[:5],
        "removed_sections": removed_sections[:5],
        "modified_sections": modified_sections[:5]
    }


def _build_change_summary_prompt(
    old_doc_metadata: Dict[str, Any],
    new_doc_metadata: Dict[str, Any],
    structured_diff: Dict[str, Any]
) -> str:
    """Build LLM prompt for change summary generation."""
    
    return f"""Analyze the differences between these two document versions and generate a change summary.

OLD VERSION: {old_doc_metadata.get('filename', 'Unknown')} v{old_doc_metadata.get('version', '?')}
NEW VERSION: {new_doc_metadata.get('filename', 'Unknown')} v{new_doc_metadata.get('version', '?')}

CHANGE STATISTICS:
- Old document chunks: {structured_diff['stats']['total_old_chunks']}
- New document chunks: {structured_diff['stats']['total_new_chunks']}
- Unchanged chunks: {structured_diff['stats']['unchanged']}
- Added sections: {structured_diff['stats']['added']}
- Removed sections: {structured_diff['stats']['removed']}
- Modified sections: {structured_diff['stats']['modified']}
- Overall change ratio: {structured_diff['stats']['change_ratio']:.1%}

OLD DOCUMENT STRUCTURE (sample):
{chr(10).join(['- ' + s for s in structured_diff['old_structure']])}

NEW DOCUMENT STRUCTURE (sample):
{chr(10).join(['- ' + s for s in structured_diff['new_structure']])}

ADDED SECTIONS (sample):
{chr(10).join(['+ ' + s for s in structured_diff['added_sections']]) if structured_diff['added_sections'] else 'None'}

REMOVED SECTIONS (sample):
{chr(10).join(['- ' + s for s in structured_diff['removed_sections']]) if structured_diff['removed_sections'] else 'None'}

MODIFIED SECTIONS (sample):
{chr(10).join(['~ ' + s for s in structured_diff['modified_sections']]) if structured_diff['modified_sections'] else 'None'}

Generate a change summary in this JSON format:
{{
    "summary_text": "One-paragraph executive summary of changes (2-3 sentences)",
    "major_changes": ["List of 2-5 significant changes"],
    "minor_changes": ["List of 0-3 minor changes (typos, formatting)"],
    "impact_assessment": "High|Medium|Low",
    "action_required": "What users should do (e.g., 'Review new requirements before 2024-12-01')"
}}

Rules:
1. Impact = High if >30% changed or core requirements modified
2. Impact = Medium if 10-30% changed or sections added/removed
3. Impact = Low if <10% changed (typos, formatting)
4. Do NOT include specific technical values in summary (for security)
5. Focus on structural changes and requirement modifications
6. Be concise and professional
"""


async def generate_change_summary(
    old_doc_id: str,
    new_doc_id: str,
    old_doc_chunks: List[Dict[str, Any]],
    new_doc_chunks: List[Dict[str, Any]],
    old_doc_metadata: Dict[str, Any],
    new_doc_metadata: Dict[str, Any],
    use_cache: bool = True
) -> ChangeSummary:
    """
    Generate LLM-powered change summary between two document versions.
    
    Args:
        old_doc_id: Old document ID
        new_doc_id: New document ID
        old_doc_chunks: Chunks from old version
        new_doc_chunks: Chunks from new version
        old_doc_metadata: Metadata for old version
        new_doc_metadata: Metadata for new version
        use_cache: Whether to use caching
    
    Returns:
        ChangeSummary object with generated summary
    """
    # Check cache
    if use_cache:
        cached = _get_cached_summary(old_doc_id, new_doc_id)
        if cached:
            return cached
    
    # Build structured diff
    structured_diff = _build_structured_diff(old_doc_chunks, new_doc_chunks)
    
    # Handle trivial cases
    if structured_diff['stats']['change_ratio'] == 0.0:
        summary = ChangeSummary(
            summary_text="No changes detected between versions.",
            major_changes=[],
            minor_changes=[],
            impact_assessment="None",
            action_required="No action required.",
            confidence=1.0,
            generated_at=datetime.now()
        )
        if use_cache:
            _cache_summary(old_doc_id, new_doc_id, summary)
        return summary
    
    # Build prompt
    prompt = _build_change_summary_prompt(
        old_doc_metadata,
        new_doc_metadata,
        structured_diff
    )
    
    try:
        # Call LLM
        messages = [{"role": "user", "content": prompt}]
        response = await asyncio.to_thread(
            llm_engine.generate, messages, max_tokens=512, temperature=0.3
        )
        
        # Parse JSON response
        summary_data = _parse_summary_response(response)
        
        if not summary_data:
            # Fallback if parsing fails
            summary = ChangeSummary(
                summary_text=f"Changes detected between versions. See diff for details.",
                major_changes=[f"{structured_diff['stats']['added']} sections added",
                              f"{structured_diff['stats']['removed']} sections removed"],
                minor_changes=[],
                impact_assessment="Medium",
                action_required="Review document differences",
                confidence=0.5,
                generated_at=datetime.now()
            )
        else:
            # Validate and create summary
            impact = summary_data.get("impact_assessment", "Medium")
            if impact not in ["High", "Medium", "Low", "None"]:
                impact = "Medium"
            
            summary = ChangeSummary(
                summary_text=summary_data.get("summary_text", ""),
                major_changes=summary_data.get("major_changes", []),
                minor_changes=summary_data.get("minor_changes", []),
                impact_assessment=impact,
                action_required=summary_data.get("action_required", ""),
                confidence=_compute_summary_confidence(summary_data, structured_diff),
                generated_at=datetime.now()
            )
        
        # Cache result
        if use_cache:
            _cache_summary(old_doc_id, new_doc_id, summary)
        
        logger.info("Generated change summary for %s -> %s (impact: %s, confidence: %.2f)",
                   old_doc_id, new_doc_id, summary.impact_assessment, summary.confidence)
        
        return summary
        
    except Exception as e:
        logger.error("Failed to generate change summary: %s", e, exc_info=True)
        
        # Return fallback on error
        return ChangeSummary(
            summary_text="Change summary generation failed. Please review document diff manually.",
            major_changes=[],
            minor_changes=[],
            impact_assessment="Unknown",
            action_required="Manual review required",
            confidence=0.0,
            generated_at=datetime.now()
        )


def _parse_summary_response(response: str) -> Optional[Dict]:
    """Parse JSON from LLM response."""
    if not response:
        return None
    
    try:
        # Try direct parse
        return json.loads(response.strip())
    except json.JSONDecodeError:
        pass
    
    # Try to extract JSON from markdown
    import re
    json_match = re.search(r'```json\s*(\{.*?\})\s*```', response, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass
    
    # Try finding JSON object
    json_match = re.search(r'\{.*"summary_text".*\}', response, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass
    
    return None


def _compute_summary_confidence(summary_data: Dict, structured_diff: Dict) -> float:
    """Compute confidence score for generated summary."""
    confidence = 0.7  # Base confidence
    
    # Check if impact matches change ratio
    change_ratio = structured_diff['stats']['change_ratio']
    stated_impact = summary_data.get("impact_assessment", "Medium")
    
    impact_map = {"High": 0.8, "Medium": 0.5, "Low": 0.2, "None": 0.0}
    expected_impact_score = impact_map.get(stated_impact, 0.5)
    
    # Boost confidence if impact matches actual changes
    if abs(change_ratio - expected_impact_score) < 0.3:
        confidence += 0.15
    
    # Boost if major changes count matches actual changes
    major_changes = len(summary_data.get("major_changes", []))
    actual_changes = structured_diff['stats']['added'] + structured_diff['stats']['removed']
    
    if 0 < major_changes <= actual_changes:
        confidence += 0.1
    
    return min(1.0, confidence)


def format_change_summary_for_storage(summary: ChangeSummary) -> Dict[str, Any]:
    """Format ChangeSummary for database storage."""
    return {
        "summary_text": summary.summary_text,
        "major_changes": summary.major_changes,
        "minor_changes": summary.minor_changes,
        "impact_assessment": summary.impact_assessment,
        "action_required": summary.action_required,
        "confidence": summary.confidence,
        "generated_at": summary.generated_at.isoformat()
    }


# Async support
import asyncio


async def generate_and_store_change_summary(
    old_doc_id: str,
    new_doc_id: str,
    store,  # VectorStore
    backend_api_url: str,
    auth_token: str
) -> Optional[Dict]:
    """
    Generate change summary and store in backend.
    
    Args:
        old_doc_id: Previous version document ID
        new_doc_id: Current version document ID
        store: VectorStore instance
        backend_api_url: Backend API base URL
        auth_token: Authentication token
    
    Returns:
        Stored summary data or None
    """
    from api.rag.vector_store import get_store
    import httpx
    
    try:
        # Get chunks for both docs
        old_chunks = store.get_chunks_by_doc(old_doc_id)
        new_chunks = store.get_chunks_by_doc(new_doc_id)
        
        if not old_chunks or not new_chunks:
            logger.warning("Cannot generate summary: missing chunks for %s or %s", 
                          old_doc_id, new_doc_id)
            return None
        
        # Build metadata
        old_meta = {"doc_id": old_doc_id, "chunks": len(old_chunks)}
        new_meta = {"doc_id": new_doc_id, "chunks": len(new_chunks)}
        
        # Generate summary
        summary = await generate_change_summary(
            old_doc_id, new_doc_id,
            old_chunks, new_chunks,
            old_meta, new_meta
        )
        
        # Store in backend
        storage_data = format_change_summary_for_storage(summary)
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{backend_api_url}/api/documents/{new_doc_id}/changes",
                json=storage_data,
                params={"from_doc_id": old_doc_id},
                headers={"Authorization": f"Bearer {auth_token}"} if auth_token else {}
            )
            
            if response.status_code == 200:
                logger.info("Stored change summary for %s -> %s", old_doc_id, new_doc_id)
                return response.json()
            else:
                logger.warning("Failed to store change summary: %s", response.status_code)
                return None
                
    except Exception as e:
        logger.error("Error in generate_and_store_change_summary: %s", e, exc_info=True)
        return None

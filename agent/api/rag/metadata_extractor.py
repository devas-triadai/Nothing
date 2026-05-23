"""
Module 7 — Automated Metadata Extraction
LLM-based extraction of version refs, cross-refs, amendments, technical entities.
"""

import logging
import json
import re
from typing import Dict, List, Optional, Any
from datetime import datetime
import asyncio

from api.rag import llm as llm_engine

logger = logging.getLogger("agra.metadata_extractor")

# Confidence threshold for storing extracted metadata
MIN_CONFIDENCE_THRESHOLD = 0.6

# Max text length to send to LLM (avoid token overflow)
MAX_TEXT_LENGTH = 8000


async def extract_document_metadata(text: str, filename: str) -> Dict[str, Any]:
    """
    Use LLM to extract structured metadata from document text.
    
    Args:
        text: Document text content
        filename: Original filename (sanitized before use)
    
    Returns:
        Dict with extracted metadata and confidence score:
        {
            "version_refs": ["v1.0", "Rev 2", ...],
            "cross_references": [{"doc": "IMO SOLAS", "ref": "Ch II-2"}, ...],
            "amendment_dates": ["2024-01-15", ...],
            "effective_date": "2024-06-01",
            "supersession_info": {"supersedes": "Doc A", "superseded_by": "Doc B"},
            "equipment_types": ["fire pump", "smoke detector", ...],
            "ship_types": ["cargo", "passenger", "tanker", ...],
            "regulation_categories": ["safety", "environmental", ...],
            "confidence": 0.0-1.0
        }
    """
    # Sanitize filename to prevent prompt injection
    safe_filename = _sanitize_filename(filename)
    
    # Truncate text if too long
    truncated_text = text[:MAX_TEXT_LENGTH]
    if len(text) > MAX_TEXT_LENGTH:
        truncated_text += "\n[Content truncated for metadata extraction]"
    
    # Build extraction prompt
    prompt = f"""Analyze this technical document and extract structured metadata.

FILENAME: {safe_filename}

DOCUMENT TEXT:
{truncated_text}

Extract the following information and return ONLY a JSON object:
{{
    "version_refs": ["v1.0", "Rev 2", "Version 3.5"],
    "cross_references": [
        {{"doc": "IMO SOLAS", "ref": "Chapter II-2", "section": "Regulation 10"}},
        {{"doc": "MARPOL Annex VI", "ref": "Regulation 14"}}
    ],
    "amendment_dates": ["2024-01-15", "2023-06-01"],
    "effective_date": "2024-06-01",
    "supersession_info": {{
        "supersedes": "Previous Document Name",
        "superseded_by": "Newer Document Name",
        "amends": "Original Regulation"
    }},
    "equipment_types": ["fire pump", "smoke detector", "life raft", "EPIRB"],
    "ship_types": ["cargo", "passenger", "tanker", "fishing", "naval"],
    "regulation_categories": ["safety", "environmental", "navigation", "security", "pollution"],
    "confidence": 0.85
}}

Rules:
1. Use ISO date format (YYYY-MM-DD) for all dates
2. Normalize equipment names to lowercase
3. Ship types should be general categories
4. Confidence should reflect extraction certainty (0.0-1.0)
5. If information not found, use empty arrays or null
6. Return ONLY the JSON object, no markdown, no explanation
"""

    try:
        # Run LLM extraction with timeout
        messages = [{"role": "user", "content": prompt}]
        response = await asyncio.wait_for(
            asyncio.to_thread(llm_engine.generate, messages, max_tokens=1024, temperature=0.1),
            timeout=30.0
        )
        
        # Parse JSON response
        extracted = _parse_json_response(response)
        
        if not extracted:
            logger.warning("Failed to parse LLM metadata extraction response for %s", filename)
            return {"confidence": 0.0, "extraction_error": "Parse failed"}
        
        # Validate and normalize extracted data
        validated = _validate_extracted_metadata(extracted)
        
        # Check confidence threshold
        if validated.get("confidence", 0.0) < MIN_CONFIDENCE_THRESHOLD:
            logger.info("Metadata extraction confidence too low for %s: %.2f", 
                       filename, validated.get("confidence", 0.0))
            return validated  # Return but caller should check threshold
        
        logger.info("Metadata extracted for %s with confidence %.2f", 
                   filename, validated.get("confidence", 0.0))
        
        return validated
        
    except asyncio.TimeoutError:
        logger.warning("Metadata extraction timeout for %s", filename)
        return {"confidence": 0.0, "extraction_error": "Timeout"}
    except Exception as e:
        logger.error("Metadata extraction failed for %s: %s", filename, e, exc_info=True)
        return {"confidence": 0.0, "extraction_error": str(e)}


def _sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent prompt injection.
    Removes dangerous characters and limits length.
    """
    # Remove any characters that could be used for injection
    # Keep only alphanumeric, dots, dashes, underscores, spaces
    sanitized = re.sub(r'[^\w\s.-]', '', filename)
    
    # Limit length
    if len(sanitized) > 100:
        sanitized = sanitized[:100]
    
    return sanitized


def _parse_json_response(response: str) -> Optional[Dict]:
    """
    Parse JSON from LLM response, handling common formatting issues.
    """
    if not response:
        return None
    
    # Try direct JSON parse
    try:
        return json.loads(response.strip())
    except json.JSONDecodeError:
        pass
    
    # Try extracting JSON from markdown code blocks
    json_pattern = r'```(?:json)?\s*(\{.*?\})\s*```'
    matches = re.findall(json_pattern, response, re.DOTALL)
    
    for match in matches:
        try:
            return json.loads(match.strip())
        except json.JSONDecodeError:
            continue
    
    # Try finding JSON object between curly braces
    brace_pattern = r'\{.*"version_refs".*\}'
    match = re.search(brace_pattern, response, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    
    return None


def _validate_extracted_metadata(data: Dict) -> Dict:
    """
    Validate and normalize extracted metadata.
    Ensures dates are ISO format, arrays are clean, confidence is float.
    """
    validated = {
        "version_refs": [],
        "cross_references": [],
        "amendment_dates": [],
        "effective_date": None,
        "supersession_info": {},
        "equipment_types": [],
        "ship_types": [],
        "regulation_categories": [],
        "confidence": 0.0,
    }
    
    # Version refs: list of strings
    if "version_refs" in data and isinstance(data["version_refs"], list):
        validated["version_refs"] = [
            str(v).strip() for v in data["version_refs"] 
            if v and len(str(v).strip()) > 0
        ]
    
    # Cross references: list of dicts with doc, ref keys
    if "cross_references" in data and isinstance(data["cross_references"], list):
        for ref in data["cross_references"]:
            if isinstance(ref, dict) and "doc" in ref:
                validated["cross_references"].append({
                    "doc": str(ref["doc"]).strip(),
                    "ref": str(ref.get("ref", "")).strip(),
                    "section": str(ref.get("section", "")).strip()
                })
    
    # Amendment dates: validate ISO format
    if "amendment_dates" in data and isinstance(data["amendment_dates"], list):
        for date_str in data["amendment_dates"]:
            validated_date = _validate_date(date_str)
            if validated_date:
                validated["amendment_dates"].append(validated_date)
    
    # Effective date: validate ISO format
    if "effective_date" in data:
        validated["effective_date"] = _validate_date(data["effective_date"])
    
    # Supersession info: dict
    if "supersession_info" in data and isinstance(data["supersession_info"], dict):
        sinfo = data["supersession_info"]
        validated["supersession_info"] = {
            k: str(v).strip() for k, v in sinfo.items() 
            if v and k in ["supersedes", "superseded_by", "amends"]
        }
    
    # Equipment types: normalize to lowercase
    if "equipment_types" in data and isinstance(data["equipment_types"], list):
        validated["equipment_types"] = [
            str(e).lower().strip() for e in data["equipment_types"]
            if e and len(str(e).strip()) > 1
        ]
    
    # Ship types: normalize to lowercase
    if "ship_types" in data and isinstance(data["ship_types"], list):
        validated["ship_types"] = [
            str(s).lower().strip() for s in data["ship_types"]
            if s and len(str(s).strip()) > 1
        ]
    
    # Regulation categories: normalize to lowercase
    if "regulation_categories" in data and isinstance(data["regulation_categories"], list):
        validated["regulation_categories"] = [
            str(c).lower().strip() for c in data["regulation_categories"]
            if c and len(str(c).strip()) > 1
        ]
    
    # Confidence: ensure float 0.0-1.0
    if "confidence" in data:
        try:
            conf = float(data["confidence"])
            validated["confidence"] = max(0.0, min(1.0, conf))
        except (ValueError, TypeError):
            validated["confidence"] = 0.0
    
    return validated


def _validate_date(date_str: Any) -> Optional[str]:
    """
    Validate and normalize date string to ISO format (YYYY-MM-DD).
    Returns None if invalid.
    """
    if not date_str:
        return None
    
    date_str = str(date_str).strip()
    
    # Common date patterns
    patterns = [
        r'^(\d{4})-(\d{2})-(\d{2})$',  # YYYY-MM-DD
        r'^(\d{2})/(\d{2})/(\d{4})$',  # MM/DD/YYYY
        r'^(\d{2})-(\d{2})-(\d{4})$',  # DD-MM-YYYY
        r'^(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{4})$',  # 15 Jan 2024
    ]
    
    for pattern in patterns:
        match = re.match(pattern, date_str, re.IGNORECASE)
        if match:
            try:
                if len(match.groups()) == 3:
                    # Try parsing as YYYY-MM-DD first
                    if pattern == patterns[0]:
                        year, month, day = match.groups()
                        dt = datetime(int(year), int(month), int(day))
                        return dt.strftime("%Y-%m-%d")
                    # MM/DD/YYYY
                    elif pattern == patterns[1]:
                        month, day, year = match.groups()
                        dt = datetime(int(year), int(month), int(day))
                        return dt.strftime("%Y-%m-%d")
                    # DD-MM-YYYY
                    elif pattern == patterns[2]:
                        day, month, year = match.groups()
                        dt = datetime(int(year), int(month), int(day))
                        return dt.strftime("%Y-%m-%d")
                    # Text month
                    elif pattern == patterns[3]:
                        day, month_str, year = match.groups()
                        month_map = {
                            'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
                            'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
                        }
                        month = month_map.get(month_str[:3].lower())
                        if month:
                            dt = datetime(int(year), month, int(day))
                            return dt.strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                continue
    
    return None


async def extract_batch_metadata(
    documents: List[Dict[str, str]],
    max_concurrency: int = 3
) -> List[Dict[str, Any]]:
    """
    Extract metadata for multiple documents with concurrency control.
    
    Args:
        documents: List of { "text": str, "filename": str, "doc_id": str }
        max_concurrency: Max parallel extractions
    
    Returns:
        List of metadata dicts (same order as input)
    """
    semaphore = asyncio.Semaphore(max_concurrency)
    
    async def extract_with_limit(doc):
        async with semaphore:
            return await extract_document_metadata(doc["text"], doc["filename"])
    
    tasks = [extract_with_limit(doc) for doc in documents]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Replace exceptions with error dicts
    final_results = []
    for result in results:
        if isinstance(result, Exception):
            final_results.append({"confidence": 0.0, "extraction_error": str(result)})
        else:
            final_results.append(result)
    
    return final_results


def format_metadata_for_storage(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format extracted metadata for database storage.
    Removes empty fields to save space.
    """
    if not metadata or metadata.get("confidence", 0.0) < MIN_CONFIDENCE_THRESHOLD:
        return {}
    
    # Only include non-empty fields
    storage_data = {}
    for key, value in metadata.items():
        if key == "extraction_error":
            continue  # Don't store errors
        if value and value != [] and value != {}:
            storage_data[key] = value
    
    return storage_data

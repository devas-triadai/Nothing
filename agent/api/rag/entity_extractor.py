"""
Module 7 Phase 4 — Entity Extraction
Extracts technical entities from document text for lineage tracking.
Uses LLM-based extraction with post-processing and normalization.
"""

import logging
import json
import re
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass

from api.rag import llm as llm_engine

logger = logging.getLogger("agra.entity_extractor")

# Maximum text length to send to LLM (to avoid token limits)
MAX_TEXT_LENGTH = 5000

# Entity types we want to extract
ENTITY_TYPES = {
    "equipment": "Physical equipment, machinery, devices, systems",
    "ship_type": "Vessel categories and ship classifications",
    "regulation": "Regulatory references, codes, standards",
    "requirement": "Mandatory requirements, specifications, criteria",
    "standard": "Industry standards, ISO, IEC, IMO references",
    "material": "Material specifications, substances, compounds",
    "process": "Procedures, processes, methodologies",
    "location": "Locations, zones, compartments on vessel"
}


@dataclass
class ExtractedEntity:
    """Represents a single extracted entity."""
    entity_type: str
    name: str
    normalized_name: str
    context: str
    confidence: float
    chunk_index: Optional[int] = None
    page_number: Optional[int] = None


def normalize_entity_name(name: str) -> str:
    """
    Normalize entity name for matching.
    - Lowercase
    - Remove special characters except alphanumeric and spaces
    - Normalize whitespace
    - Remove common stopwords
    """
    # Lowercase
    normalized = name.lower()
    
    # Remove special characters but keep alphanumeric and spaces
    normalized = re.sub(r'[^\w\s]', ' ', normalized)
    
    # Normalize whitespace
    normalized = ' '.join(normalized.split())
    
    # Remove common equipment modifiers that don't change identity
    stopwords = {'the', 'a', 'an', 'system', 'unit', 'device', 'type', 'model'}
    words = [w for w in normalized.split() if w not in stopwords]
    
    normalized = ' '.join(words)
    
    return normalized


def _build_extraction_prompt(text: str) -> str:
    """Build LLM prompt for entity extraction."""
    
    entity_descriptions = "\n".join([f"- {k}: {v}" for k, v in ENTITY_TYPES.items()])
    
    return f"""Analyze this maritime/technical document text and extract all significant entities.

Extract the following entity types:
{entity_descriptions}

For each entity found, provide:
1. entity_type: One of the types above
2. name: The exact name as it appears in text
3. context: The sentence or phrase containing this entity (for verification)

Document text:
{text[:MAX_TEXT_LENGTH]}

Return ONLY a JSON array of entities in this format:
[
  {{"entity_type": "equipment", "name": "fire pump", "context": "The fire pump must be capable of..."}},
  {{"entity_type": "regulation", "name": "SOLAS Chapter II-2", "context": "As per SOLAS Chapter II-2, all vessels must..."}},
  {{"entity_type": "ship_type", "name": "oil tanker", "context": "For oil tankers over 5000 GT..."}}
]

Rules:
- Only extract entities that clearly match the defined types
- Include specific model numbers when available (e.g., "EPIRB Model XYZ")
- Regulations should include chapter/section if mentioned
- Ship types should be specific (not just "vessel")
- Context must be the full sentence, not just the entity name
- Return empty array [] if no entities found
"""


async def extract_entities_from_text(
    text: str,
    chunk_index: Optional[int] = None,
    page_number: Optional[int] = None
) -> List[ExtractedEntity]:
    """
    Extract entities from text using LLM.
    
    Args:
        text: Document text to analyze
        chunk_index: Which chunk this is (for tracking)
        page_number: Page number if available
    
    Returns:
        List of ExtractedEntity objects
    """
    if not text or len(text.strip()) < 20:
        return []
    
    prompt = _build_extraction_prompt(text)
    
    try:
        messages = [{"role": "user", "content": prompt}]
        response = await asyncio.to_thread(
            llm_engine.generate, messages, max_tokens=1024, temperature=0.1
        )
        
        # Parse JSON response
        entities_data = _parse_json_response(response)
        
        if not entities_data:
            return []
        
        # Convert to ExtractedEntity objects with validation
        extracted = []
        for entity_data in entities_data:
            try:
                entity_type = entity_data.get("entity_type", "").lower()
                name = entity_data.get("name", "").strip()
                context = entity_data.get("context", "").strip()
                
                # Validate
                if not name or len(name) < 2:
                    continue
                
                if entity_type not in ENTITY_TYPES:
                    # Try to map to known type or skip
                    entity_type = _map_entity_type(entity_type)
                    if not entity_type:
                        continue
                
                # Compute confidence based on extraction quality
                confidence = _compute_extraction_confidence(entity_data, text)
                
                # Create entity
                entity = ExtractedEntity(
                    entity_type=entity_type,
                    name=name,
                    normalized_name=normalize_entity_name(name),
                    context=context if context else text[:200],
                    confidence=confidence,
                    chunk_index=chunk_index,
                    page_number=page_number
                )
                
                extracted.append(entity)
                
            except Exception as e:
                logger.debug("Failed to process entity data: %s", e)
                continue
        
        # Deduplicate by normalized name within same type
        seen = set()
        deduplicated = []
        for entity in extracted:
            key = (entity.entity_type, entity.normalized_name)
            if key not in seen:
                seen.add(key)
                deduplicated.append(entity)
        
        logger.info("Extracted %d unique entities from chunk %s", 
                   len(deduplicated), chunk_index)
        
        return deduplicated
        
    except Exception as e:
        logger.error("Entity extraction failed: %s", e, exc_info=True)
        return []


def _parse_json_response(response: str) -> List[Dict]:
    """Parse JSON array from LLM response."""
    if not response:
        return []
    
    try:
        # Try direct parse
        return json.loads(response.strip())
    except json.JSONDecodeError:
        pass
    
    # Try to extract JSON array from markdown
    import re
    json_match = re.search(r'\[.*\]', response, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass
    
    return []


def _map_entity_type(raw_type: str) -> Optional[str]:
    """Map various entity type names to standard types."""
    mapping = {
        "equipment": "equipment",
        "device": "equipment",
        "machinery": "equipment",
        "machine": "equipment",
        "ship": "ship_type",
        "vessel": "ship_type",
        "boat": "ship_type",
        "rule": "regulation",
        "code": "regulation",
        "law": "regulation",
        "spec": "requirement",
        "specification": "requirement",
        "criteria": "requirement",
        "iso": "standard",
        "iec": "standard",
        "imo": "standard",
        "material": "material",
        "substance": "material",
        "procedure": "process",
        "method": "process",
        "zone": "location",
        "area": "location",
        "compartment": "location"
    }
    
    return mapping.get(raw_type.lower())


def _compute_extraction_confidence(entity_data: Dict, source_text: str) -> float:
    """Compute confidence score for extracted entity."""
    confidence = 0.7  # Base confidence
    
    name = entity_data.get("name", "")
    context = entity_data.get("context", "")
    
    # Boost if context contains the entity name
    if name and context and name.lower() in context.lower():
        confidence += 0.15
    
    # Boost for longer, more specific names
    if len(name) > 10:
        confidence += 0.05
    
    # Boost if entity appears multiple times in source
    if source_text and name:
        occurrences = source_text.lower().count(name.lower())
        if occurrences > 1:
            confidence += 0.05
    
    return min(1.0, confidence)


async def extract_entities_from_chunks(
    chunks: List[Dict[str, Any]],
    max_chunks: int = 10
) -> List[ExtractedEntity]:
    """
    Extract entities from multiple chunks.
    Samples chunks for efficiency if too many.
    
    Args:
        chunks: List of chunk dicts with 'text', optionally 'chunk_index', 'page'
        max_chunks: Maximum chunks to analyze
    
    Returns:
        Consolidated list of unique entities
    """
    if not chunks:
        return []
    
    # Sample chunks if too many (first, middle, last)
    n = len(chunks)
    if n > max_chunks:
        indices = [0, n // 4, n // 2, 3 * n // 4, n - 1]
        selected_chunks = [chunks[i] for i in indices if i < n]
    else:
        selected_chunks = chunks
    
    all_entities = []
    
    for chunk in selected_chunks:
        text = chunk.get("text", "")
        chunk_index = chunk.get("chunk_index")
        page = chunk.get("page_number") or chunk.get("page")
        
        entities = await extract_entities_from_text(text, chunk_index, page)
        all_entities.extend(entities)
    
    # Deduplicate across all chunks
    seen = set()
    unique_entities = []
    for entity in all_entities:
        key = (entity.entity_type, entity.normalized_name)
        if key not in seen:
            seen.add(key)
            unique_entities.append(entity)
        else:
            # Merge contexts if duplicate
            existing = next(e for e in unique_entities 
                          if e.entity_type == entity.entity_type 
                          and e.normalized_name == entity.normalized_name)
            if len(existing.context) < 100:
                existing.context += f" ...also: {entity.context[:100]}"
    
    logger.info("Extracted %d total unique entities from %d chunks", 
               len(unique_entities), len(chunks))
    
    return unique_entities


import asyncio  # For to_thread


# Rule-based extractors for common patterns (faster than LLM for simple cases)
def extract_regulations_rule_based(text: str) -> List[Dict]:
    """Extract regulation references using regex patterns."""
    regulations = []
    
    # Patterns like "SOLAS Chapter II-2", "MARPOL Annex VI", "STCW Code A"
    patterns = [
        r'(SOLAS|MARPOL|STCW|ISPS|ISMM)\s+(?:Chapter|Ch|Annex|Regulation|Code)\s+[IVX0-9-]+',
        r'(ISO|IEC)\s+\d{4,5}(?:-\d+)?',
        r'IMO\s+(?:Resolution|Circular)\s+[A-Z.0-9/-]+'
    ]
    
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            regulations.append({
                "entity_type": "regulation",
                "name": match.group(0),
                "context": text[max(0, match.start()-50):match.end()+50]
            })
    
    return regulations


def extract_equipment_rule_based(text: str) -> List[Dict]:
    """Extract equipment mentions using keyword matching."""
    equipment_keywords = [
        "fire pump", "smoke detector", "sprinkler", "extinguisher", "EPIRB",
        "lifeboat", "liferaft", "radar", "GPS", "AIS", "ECDIS", "compass",
        "gyro", "engine", "generator", "boiler", "pump", "valve", "tank"
    ]
    
    equipment = []
    text_lower = text.lower()
    
    for keyword in equipment_keywords:
        for match in re.finditer(r'\b' + re.escape(keyword) + r'\b', text_lower):
            start = max(0, match.start() - 50)
            end = min(len(text), match.end() + 50)
            equipment.append({
                "entity_type": "equipment",
                "name": keyword,
                "context": text[start:end]
            })
    
    return equipment

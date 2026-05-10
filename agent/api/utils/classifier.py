"""
AGRA — Intelligent Document Classifier (Phase 1)
Two-tier auto-classification engine:
  Tier 1: Fast heuristic (filename regex + content keyword scan) — ~0ms
  Tier 2: LLM deep classification (first 1000 tokens) — ~300ms

Shared by agent auto_ingest and admin backend upload.
"""

import hashlib
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("agra.classifier")


# ═══════════════════════════════════════════════════════════════
#  TIER 1 — FAST HEURISTIC CLASSIFICATION
# ═══════════════════════════════════════════════════════════════

_FILENAME_PATTERNS = [
    (r"(?i)(SOTR|SOR|specification|standard|requirement|norm|ISO|BIS|MIL.STD|ABS|LR|DNV|IRS|IACS)", "Standard", "specification,requirements"),
    (r"(?i)(blueprint|drawing|GA|general.arrangement|piping|schematic|diagram|layout|assembly|cross.section|structural)", "Blueprint", "engineering,drawing"),
    (r"(?i)(SOP|operational|procedure|manual|guideline|protocol|instruction|checklist)", "SOP", "operational,procedure"),
    (r"(?i)(report|analysis|assessment|survey|inspection|audit|finding|observation|review)", "Report", "report,assessment"),
    (r"(?i)(compliance|regulation|rule|act|policy|circular|notification|amendment|addendum)", "Compliance", "regulatory,compliance"),
    (r"(?i)(proposal|bid|tender|quotation|RFP|RFQ|techno.commercial|price.bid|commercial)", "Bid Document", "procurement,tender"),
    (r"(?i)(missile|weapon|torpedo|gun|armament|munition|ordnance|warhead)", "Weapon System", "defense,armament"),
    (r"(?i)(ship|vessel|OPV|patrol|frigate|corvette|hull|propulsion|engine|machinery)", "Vessel Document", "naval,ship"),
    (r"(?i)(training|course|syllabus|HR|human.resource|personnel|roster)", "Training", "training,personnel"),
    (r"(?i)(SOLAS|MARPOL|STCW|IMO|convention|resolution|MSC|MEPC)", "IMO Standard", "imo,convention,maritime"),
    (r"(?i)(ICG|coast.guard|maritime|naval|navy|defense|defence)", "ICG Document", "coast_guard,maritime"),
]

_CONTENT_PATTERNS = [
    (r"(?i)STANDARD\s+OPERATING\s+PROCEDURE", "SOP", "operational,procedure", 0.95),
    (r"(?i)STATEMENT\s+OF\s+TECHNICAL\s+REQUIREMENTS", "SOTR", "specification,requirements,sotr", 0.98),
    (r"(?i)GENERAL\s+ARRANGEMENT", "Blueprint", "engineering,drawing,ga", 0.95),
    (r"(?i)(SOLAS|SAFETY\s+OF\s+LIFE\s+AT\s+SEA)", "IMO Standard", "imo,solas,safety", 0.95),
    (r"(?i)(MARPOL|MARINE\s+POLLUTION)", "IMO Standard", "imo,marpol,pollution", 0.95),
    (r"(?i)STCW|STANDARDS?\s+OF\s+TRAINING", "IMO Standard", "imo,stcw,training", 0.95),
    (r"(?i)COMPLIANCE\s+(REPORT|ANALYSIS|CHECK)", "Compliance", "regulatory,compliance", 0.90),
    (r"(?i)(TENDER|BID)\s+(DOCUMENT|SUBMISSION|PROPOSAL)", "Bid Document", "procurement,tender", 0.92),
    (r"(?i)(SEARCH\s+AND\s+RESCUE|SAR\s+OPERATION)", "SOP", "sar,operations,procedure", 0.90),
    (r"(?i)(POLLUTION\s+RESPONSE|OIL\s+SPILL)", "SOP", "pollution,response,procedure", 0.90),
    (r"(?i)(PORT\s+FACILITY\s+SECURITY|ISPS\s+CODE)", "Compliance", "isps,port_security", 0.90),
    (r"(?i)(HEADQUARTERS\s+DIRECTIVE|ICG/OPS)", "ICG Document", "directive,coast_guard", 0.92),
    (r"(?i)(REGULATION\s+\d+|CHAPTER\s+\d+|ANNEX\s+[IVXLCDM]+)", "Standard", "regulation,chapter", 0.70),
    (r"(?i)(INSPECTION|SURVEY|AUDIT)\s+(REPORT|FINDING)", "Report", "inspection,report", 0.85),
    (r"(?i)(MACHINERY|PROPULSION|ENGINE)\s+(SPECIFICATION|REQUIREMENT)", "Standard", "machinery,specification", 0.85),
]


def compute_sha256(content: bytes) -> str:
    """Compute SHA-256 hash of file content for tamper detection and dedup."""
    return hashlib.sha256(content).hexdigest()


def classify_tier1(
    filename: str,
    file_type: str,
    content_preview: str = "",
) -> Dict[str, Any]:
    """
    Tier 1 — Fast heuristic classification.
    Uses filename patterns + first N chars of extracted text.

    Returns:
        {
            "category": str,
            "sub_category": str,
            "tags": str (comma-separated),
            "confidence": float (0-1),
            "tier": 1,
            "detected_entities": List[str],
            "summary": str,
        }
    """
    # Image files → Imagery
    if file_type in ("png", "jpg", "jpeg", "bmp", "tiff", "tif"):
        return {
            "category": "Imagery",
            "sub_category": "Scan/Photo",
            "tags": "visual,scan,image",
            "confidence": 0.95,
            "tier": 1,
            "detected_entities": [],
            "summary": f"Image file: {filename}",
        }

    # Spreadsheet → Data/Report
    if file_type in ("xlsx", "xls", "csv"):
        return {
            "category": "Report",
            "sub_category": "Data/Spreadsheet",
            "tags": "data,spreadsheet",
            "confidence": 0.80,
            "tier": 1,
            "detected_entities": [],
            "summary": f"Spreadsheet: {filename}",
        }

    # Presentation
    if file_type in ("pptx", "ppt"):
        return {
            "category": "Presentation",
            "sub_category": "Briefing/Slides",
            "tags": "slides,briefing",
            "confidence": 0.85,
            "tier": 1,
            "detected_entities": [],
            "summary": f"Presentation: {filename}",
        }

    best_cat = "General"
    best_sub = ""
    best_tags = "uncategorized"
    best_conf = 0.0
    detected_entities: List[str] = []

    # --- Pass 1: Content-based patterns (higher priority) ---
    if content_preview:
        for pattern, cat, tags, conf in _CONTENT_PATTERNS:
            matches = re.findall(pattern, content_preview[:3000])
            if matches:
                if conf > best_conf:
                    best_cat = cat
                    best_tags = tags
                    best_conf = conf
                for m in matches:
                    entity = m if isinstance(m, str) else m[0] if m else ""
                    if entity and entity not in detected_entities:
                        detected_entities.append(entity.strip())

    # --- Pass 2: Filename-based patterns ---
    for pattern, cat, tags in _FILENAME_PATTERNS:
        if re.search(pattern, filename):
            fn_conf = 0.75
            if fn_conf > best_conf:
                best_cat = cat
                best_tags = tags
                best_conf = fn_conf
            break

    # Detect sub_category from content
    sub_category = _detect_sub_category(best_cat, content_preview, filename)

    # Build summary from first meaningful lines
    summary = _extract_summary(content_preview, filename)

    return {
        "category": best_cat,
        "sub_category": sub_category,
        "tags": best_tags,
        "confidence": round(best_conf, 2),
        "tier": 1,
        "detected_entities": detected_entities[:10],
        "summary": summary,
    }


def _detect_sub_category(category: str, content: str, filename: str) -> str:
    """Detect fine-grained sub-category based on content."""
    if not content:
        return ""

    sub_map = {
        "SOP": [
            (r"(?i)search\s+and\s+rescue|SAR", "Search & Rescue"),
            (r"(?i)patrol|surveillance|MDA", "Patrol & Surveillance"),
            (r"(?i)pollution|oil\s+spill|dispersant", "Pollution Response"),
            (r"(?i)port|coastal|security|ISPS", "Port & Coastal Security"),
            (r"(?i)boarding|inspection|anti.smuggling", "Law Enforcement"),
        ],
        "Standard": [
            (r"(?i)fire|safety|SOLAS", "Fire & Safety"),
            (r"(?i)hull|structural|steel", "Hull & Structure"),
            (r"(?i)propulsion|engine|machinery", "Machinery"),
            (r"(?i)electrical|power|generator", "Electrical"),
            (r"(?i)navigation|radar|communication", "Navigation & Comms"),
        ],
        "IMO Standard": [
            (r"(?i)SOLAS", "SOLAS"),
            (r"(?i)MARPOL", "MARPOL"),
            (r"(?i)STCW", "STCW"),
            (r"(?i)IMDG|dangerous\s+goods", "IMDG Code"),
        ],
    }

    patterns = sub_map.get(category, [])
    for pattern, sub in patterns:
        if re.search(pattern, content[:3000]):
            return sub
    return ""


def _extract_summary(content: str, filename: str) -> str:
    """Extract a short summary from the first meaningful lines of content."""
    if not content:
        return f"Document: {filename}"

    lines = [l.strip() for l in content.split("\n") if l.strip() and len(l.strip()) > 10]
    if not lines:
        return f"Document: {filename}"

    # Take first 2-3 meaningful lines
    summary_parts = []
    for line in lines[:3]:
        if len(line) > 150:
            line = line[:150] + "…"
        summary_parts.append(line)

    return " | ".join(summary_parts)


# ═══════════════════════════════════════════════════════════════
#  TIER 2 — LLM DEEP CLASSIFICATION (optional)
# ═══════════════════════════════════════════════════════════════

_LLM_CLASSIFY_PROMPT = """You are a document classifier for the Indian Coast Guard.
Analyze the following document content and classify it.

FILENAME: {filename}

CONTENT (first 1500 chars):
{content}

Return ONLY valid JSON:
{{
  "category": "One of: SOP, Standard, SOTR, Blueprint, Report, Compliance, Bid Document, IMO Standard, ICG Document, Vessel Document, Weapon System, Training, Presentation, Imagery, General",
  "sub_category": "Fine-grained type (e.g., 'Search & Rescue', 'SOLAS', 'Hull & Structure')",
  "tags": "comma,separated,tags",
  "detected_entities": ["key entities found in document"],
  "summary": "One sentence summary of the document's purpose and content"
}}"""


def classify_tier2(
    filename: str,
    content_preview: str,
) -> Optional[Dict[str, Any]]:
    """
    Tier 2 — LLM-based deep classification.
    Only call when Tier 1 confidence < 0.80 or for explicit re-classification.

    Returns same schema as Tier 1, or None if LLM unavailable.
    """
    try:
        from api.rag import llm as llm_engine
        import json

        prompt = _LLM_CLASSIFY_PROMPT.format(
            filename=filename,
            content=content_preview[:1500],
        )

        messages = [
            {"role": "system", "content": "You are a document classifier. Return only valid JSON."},
            {"role": "user", "content": prompt},
        ]

        raw = llm_engine.generate(messages, max_tokens=512, temperature=0.1)

        # Clean and parse JSON
        cleaned = re.sub(r'^```(?:json)?\s*', '', raw.strip(), flags=re.MULTILINE)
        cleaned = re.sub(r'```\s*$', '', cleaned.strip(), flags=re.MULTILINE)
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        if start == -1 or end == 0:
            return None

        result = json.loads(cleaned[start:end])
        result["confidence"] = 0.90
        result["tier"] = 2
        logger.info("LLM classified %s → %s (sub: %s)", filename, result.get("category"), result.get("sub_category"))
        return result

    except Exception as e:
        logger.warning("Tier 2 classification failed for %s: %s", filename, e)
        return None


def classify_document(
    filename: str,
    file_type: str,
    content_preview: str = "",
    force_llm: bool = False,
) -> Dict[str, Any]:
    """
    Main classification entry point.
    Runs Tier 1 first; escalates to Tier 2 if confidence < 0.80 or force_llm=True.
    """
    result = classify_tier1(filename, file_type, content_preview)

    if force_llm or result["confidence"] < 0.80:
        llm_result = classify_tier2(filename, content_preview)
        if llm_result and llm_result.get("confidence", 0) > result["confidence"]:
            return llm_result

    return result

"""
AGRA Phase 3 — Enhanced Drawing Pipeline
Stage-wise processing with confidence tracking and structured output.

Pipeline Stages:
1. Ingest — PDF→Image conversion
2. Classify — Drawing type detection (Phase 1)
3. Preprocess — OpenCV enhancement
4. OCR — Tesseract + TrOCR
5. Extract — VLM structured extraction
6. Validate — Measurement validation
7. Index — Store in vector store
8. Respond — Return structured JSON
"""

import base64
import json
import logging
import time
import uuid
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from sqlalchemy.orm import Session

from api.models.models import AsyncJob, get_agent_db
from api.models.drawing_models import (
    DrawingType, DrawingFeature, Dimension, MeasurementUnit,
    TitleBlock, EquipmentTag, ComplianceNote,
    StageConfidence, AnalysisConfidence, DrawingAnalysisResult,
    DrawingAnalysisRequest, DrawingAnalysisResponse, ChatDrawingAnalysis,
)
from api.utils.auth_check import get_current_user
from api.utils.usage_logger import log_usage
from api.rag import llm as llm_engine
from api.rag.vector_store import get_store

# Phase 1, 4, 6 imports
from api.rag.drawing_classifier import classify_drawing, _get_recommended_analysis
from api.rag.measurement_parser import parse_measurements, extract_dimensions, validate_dimensions
from api.rag.confidence_scorer import (
    calculate_ocr_confidence,
    calculate_vlm_confidence,
    calculate_validation_score,
    calculate_title_block_completeness,
    calculate_overall_confidence,
    assess_result_quality,
)
from api.rag import tesseract_ocr as hybrid_ocr

logger = logging.getLogger("agra.drawing_pipeline")
router = APIRouter()


# ═══════════════════════════════════════════════════════════════
#  STAGE DEFINITIONS
# ═══════════════════════════════════════════════════════════════

class PipelineStage:
    """Represents a single pipeline stage with confidence tracking."""
    def __init__(self, name: str, weight: float):
        self.name = name
        self.weight = weight  # Weight in overall confidence calculation
        self.confidence = 0.0
        self.status = "pending"
        self.details = ""
        self.start_time = None
        self.end_time = None
    
    def start(self):
        self.start_time = time.time()
        self.status = "running"
    
    def complete(self, confidence: float, details: str = ""):
        self.confidence = confidence
        self.status = "success"
        self.details = details
        self.end_time = time.time()
    
    def fail(self, error: str):
        self.status = "failed"
        self.details = error
        self.end_time = time.time()
    
    def to_model(self) -> StageConfidence:
        return StageConfidence(
            stage_name=self.name,
            confidence=round(self.confidence, 2),
            status=self.status,
            details=self.details
        )


# ═══════════════════════════════════════════════════════════════
#  STAGE 1: INGEST
# ═══════════════════════════════════════════════════════════════

def stage_ingest(file_bytes: bytes, content_type: str, filename: str) -> Tuple[str, bytes, float]:
    """
    Convert input to processable image format.
    
    Returns:
        (data_uri, image_bytes, confidence)
    """
    try:
        if content_type == "application/pdf":
            import fitz
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            if doc.page_count == 0:
                raise ValueError("PDF has no pages")
            
            page = doc[0]
            pix = page.get_pixmap(matrix=fitz.Matrix(300/72, 300/72))
            img_data = pix.tobytes("png")
            doc.close()
            
            base64_image = base64.b64encode(img_data).decode("utf-8")
            data_uri = f"data:image/png;base64,{base64_image}"
            return data_uri, img_data, 0.95
        
        else:
            # Already an image
            base64_image = base64.b64encode(file_bytes).decode("utf-8")
            data_uri = f"data:{content_type};base64,{base64_image}"
            return data_uri, file_bytes, 0.98
    
    except Exception as e:
        logger.error(f"Stage 1 (Ingest) failed: {e}")
        raise


# ═══════════════════════════════════════════════════════════════
#  STAGE 2: CLASSIFY
# ═══════════════════════════════════════════════════════════════

def stage_classify(
    filename: str,
    ocr_preview: str,
    image_bytes: bytes,
    content_type: str
) -> Tuple[DrawingType, float, List[DrawingFeature], str]:
    """
    Classify drawing type using Tier 1 + Tier 2.
    
    Returns:
        (drawing_type, confidence, features, recommended_analysis)
    """
    result = classify_drawing(
        filename=filename,
        ocr_text=ocr_preview,
        image_bytes=image_bytes,
        image_content_type=content_type,
        confidence_threshold=0.75
    )
    
    return (
        result["drawing_type"],
        result["confidence"],
        result["detected_features"],
        result["recommended_analysis"]
    )


# ═══════════════════════════════════════════════════════════════
#  STAGE 3: PREPROCESS
# ═══════════════════════════════════════════════════════════════

def stage_preprocess(data_uri: str, drawing_type: DrawingType) -> Tuple[str, float]:
    """
    Apply OpenCV preprocessing optimized for drawing type.
    
    Returns:
        (processed_data_uri, confidence)
    """
    try:
        from api.rag.vision import preprocess_engineering_drawing
        processed = preprocess_engineering_drawing(data_uri)
        return processed, 0.90
    except Exception as e:
        logger.warning(f"Preprocessing failed, using original: {e}")
        return data_uri, 0.50  # Lower confidence if preprocessing failed


# ═══════════════════════════════════════════════════════════════
#  STAGE 4: OCR
# ═══════════════════════════════════════════════════════════════

def stage_ocr(image_bytes: bytes) -> Tuple[Dict[str, Any], float]:
    """
    Run hybrid OCR (Tesseract + TrOCR).
    
    Returns:
        (ocr_result_dict, confidence)
    """
    ocr_result = hybrid_ocr.extract_all(image_bytes)
    
    # Calculate OCR confidence using Phase 6 confidence scorer
    confidence = calculate_ocr_confidence(ocr_result)
    
    return ocr_result, confidence


# ═══════════════════════════════════════════════════════════════
#  STAGE 5: EXTRACT (VLM)
# ═══════════════════════════════════════════════════════════════

def stage_extract_vlm(
    data_uri: str,
    ocr_result: Dict[str, Any],
    drawing_type: DrawingType,
    features: List[DrawingFeature]
) -> Tuple[Dict[str, Any], float]:
    """
    VLM-based structured extraction.
    
    Returns:
        (extracted_data, confidence)
    """
    printed_text = ocr_result.get("printed_text", "")
    handwritten_text = ocr_result.get("handwritten_text", "")
    printed_conf = ocr_result.get("printed_confidence", 0.0)
    
    # Build type-specific prompt
    ocr_context = f"""OCR-EXTRACTED PRINTED TEXT (confidence {printed_conf:.1f}%):
{printed_text if printed_text else 'No printed text detected.'}

OCR-EXTRACTED HANDWRITTEN NOTES / STAMPS:
{handwritten_text if handwritten_text else 'No handwriting detected.'}"""

    # Customize extraction based on drawing type
    type_specific_prompt = _get_type_specific_prompt(drawing_type, features)
    
    prompt = f"""You are a naval architect and military engineering analyst for the Indian Coast Guard.
You are analyzing a {drawing_type.value.replace('_', ' ')} engineering drawing.

{ocr_context}

{type_specific_prompt}

Return ONLY valid JSON matching the schema above. Ground all values in the provided OCR text."""

    messages = [
        {
            "role": "system",
            "content": "You are a military engineering parser. Return only valid JSON with extracted parameters."
        },
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_uri}}
            ]
        }
    ]
    
    try:
        raw_output = llm_engine.generate(messages, max_tokens=1200, temperature=0.1)
        
        # Parse JSON
        cleaned = re.sub(r'^```(?:json)?\s*', '', raw_output.strip(), flags=re.MULTILINE)
        cleaned = re.sub(r'```\s*$', '', cleaned.strip(), flags=re.MULTILINE)
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        
        if start == -1 or end == 0:
            raise ValueError("No JSON found in VLM response")
        
        result = json.loads(cleaned[start:end])
        
        # Calculate VLM confidence using Phase 6 confidence scorer
        confidence = calculate_vlm_confidence(result, drawing_type)
        
        return result, confidence
    
    except Exception as e:
        logger.error(f"VLM extraction failed: {e}")
        return {"error": str(e)}, 0.30


def _get_type_specific_prompt(drawing_type: DrawingType, features: List[DrawingFeature]) -> str:
    """Generate extraction prompt based on drawing type."""
    
    base_prompt = """Extract and return JSON with:
{
  "title_block": {
    "project_name": "...",
    "vessel_name": "...",
    "drawing_number": "...",
    "drawing_title": "...",
    "revision": "...",
    "scale": "...",
    "date": "...",
    "drawn_by": "...",
    "company": "..."
  },
  "dimensions": [
    {"name": "...", "value": number, "unit": "m|mm", "tolerance": "..."}
  ],
  "equipment_tags": [
    {"tag_id": "...", "description": "...", "location": "..."}
  ],
  "compliance_notes": [
    {"standard": "...", "clause": "...", "requirement": "..."}
  ]
}"""
    
    if drawing_type == DrawingType.GENERAL_ARRANGEMENT:
        return base_prompt + """

Additional GA-specific extraction:
- Hull profile shape (straight, curved, bulbous bow)
- Main dimensions: LOA, LBP, Beam, Depth, Draft
- Deck count and positions
- Superstructure locations"""
    
    elif drawing_type == DrawingType.PIPING_DIAGRAM:
        return base_prompt + """

Additional piping-specific extraction:
- Pipe sizes (nominal bore)
- Valve types and positions
- Pump identifiers
- Flow directions
- System type (bilge, ballast, fire main)"""
    
    elif drawing_type == DrawingType.ELECTRICAL_SCHEMATIC:
        return base_prompt + """

Additional electrical-specific extraction:
- Voltage levels
- Power ratings (kW)
- Cable types
- Panel locations
- Circuit identifiers"""
    
    elif drawing_type == DrawingType.STRUCTURAL_DRAWING:
        return base_prompt + """

Additional structural-specific extraction:
- Steel grades
- Plate thicknesses
- Weld symbols and types
- Frame spacing
- Section modulus references"""
    
    return base_prompt


def _calculate_extraction_confidence(result: Dict, drawing_type: DrawingType) -> float:
    """Calculate confidence based on extraction completeness."""
    scores = []
    
    # Title block completeness
    tb = result.get("title_block", {})
    tb_fields = [tb.get(f) for f in ["project_name", "vessel_name", "drawing_number", "scale"]]
    tb_score = sum(1 for f in tb_fields if f) / len(tb_fields)
    scores.append(tb_score * 0.3)
    
    # Dimensions found
    dims = result.get("dimensions", [])
    if len(dims) >= 3:
        scores.append(0.25)
    elif len(dims) >= 1:
        scores.append(0.15)
    else:
        scores.append(0.05)
    
    # Equipment tags
    tags = result.get("equipment_tags", [])
    if len(tags) >= 5:
        scores.append(0.25)
    elif len(tags) >= 1:
        scores.append(0.15)
    else:
        scores.append(0.05)
    
    # Compliance notes
    notes = result.get("compliance_notes", [])
    if notes:
        scores.append(0.2)
    else:
        scores.append(0.1)
    
    return min(sum(scores) + 0.1, 0.95)  # Base confidence + cap


# ═══════════════════════════════════════════════════════════════
#  STAGE 6: VALIDATE
# ═══════════════════════════════════════════════════════════════

def stage_validate(
    vlm_result: Dict[str, Any],
    ocr_result: Dict[str, Any]
) -> Tuple[List[Dimension], List[EquipmentTag], List[ComplianceNote], float, List]:
    """
    Validate and parse measurements from VLM result.
    
    Returns:
        (dimensions, equipment_tags, compliance_notes, confidence)
    """
    # Parse dimensions using Phase 4 measurement parser
    all_text = f"{ocr_result.get('printed_text', '')} {ocr_result.get('handwritten_text', '')}"
    
    # Also include VLM-extracted dimensions as text
    vlm_dims = vlm_result.get("dimensions", [])
    for d in vlm_dims:
        if isinstance(d, dict):
            all_text += f" {d.get('name', '')} {d.get('value', '')} {d.get('unit', '')}"
        elif isinstance(d, str):
            all_text += f" {d}"
    
    # Parse measurements
    parsed = parse_measurements(all_text, vessel_class="general", confidence_threshold=0.6)
    dimensions = parsed["dimensions"]
    
    # Parse equipment tags from VLM result
    equipment_tags = []
    for tag_data in vlm_result.get("equipment_tags", []):
        if isinstance(tag_data, dict):
            equipment_tags.append(EquipmentTag(
                tag_id=tag_data.get("tag_id", "unknown"),
                description=tag_data.get("description"),
                location=tag_data.get("location"),
                confidence=0.85 if tag_data.get("tag_id") else 0.60
            ))
    
    # Parse compliance notes
    compliance_notes = []
    for note_data in vlm_result.get("compliance_notes", []):
        if isinstance(note_data, dict):
            compliance_notes.append(ComplianceNote(
                standard_reference=note_data.get("standard"),
                clause_reference=note_data.get("clause"),
                requirement_text=note_data.get("requirement"),
                status="unverified",
                confidence=0.70
            ))
    
    # Calculate validation confidence using Phase 6 confidence scorer
    validation_conf = calculate_validation_score(dimensions, parsed["validation_issues"])
    
    return dimensions, equipment_tags, compliance_notes, validation_conf, parsed["validation_issues"]


# ═══════════════════════════════════════════════════════════════
#  STAGE 7: INDEX
# ═══════════════════════════════════════════════════════════════

def stage_index(
    job_id: str,
    filename: str,
    result: DrawingAnalysisResult
) -> float:
    """
    Index results in vector store for RAG search.
    
    Returns:
        confidence score
    """
    try:
        from api.rag import embedder
        from api.rag.vector_store import get_store
        
        # Build summary text
        summary = f"Engineering Drawing Analysis: {filename}\n"
        summary += f"Type: {result.drawing_type.value}\n"
        summary += f"Vessel: {result.title_block.vessel_name or 'Unknown'}\n"
        summary += f"Drawing: {result.title_block.drawing_number or 'Unknown'}\n"
        
        if result.dimensions:
            summary += "\nDimensions:\n"
            for d in result.dimensions[:5]:
                summary += f"- {d.name}: {d.value} {d.unit.value}\n"
        
        if result.equipment_tags:
            summary += "\nEquipment:\n"
            for t in result.equipment_tags[:5]:
                summary += f"- {t.tag_id}: {t.description or 'N/A'}\n"
        
        chunk = {
            "text": summary,
            "metadata": {
                "doc_id": f"drawing_{job_id}",
                "filename": filename,
                "category": "Engineering Drawing",
                "drawing_type": result.drawing_type.value,
                "vessel_name": result.title_block.vessel_name,
                "source": "drawing_analysis",
                "job_id": job_id,
                "analysis_confidence": result.confidence.overall_confidence,
            }
        }
        
        emb = embedder.embed_texts([summary])[0]
        store = get_store()
        store.upsert_chunks([chunk], [emb])
        
        logger.info(f"Stage 7 (Index): Drawing {job_id} indexed successfully")
        return 0.95
    
    except Exception as e:
        logger.error(f"Stage 7 (Index) failed: {e}")
        return 0.40


# ═══════════════════════════════════════════════════════════════
#  MAIN PIPELINE ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════

def run_drawing_analysis_pipeline(
    job_id: str,
    file_bytes: bytes,
    filename: str,
    content_type: str,
    db_session: Session,
    request_options: Optional[DrawingAnalysisRequest] = None
) -> DrawingAnalysisResult:
    """
    Execute full 8-stage drawing analysis pipeline.
    
    Returns:
        DrawingAnalysisResult with all stages recorded
    """
    stages: Dict[str, PipelineStage] = {
        "ingest": PipelineStage("ingest", 0.10),
        "classify": PipelineStage("classify", 0.15),
        "preprocess": PipelineStage("preprocess", 0.05),
        "ocr": PipelineStage("ocr", 0.20),
        "extract": PipelineStage("extract", 0.25),
        "validate": PipelineStage("validate", 0.15),
        "index": PipelineStage("index", 0.10),
    }
    
    start_time = time.time()
    
    try:
        # Update job status
        job = db_session.query(AsyncJob).filter(AsyncJob.id == job_id).first()
        if job:
            job.status = "processing"
            db_session.commit()
        
        # ── STAGE 1: INGEST ──
        stages["ingest"].start()
        data_uri, image_bytes, ingest_conf = stage_ingest(file_bytes, content_type, filename)
        stages["ingest"].complete(ingest_conf, f"Converted to {content_type}")
        
        # ── STAGE 2: CLASSIFY ──
        stages["classify"].start()
        # Quick OCR for classification preview
        ocr_preview = ""
        try:
            preview_ocr = hybrid_ocr.extract_printed_text(image_bytes[:1024*1024])  # 1MB limit for preview
            ocr_preview = preview_ocr.get("full_text", "")[:500]
        except:
            pass
        
        drawing_type, type_conf, features, recommended = stage_classify(
            filename, ocr_preview, image_bytes, content_type
        )
        stages["classify"].complete(type_conf, f"Detected: {drawing_type.value}")
        
        # ── STAGE 3: PREPROCESS ──
        stages["preprocess"].start()
        processed_uri, preprocess_conf = stage_preprocess(data_uri, drawing_type)
        stages["preprocess"].complete(preprocess_conf, "OpenCV enhancement applied")
        
        # Decode processed for OCR
        if processed_uri.startswith("data:"):
            _, b64 = processed_uri.split(",", 1)
            processed_bytes = base64.b64decode(b64)
        else:
            processed_bytes = base64.b64decode(processed_uri)
        
        # ── STAGE 4: OCR ──
        stages["ocr"].start()
        ocr_result, ocr_conf = stage_ocr(processed_bytes)
        stages["ocr"].complete(ocr_conf, f"Printed: {len(ocr_result.get('printed_text', ''))} chars")
        
        # ── STAGE 5: VLM EXTRACT ──
        stages["extract"].start()
        vlm_result, vlm_conf = stage_extract_vlm(
            processed_uri, ocr_result, drawing_type, features
        )
        stages["extract"].complete(vlm_conf, "Structured extraction complete")
        
        # ── STAGE 6: VALIDATE ──
        stages["validate"].start()
        dimensions, equipment_tags, compliance_notes, val_conf, validation_issues = stage_validate(
            vlm_result, ocr_result
        )
        stages["validate"].complete(val_conf, f"{len(dimensions)} dimensions validated")
        
        # Build TitleBlock
        tb_data = vlm_result.get("title_block", {})
        title_block = TitleBlock(
            project_name=tb_data.get("project_name"),
            vessel_name=tb_data.get("vessel_name"),
            drawing_number=tb_data.get("drawing_number"),
            drawing_title=tb_data.get("drawing_title"),
            revision=tb_data.get("revision"),
            scale=tb_data.get("scale"),
            date=tb_data.get("date"),
            drawn_by=tb_data.get("drawn_by"),
            company=tb_data.get("company"),
            completeness_score=0.0  # Will be calculated by confidence scorer
        )
        
        # Calculate title block completeness using Phase 6 scorer
        title_block.completeness_score = calculate_title_block_completeness(title_block)
        
        # ── STAGE 7: INDEX ──
        stages["index"].start()
        
        # Get stage scores
        stage_scores = [s.to_model() for s in stages.values()]
        
        # Calculate overall confidence using Phase 6 weighted algorithm
        overall_confidence = calculate_overall_confidence(
            ocr_confidence=ocr_conf,
            vlm_confidence=vlm_conf,
            validation_score=val_conf,
            classification_confidence=type_conf
        )
        
        # Build result
        result = DrawingAnalysisResult(
            analysis_id=job_id,
            filename=filename,
            drawing_type=drawing_type,
            drawing_type_confidence=type_conf,
            detected_features=features,
            title_block=title_block,
            dimensions=dimensions,
            equipment_tags=equipment_tags,
            compliance_notes=compliance_notes,
            confidence=AnalysisConfidence(
                overall_confidence=overall_confidence,
                drawing_type_confidence=type_conf,
                ocr_confidence=ocr_conf,
                vlm_confidence=vlm_conf,
                validation_score=val_conf,
                title_block_completeness=title_block.completeness_score,
                stage_scores=stage_scores
            ),
            processing_time_ms=(time.time() - start_time) * 1000,
            ocr_metadata=ocr_result,
            recommended_analysis=recommended,
            completed_at=datetime.utcnow()
        )
        
        index_conf = stage_index(job_id, filename, result)
        stages["index"].complete(index_conf, "Indexed in vector store")
        
        # Update job
        job = db_session.query(AsyncJob).filter(AsyncJob.id == job_id).first()
        if job:
            job.status = "completed"
            job.progress = 100
            job.result_data = result.dict()
            db_session.commit()
        
        return result
    
    except Exception as e:
        logger.error(f"Pipeline failed for job {job_id}: {e}")
        
        # Mark failed stages
        for stage in stages.values():
            if stage.status == "running" or stage.status == "pending":
                stage.fail(str(e) if stage.status == "running" else "Skipped due to earlier failure")
        
        # Update job
        job = db_session.query(AsyncJob).filter(AsyncJob.id == job_id).first()
        if job:
            job.status = "failed"
            job.error_message = str(e)
            db_session.commit()
        
        # Return partial result with error info
        return DrawingAnalysisResult(
            analysis_id=job_id,
            filename=filename,
            drawing_type=DrawingType.UNKNOWN,
            confidence=AnalysisConfidence(
                overall_confidence=0.0,
                drawing_type_confidence=0.0,
                ocr_confidence=0.0,
                vlm_confidence=0.0,
                validation_score=0.0,
                title_block_completeness=0.0,
                stage_scores=[s.to_model() for s in stages.values()]
            ),
            processing_time_ms=(time.time() - start_time) * 1000,
        )


# ═══════════════════════════════════════════════════════════════
#  API ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@router.post("/drawing/analyze", response_model=DrawingAnalysisResponse)
async def analyze_drawing(
    background_tasks: BackgroundTasks,
    image: UploadFile = File(...),
    db: Session = Depends(get_agent_db),
    user: dict = Depends(get_current_user),
):
    """
    Submit a drawing for full analysis.
    Returns a job ID for polling status.
    """
    # Validate input
    is_pdf = image.content_type == "application/pdf"
    if not image.content_type.startswith("image/") and not is_pdf:
        raise HTTPException(status_code=400, detail="File must be an image or PDF")
    
    file_bytes = await image.read()
    if len(file_bytes) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File size exceeds 20MB limit")
    
    # Create job
    job = AsyncJob(
        job_type="drawing_analysis",
        input_data={"filename": image.filename, "content_type": image.content_type}
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    
    # Queue pipeline — wrap in helper that closes DB session after use
    from api.models.models import SessionLocal
    def _run_and_close_session():
        session = SessionLocal()
        try:
            run_drawing_analysis_pipeline(
                job.id, file_bytes, image.filename, image.content_type, session
            )
        finally:
            session.close()

    background_tasks.add_task(_run_and_close_session)
    
    return DrawingAnalysisResponse(
        job_id=job.id,
        status="pending",
        estimated_completion_seconds=30
    )


@router.get("/drawing/status/{job_id}", response_model=DrawingAnalysisResponse)
async def get_analysis_status(
    job_id: str,
    db: Session = Depends(get_agent_db),
    user: dict = Depends(get_current_user),
):
    """Get status and result of drawing analysis job."""
    job = db.query(AsyncJob).filter(AsyncJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    result = None
    if job.status == "completed" and job.result_data:
        try:
            result = DrawingAnalysisResult(**job.result_data)
        except:
            pass
    
    return DrawingAnalysisResponse(
        job_id=job.id,
        status=job.status,
        result=result,
        error_message=job.error_message
    )


@router.post("/drawing/quick_classify")
async def quick_classify_drawing(
    image: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """
    Quick classification only (Tier 1).
    Returns immediately without full analysis.
    """
    file_bytes = await image.read()
    
    # Simple ingest
    if image.content_type == "application/pdf":
        import fitz
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        page = doc[0]
        pix = page.get_pixmap(matrix=fitz.Matrix(150/72, 150/72))  # Lower res for speed
        img_data = pix.tobytes("png")
        doc.close()
        base64_image = base64.b64encode(img_data).decode("utf-8")
        data_uri = f"data:image/png;base64,{base64_image}"
        image_bytes = img_data
    else:
        base64_image = base64.b64encode(file_bytes).decode("utf-8")
        data_uri = f"data:{image.content_type};base64,{base64_image}"
        image_bytes = file_bytes
    
    # Quick OCR for preview
    ocr_preview = ""
    try:
        preview = hybrid_ocr.extract_printed_text(image_bytes)
        ocr_preview = preview.get("full_text", "")[:300]
    except:
        pass
    
    # Classify
    result = classify_drawing(
        filename=image.filename,
        ocr_text=ocr_preview,
        image_bytes=image_bytes,
        image_content_type="image/png",
        confidence_threshold=0.75
    )
    
    return {
        "filename": image.filename,
        "drawing_type": result["drawing_type"].value,
        "confidence": result["confidence"],
        "detected_features": [f.value for f in result["detected_features"]],
        "recommended_analysis": result["recommended_analysis"],
        "classification_method": result["classification_method"],
    }


# ═══════════════════════════════════════════════════════════════
#  LEGACY COMPATIBILITY
# ═══════════════════════════════════════════════════════════════

# Import and re-export old endpoints for backward compatibility
from .drawing import (
    extract_parameters as _legacy_extract,
    compare_spec as _legacy_compare,
    get_job_status as _legacy_get_job,
)

# Re-wire legacy endpoints to use new pipeline where appropriate
@router.post("/drawing/extract_parameters")
async def legacy_extract_parameters(
    background_tasks: BackgroundTasks,
    image: UploadFile = File(...),
    db: Session = Depends(get_agent_db),
    user: dict = Depends(get_current_user),
):
    """Legacy endpoint - now routes to new analyze endpoint."""
    return await analyze_drawing(background_tasks, image, db, user)


@router.post("/drawing/compare_spec")
async def legacy_compare_spec(
    background_tasks: BackgroundTasks,
    spec_doc_id: str = Form(...),
    extracted_json_str: str = Form(...),
    db: Session = Depends(get_agent_db),
    user: dict = Depends(get_current_user),
):
    """Legacy compare endpoint - unchanged."""
    # Delegate to original implementation
    return await _legacy_compare(background_tasks, spec_doc_id, extracted_json_str, db, user)


@router.get("/drawing/jobs/{job_id}")
async def legacy_get_job_status(
    job_id: str,
    db: Session = Depends(get_agent_db),
    user: dict = Depends(get_current_user),
):
    """Legacy job status endpoint - routes to new status endpoint."""
    return await get_analysis_status(job_id, db, user)

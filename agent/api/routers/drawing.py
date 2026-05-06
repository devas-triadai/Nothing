"""
AGRA Phase 3 — Router: Deep Drawing Analysis
Extracts parameters and compares drawings using Background Jobs (AsyncJob).
"""
import base64
import json
import logging
import time
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from sqlalchemy.orm import Session

from api.models.models import AsyncJob, get_agent_db
from api.utils.auth_check import get_current_user
from api.rag import llm as llm_engine
from api.rag.vector_store import get_store

logger = logging.getLogger("agra.drawing")
router = APIRouter()

def _clean_json(raw: str) -> str:
    cleaned = re.sub(r'^```(?:json)?\s*', '', raw.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r'```\s*$', '', cleaned.strip(), flags=re.MULTILINE)
    return cleaned.strip()

def _run_drawing_extraction(job_id: str, data_uri: str, db_session: Session):
    try:
        # Mark processing
        job = db_session.query(AsyncJob).filter(AsyncJob.id == job_id).first()
        job.status = "processing"
        db_session.commit()

        prompt = """You are a naval architect. Analyze this engineering drawing.
Extract the following exact parameters into a JSON object. Return ONLY valid JSON and nothing else.
{
  "dimensions": ["length: X m", "beam: Y m"],
  "tolerances": ["list of tolerances found"],
  "materials": ["list of materials found"],
  "equipment_tags": ["list of equipment tags found"]
}"""

        messages = [
            {"role": "system", "content": "You are a military engineering parser. Return only JSON."},
            {"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_uri}}
            ]}
        ]

        raw_output = llm_engine.generate(messages, max_tokens=2048, temperature=0.1)
        cleaned = _clean_json(raw_output)
        
        try:
            start = cleaned.find("{")
            end = cleaned.rfind("}") + 1
            result_json = json.loads(cleaned[start:end])
        except Exception:
            result_json = {"raw": cleaned}

        job = db_session.query(AsyncJob).filter(AsyncJob.id == job_id).first()
        job.status = "completed"
        job.progress = 100
        job.result_data = result_json
        db_session.commit()
    except Exception as e:
        logger.error("Drawing extraction failed for job %s: %s", job_id, e)
        job = db_session.query(AsyncJob).filter(AsyncJob.id == job_id).first()
        job.status = "failed"
        job.error_message = str(e)
        db_session.commit()
    finally:
        db_session.close()

def _run_drawing_compare(job_id: str, extracted_json: dict, spec_doc_id: str, db_session: Session):
    try:
        job = db_session.query(AsyncJob).filter(AsyncJob.id == job_id).first()
        job.status = "processing"
        db_session.commit()

        store = get_store()
        spec_chunks = store.get_chunks_by_doc(spec_doc_id)
        spec_text = "\n\n".join(c["text"] for c in spec_chunks[:30])

        prompt = f"""You are a naval compliance officer.
Compare the parameters extracted from the engineering drawing against the SOTR/Build Specifications.

DRAWING PARAMETERS (JSON):
{json.dumps(extracted_json, indent=2)}

BUILD SPECIFICATIONS:
{spec_text[:12000]}

Return a JSON array of comparisons. For each parameter in the drawing, check if the spec allows it.
[
  {{
    "parameter": "Name of parameter (e.g. Overall Length)",
    "drawing_value": "Value from drawing",
    "spec_value": "Value required by standard",
    "status": "Compliant" | "Non-Compliant" | "Unverifiable",
    "notes": "Explanation"
  }}
]
Return ONLY JSON array.
"""
        messages = [
            {"role": "system", "content": "You are a military engineering auditor. Return only JSON arrays."},
            {"role": "user", "content": prompt}
        ]
        
        raw_output = llm_engine.generate(messages, max_tokens=2048, temperature=0.1)
        cleaned = _clean_json(raw_output)
        
        try:
            start = cleaned.find("[")
            end = cleaned.rfind("]") + 1
            result_json = json.loads(cleaned[start:end])
        except Exception:
            result_json = [{"error": "Failed to parse JSON", "raw": cleaned}]

        job = db_session.query(AsyncJob).filter(AsyncJob.id == job_id).first()
        job.status = "completed"
        job.progress = 100
        job.result_data = result_json
        db_session.commit()

    except Exception as e:
        logger.error("Drawing compare failed for job %s: %s", job_id, e)
        job = db_session.query(AsyncJob).filter(AsyncJob.id == job_id).first()
        job.status = "failed"
        job.error_message = str(e)
        db_session.commit()
    finally:
        db_session.close()


@router.post("/drawing/extract_parameters")
async def extract_parameters(
    background_tasks: BackgroundTasks,
    image: UploadFile = File(...),
    db: Session = Depends(get_agent_db),
    user: dict = Depends(get_current_user),
):
    if not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Uploaded file must be an image.")

    image_bytes = await image.read()
    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image size exceeds 10MB limit.")

    base64_image = base64.b64encode(image_bytes).decode("utf-8")
    data_uri = f"data:{image.content_type};base64,{base64_image}"

    job = AsyncJob(job_type="drawing_extraction", input_data={"filename": image.filename})
    db.add(job)
    db.commit()
    db.refresh(job)

    # Use a new DB session for the background task to prevent thread sharing issues
    from api.models.models import SessionLocal
    background_tasks.add_task(_run_drawing_extraction, job.id, data_uri, SessionLocal())

    return {"job_id": job.id, "status": "pending", "message": "Extraction job submitted."}

@router.post("/drawing/compare_spec")
async def compare_spec(
    background_tasks: BackgroundTasks,
    spec_doc_id: str = Form(...),
    extracted_json_str: str = Form(...),
    db: Session = Depends(get_agent_db),
    user: dict = Depends(get_current_user),
):
    try:
        extracted_json = json.loads(extracted_json_str)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON for extracted parameters.")

    job = AsyncJob(job_type="drawing_compare", input_data={"spec_doc_id": spec_doc_id})
    db.add(job)
    db.commit()
    db.refresh(job)

    from api.models.models import SessionLocal
    background_tasks.add_task(_run_drawing_compare, job.id, extracted_json, spec_doc_id, SessionLocal())

    return {"job_id": job.id, "status": "pending", "message": "Comparison job submitted."}

@router.get("/drawing/jobs/{job_id}")
async def get_job_status(
    job_id: str,
    db: Session = Depends(get_agent_db),
    user: dict = Depends(get_current_user),
):
    job = db.query(AsyncJob).filter(AsyncJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return {
        "job_id": job.id,
        "job_type": job.job_type,
        "status": job.status,
        "progress": job.progress,
        "result_data": job.result_data,
        "error_message": job.error_message,
    }

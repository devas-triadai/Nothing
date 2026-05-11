"""
AGRA Phase 3 — Router: Multimodal VLM
Analyzes architectural drawings, schematics, and images using the loaded VLM.
"""

import base64
import logging
import time
import json
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse

from api.utils.auth_check import get_current_user
from api.utils.usage_logger import log_usage
from api.rag import llm as llm_engine

logger = logging.getLogger("agra.vlm")

router = APIRouter()

@router.post("/vlm/analyze")
async def analyze_image(
    prompt: str = Form(...),
    image: UploadFile = File(...),
    use_ocr: bool = Form(True),
    user: dict = Depends(get_current_user),
):
    """
    Analyze an uploaded image (architectural drawing, schematic, etc.) using the VLM.
    Optionally runs hybrid OCR (Tesseract 5 + TrOCR) first to ground the VLM in exact text.
    Streams the response back to the client.
    """
    start_time = time.time()
    username = user.get("sub", "unknown")
    logger.info("VLM Request from %s: %s (use_ocr=%s)", username, prompt[:50], use_ocr)

    # Validate image
    if not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Uploaded file must be an image.")

    image_bytes = await image.read()
    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image size exceeds 10MB limit.")

    # Convert to base64
    base64_image = base64.b64encode(image_bytes).decode("utf-8")
    data_uri = f"data:{image.content_type};base64,{base64_image}"

    # ── Optional: Hybrid OCR grounding ──
    ocr_context = ""
    if use_ocr:
        try:
            from api.rag import tesseract_ocr as hybrid_ocr
            ocr_result = hybrid_ocr.extract_all(image_bytes)
            printed = ocr_result.get("printed_text", "")
            handwritten = ocr_result.get("handwritten_text", "")
            printed_conf = ocr_result.get("printed_confidence", 0.0)
            if printed or handwritten:
                ocr_context = f"""
[SYSTEM — OCR-EXTRACTED TEXT FROM IMAGE]
The following text was mechanically extracted from the image before this analysis:

PRINTED TEXT (confidence {printed_conf:.1f}%):
{printed if printed else 'None detected.'}

HANDWRITTEN NOTES / STAMPS:
{handwritten if handwritten else 'None detected.'}

When answering, ground any quoted numbers, labels, or dimensions in the OCR text above.
[/SYSTEM]
"""
        except Exception as e:
            logger.warning("OCR grounding failed for VLM, continuing without it: %s", e)

    # Build multimodal message format for llama-server (OpenAI-compatible vision)
    full_prompt = f"{prompt}\n{ocr_context}" if ocr_context else prompt

    messages = [
        {
            "role": "system",
            "content": "You are a highly skilled military architect and systems engineer for the Indian Coast Guard. You excel at analyzing technical drawings, schematics, and UI mockups. When OCR text is provided, you must ground your analysis in it."
        },
        {
            "role": "user",
            "content": [
                {"type": "text", "text": full_prompt},
                {"type": "image_url", "image_url": {"url": data_uri}}
            ]
        }
    ]

    async def event_stream():
        try:
            for tok in llm_engine.stream_generate(messages, max_tokens=2048, temperature=0.3):
                yield f"data: {json.dumps({'token': tok})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as e:
            logger.error("VLM inference failed: %s", e)
            yield f"data: {json.dumps({'error': str(e), 'done': True})}\n\n"
        finally:
            elapsed_ms = (time.time() - start_time) * 1000
            log_usage(
                action_type="vlm",
                module="vision",
                token="",
                response_time_ms=elapsed_ms,
            )

    return StreamingResponse(event_stream(), media_type="text/event-stream")

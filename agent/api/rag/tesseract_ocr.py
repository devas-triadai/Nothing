"""
AGRA Phase 4 — Hybrid OCR Engine (Tesseract 5 + TrOCR)
Military-grade text extraction for engineering drawings and scanned documents.

Architecture:
  1. Tesseract 5 (rule-based)   → printed text, title blocks, dimensions, labels
  2. TrOCR (transformer-based)  → handwritten annotations, stamps, signatures,
                                   and low-confidence printed regions

Both models are lazy-loaded as singletons to avoid blocking FastAPI startup.
"""

import base64
import io
import logging
import threading
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

logger = logging.getLogger("agra.ocr_hybrid")

# ── Lazy-loaded singletons ──
_trocr_processor = None
_trocr_model = None
_trocr_lock = threading.Lock()

_tesseract_available = None


def _check_tesseract() -> bool:
    """Check if the tesseract-ocr system binary is installed."""
    global _tesseract_available
    if _tesseract_available is not None:
        return _tesseract_available
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        _tesseract_available = True
        logger.info("Tesseract 5 is available.")
    except Exception as e:
        logger.warning("Tesseract 5 not available (%s). Printed-text OCR will be disabled.", e)
        _tesseract_available = False
    return _tesseract_available


def _load_trocr():
    """Lazy-load TrOCR model and processor (thread-safe)."""
    global _trocr_processor, _trocr_model
    if _trocr_model is not None:
        return _trocr_processor, _trocr_model

    with _trocr_lock:
        if _trocr_model is not None:
            return _trocr_processor, _trocr_model

        try:
            from transformers import TrOCRProcessor, VisionEncoderDecoderModel
            logger.info("Loading TrOCR (microsoft/trocr-large-handwritten) …")
            _trocr_processor = TrOCRProcessor.from_pretrained(
                "microsoft/trocr-large-handwritten"
            )
            _trocr_model = VisionEncoderDecoderModel.from_pretrained(
                "microsoft/trocr-large-handwritten"
            )
            logger.info("TrOCR loaded successfully.")
        except Exception as e:
            logger.error("Failed to load TrOCR: %s", e)
            _trocr_processor = None
            _trocr_model = None

    return _trocr_processor, _trocr_model


def _run_trocr_on_image(pil_img: Image.Image) -> str:
    """Run TrOCR on a PIL image. Returns decoded text or empty string."""
    processor, model = _load_trocr()
    if processor is None or model is None:
        return ""

    import torch

    try:
        pixel_values = processor(images=pil_img, return_tensors="pt").pixel_values
        generated_ids = model.generate(pixel_values)
        text = processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
        return text.strip()
    except Exception as e:
        logger.warning("TrOCR inference failed: %s", e)
        return ""


def _run_trocr_on_regions(
    pil_img: Image.Image, regions: List[Tuple[int, int, int, int]]
) -> List[str]:
    """Run TrOCR on a list of cropped regions (x, y, w, h)."""
    results = []
    for x, y, w, h in regions:
        crop = pil_img.crop((x, y, x + w, y + h))
        text = _run_trocr_on_image(crop)
        if text:
            results.append(text)
    return results


def extract_printed_text(image_input) -> Dict:
    """
    Extract printed text using Tesseract 5.
    Accepts PIL Image, numpy array, or base64/bytes.
    Returns dict with 'full_text', 'lines', 'word_count', 'confidence_avg'.
    """
    if not _check_tesseract():
        return {
            "full_text": "",
            "lines": [],
            "word_count": 0,
            "confidence_avg": 0.0,
            "error": "Tesseract 5 not installed",
        }

    import pytesseract

    # Normalise input to PIL Image
    if isinstance(image_input, np.ndarray):
        pil_img = Image.fromarray(image_input)
    elif isinstance(image_input, (str, bytes)):
        if isinstance(image_input, str):
            if "," in image_input:
                image_input = image_input.split(",", 1)[1]
            try:
                image_input = base64.b64decode(image_input)
            except Exception:
                image_input = image_input.encode()
        pil_img = Image.open(io.BytesIO(image_input))
    else:
        pil_img = image_input

    # Convert to RGB if necessary
    if pil_img.mode != "RGB":
        pil_img = pil_img.convert("RGB")

    # ── Full-text extraction ──
    full_text = pytesseract.image_to_string(
        pil_img, config="--psm 6 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz.,;:'\"!?&@#$%*()[]{}|\/+=-_<>~` \n"
    ).strip()

    # ── Data with bounding boxes + confidence ──
    data = pytesseract.image_to_data(
        pil_img, config="--psm 6", output_type=pytesseract.Output.DICT
    )

    lines = []
    confidences = []
    n_boxes = len(data["text"])

    for i in range(n_boxes):
        text = data["text"][i].strip()
        conf = int(data["conf"][i])
        if text and conf > 0:
            lines.append(text)
            confidences.append(conf)

    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

    return {
        "full_text": full_text,
        "lines": lines,
        "word_count": len(lines),
        "confidence_avg": round(avg_conf, 2),
        "raw_tesseract_data": data,
    }


def extract_handwritten_text(image_input, confidence_threshold: int = 40) -> Dict:
    """
    Extract handwritten annotations / stamps using TrOCR.
    Strategy:
      1. Run Tesseract to get all text regions.
      2. Identify low-confidence regions (< threshold) — likely handwriting or stamps.
      3. Crop those regions and run TrOCR on each.
      4. Also run TrOCR on the full image as a fallback scan.
    """
    if not _check_tesseract():
        return {
            "full_text": "",
            "regions": [],
            "error": "Tesseract 5 not installed; cannot locate handwriting regions",
        }

    import pytesseract

    # Normalise to PIL
    if isinstance(image_input, np.ndarray):
        pil_img = Image.fromarray(image_input)
    elif isinstance(image_input, (str, bytes)):
        if isinstance(image_input, str):
            if "," in image_input:
                image_input = image_input.split(",", 1)[1]
            try:
                image_input = base64.b64decode(image_input)
            except Exception:
                image_input = image_input.encode()
        pil_img = Image.open(io.BytesIO(image_input))
    else:
        pil_img = image_input

    if pil_img.mode != "RGB":
        pil_img = pil_img.convert("RGB")

    # ── Step 1: Tesseract bounding boxes ──
    data = pytesseract.image_to_data(
        pil_img, config="--psm 6", output_type=pytesseract.Output.DICT
    )

    low_conf_regions = []
    for i in range(len(data["text"])):
        conf = int(data["conf"][i])
        text = data["text"][i].strip()
        if conf < confidence_threshold and text:
            x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
            if w > 10 and h > 10:
                low_conf_regions.append((x, y, w, h))

    # ── Step 2: TrOCR on low-confidence regions ──
    region_texts = []
    if low_conf_regions:
        logger.info("Running TrOCR on %d low-confidence regions …", len(low_conf_regions))
        region_texts = _run_trocr_on_regions(pil_img, low_conf_regions)

    # ── Step 3: Full-image fallback TrOCR scan ──
    # Resize to a reasonable height for TrOCR (it expects ~384px height)
    full_text_fallback = ""
    try:
        resized = pil_img.copy()
        resized.thumbnail((800, 384), Image.Resampling.LANCZOS)
        full_text_fallback = _run_trocr_on_image(resized)
    except Exception as e:
        logger.debug("Full-image TrOCR fallback failed: %s", e)

    # Combine results, deduplicate
    combined = []
    for t in region_texts:
        if t and t not in combined:
            combined.append(t)
    if full_text_fallback and full_text_fallback not in combined:
        combined.append(full_text_fallback)

    return {
        "full_text": "\n".join(combined),
        "regions": combined,
        "low_confidence_regions_count": len(low_conf_regions),
        "error": None,
    }


def extract_all(image_input) -> Dict:
    """
    Master hybrid extraction function.
    Returns a structured dict with both printed and handwritten text,
    ready to be injected into a VLM prompt.
    """
    logger.info("Starting hybrid OCR extraction (Tesseract + TrOCR) …")

    printed = extract_printed_text(image_input)
    handwritten = extract_handwritten_text(image_input)

    result = {
        "printed_text": printed.get("full_text", ""),
        "printed_lines": printed.get("lines", []),
        "printed_confidence": printed.get("confidence_avg", 0.0),
        "handwritten_text": handwritten.get("full_text", ""),
        "handwritten_regions": handwritten.get("regions", []),
        "combined_text": f"{printed.get('full_text', '')}\n{handwritten.get('full_text', '')}".strip(),
    }

    logger.info(
        "OCR complete — printed words: %d (conf %.1f%%), handwriting regions: %d",
        printed.get("word_count", 0),
        printed.get("confidence_avg", 0.0),
        handwritten.get("low_confidence_regions_count", 0),
    )
    return result

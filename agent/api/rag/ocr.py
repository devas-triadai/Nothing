"""
AGRA Phase 2 — RAG: Document Text Extraction + OCR
- Digital PDFs: PyMuPDF (fitz) for fast native text extraction.
- Scanned PDFs / images: PaddleOCR fallback.
- Auto-detects scanned pages (image-only) vs digital text.
- DOCX / TXT: direct text extraction.
"""

import io
import logging
import re
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger("agra.ocr")

# Lazy-loaded PaddleOCR instance
_paddle_ocr = None


def _get_paddle_ocr():
    """
    Lazy-load PaddleOCR with forward-compatible argument handling.

    PaddleOCR v3+ removed several legacy arguments (show_log, use_gpu).
    We try the minimal compatible API and fall back if needed.
    """
    global _paddle_ocr
    if _paddle_ocr is None:
        import os
        # Disable oneDNN to prevent PIR runtime crash (ERR_HTTP2_PROTOCOL_ERROR)
        os.environ["FLAGS_use_mkldnn"] = "0"
        from paddleocr import PaddleOCR
        try:
            # Try passing legacy kwargs for older versions
            _paddle_ocr = PaddleOCR(use_angle_cls=True, use_gpu=False, enable_mkldnn=False, lang="en")
        except Exception as e:
            logger.warning("PaddleOCR init with legacy args failed (%s), retrying with v3 minimal API.", e)
            try:
                # PaddleOCR v3+ minimal API (use_gpu/enable_mkldnn are removed)
                _paddle_ocr = PaddleOCR(use_angle_cls=True, lang="en")
            except Exception as e2:
                logger.error("PaddleOCR could not be initialised: %s", e2)
                raise
        logger.info("PaddleOCR engine initialised.")
    return _paddle_ocr


def _ocr_image_bytes(image_bytes: bytes) -> str:
    """Run PaddleOCR on raw image bytes, return extracted text."""
    import numpy as np
    from PIL import Image

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img_array = np.array(img)
    ocr = _get_paddle_ocr()
    try:
        results = ocr.ocr(img_array)
    except Exception as e:
        logger.error("PaddleOCR failed to process image (likely PIR attribute error): %s", e)
        return ""
        
    if not results or not results[0]:
        return ""
    lines = []
    for line in results[0]:
        if line and len(line) >= 2:
            text = line[1][0] if isinstance(line[1], (list, tuple)) else str(line[1])
            lines.append(text)
    return "\n".join(lines)


def _is_scanned_page(page) -> bool:
    """Detect whether a PyMuPDF page is scanned (image-only, no selectable text)."""
    text = page.get_text("text").strip()
    # If the page has very little text but has images, it's likely scanned
    if len(text) < 20:
        images = page.get_images(full=True)
        if images:
            return True
    return False


def extract_pdf(file_path: str) -> List[Dict[str, Any]]:
    """
    Extract text from a PDF file, page by page.
    Uses PyMuPDF for digital text; falls back to PaddleOCR for scanned pages.

    Returns: [{"page": int, "text": str}, ...]
    """
    import fitz  # PyMuPDF

    doc = fitz.open(file_path)
    pages: List[Dict[str, Any]] = []

    for page_num in range(len(doc)):
        page = doc[page_num]

        if _is_scanned_page(page):
            # Scanned page → render to image → OCR
            logger.debug("Page %d is scanned — using OCR.", page_num + 1)
            pix = page.get_pixmap(dpi=300)
            img_bytes = pix.tobytes("png")
            text = _ocr_image_bytes(img_bytes)
        else:
            text = page.get_text("text")

        text = text.strip()
        if text:
            pages.append({"page": page_num + 1, "text": text})

    doc.close()
    logger.info("PDF %s: extracted %d pages.", Path(file_path).name, len(pages))
    return pages


def extract_docx(file_path: str) -> List[Dict[str, Any]]:
    """Extract text from a DOCX file. Returns as a single-page document."""
    import docx2txt
    text = docx2txt.process(file_path)
    if not text or not text.strip():
        return []

    # Split into pseudo-pages of ~3000 chars for manageability
    chunks = []
    lines = text.split("\n")
    current_page: List[str] = []
    current_len = 0
    page_num = 1

    for line in lines:
        current_page.append(line)
        current_len += len(line)
        if current_len >= 3000:
            chunks.append({"page": page_num, "text": "\n".join(current_page)})
            current_page = []
            current_len = 0
            page_num += 1

    if current_page:
        chunks.append({"page": page_num, "text": "\n".join(current_page)})

    logger.info("DOCX %s: extracted %d pages.", Path(file_path).name, len(chunks))
    return chunks


def extract_txt(file_path: str) -> List[Dict[str, Any]]:
    """Extract text from a plain text file."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except Exception:
        with open(file_path, "r", encoding="latin-1") as f:
            text = f.read()

    if not text.strip():
        return []

    logger.info("TXT %s: %d characters.", Path(file_path).name, len(text))
    return [{"page": 1, "text": text}]


def extract_image(file_path: str) -> List[Dict[str, Any]]:
    """OCR a standalone image file (JPEG, PNG)."""
    with open(file_path, "rb") as f:
        img_bytes = f.read()
    text = _ocr_image_bytes(img_bytes)
    if not text.strip():
        return []
    logger.info("Image %s: OCR extracted %d characters.", Path(file_path).name, len(text))
    return [{"page": 1, "text": text}]


def extract_document(file_path: str) -> List[Dict[str, Any]]:
    """
    Auto-detect file type and extract text.
    Returns: [{"page": int, "text": str}, ...]
    """
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return extract_pdf(file_path)
    elif suffix in (".docx", ".doc"):
        return extract_docx(file_path)
    elif suffix == ".txt":
        return extract_txt(file_path)
    elif suffix in (".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif"):
        return extract_image(file_path)
    else:
        logger.warning("Unsupported file type: %s", suffix)
        return []

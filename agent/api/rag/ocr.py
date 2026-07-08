"""
AGRA Phase 2 — RAG: Document Text Extraction + OCR
- Digital PDFs: PyMuPDF (fitz) for fast native text extraction.
- Scanned PDFs / images: PaddleOCR → EasyOCR fallback.
- Auto-detects scanned pages (image-only) vs digital text.
- DOCX / TXT: direct text extraction.
- Last resort: tries pypdf for PDFs where PyMuPDF returns no text.
"""

import io
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("agra.ocr")

# Lazy-loaded OCR engines
_paddle_ocr = None
_easy_ocr = None


def _get_paddle_ocr():
    """
    Lazy-load PaddleOCR with forward-compatible argument handling.
    Returns None if PaddleOCR is not available or fails to init.
    """
    global _paddle_ocr
    if _paddle_ocr is not None:
        return _paddle_ocr
    # Disable oneDNN and PIR to prevent runtime crash
    os.environ.setdefault("FLAGS_use_mkldnn", "0")
    os.environ.setdefault("FLAGS_enable_pir_api", "0")
    try:
        from paddleocr import PaddleOCR
        try:
            _paddle_ocr = PaddleOCR(use_angle_cls=True, use_gpu=False, enable_mkldnn=False, lang="en")
        except Exception:
            # PaddleOCR v3+ minimal API (use_gpu/enable_mkldnn removed)
            _paddle_ocr = PaddleOCR(use_angle_cls=True, lang="en")
        logger.info("PaddleOCR engine initialised.")
    except ImportError:
        logger.warning("PaddleOCR not installed.")
        _paddle_ocr = False
    except Exception as e:
        logger.warning("PaddleOCR could not be initialised: %s", e)
        _paddle_ocr = False
    return _paddle_ocr if _paddle_ocr is not False else None


def _get_easy_ocr():
    """
    Lazy-load EasyOCR as a fallback OCR engine.
    Returns None if EasyOCR is not available.
    """
    global _easy_ocr
    if _easy_ocr is not None:
        return _easy_ocr
    try:
        import easyocr
        try:
            _easy_ocr = easyocr.Reader(["en"], gpu=False)
            logger.info("EasyOCR engine initialised (CPU mode).")
        except Exception:
            _easy_ocr = easyocr.Reader(["en"])
            logger.info("EasyOCR engine initialised.")
    except ImportError:
        logger.warning("EasyOCR not installed.")
        _easy_ocr = False
    except Exception as e:
        logger.warning("EasyOCR could not be initialised: %s", e)
        _easy_ocr = False
    return _easy_ocr if _easy_ocr is not False else None


def _ocr_image_bytes_paddle(image_bytes: bytes) -> Optional[str]:
    """Run PaddleOCR on raw image bytes, return text or None on failure."""
    import numpy as np
    from PIL import Image
    ocr = _get_paddle_ocr()
    if ocr is None:
        return None
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img_array = np.array(img)
        results = ocr.ocr(img_array)
    except Exception as e:
        logger.debug("PaddleOCR runtime failure: %s", e)
        return None
    if not results or not results[0]:
        return None
    lines = []
    for line in results[0]:
        if line and len(line) >= 2:
            val = line[1]
            if isinstance(val, (list, tuple)) and len(val) >= 2:
                lines.append(str(val[0]))
            else:
                lines.append(str(val))
    return "\n".join(lines) if lines else None


def _ocr_image_bytes_easy(image_bytes: bytes) -> Optional[str]:
    """Run EasyOCR on raw image bytes, return text or None on failure."""
    import numpy as np
    from PIL import Image
    ocr = _get_easy_ocr()
    if ocr is None:
        return None
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img_array = np.array(img)
        results = ocr.readtext(img_array)
    except Exception as e:
        logger.debug("EasyOCR runtime failure: %s", e)
        return None
    if not results:
        return None
    lines = [str(r[1]) for r in results if r and len(r) >= 2 and r[1]]
    return "\n".join(lines) if lines else None


def _ocr_image_bytes_tesseract(image_bytes: bytes) -> Optional[str]:
    """Run pytesseract on image bytes, return text or None on failure."""
    try:
        from PIL import Image
        import pytesseract
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        text = pytesseract.image_to_string(img).strip()
        return text if text else None
    except ImportError:
        return None
    except Exception as e:
        logger.debug("pytesseract failure: %s", e)
        return None


def _ocr_image_bytes_fallback(image_bytes: bytes) -> Tuple[str, float]:
    """
    Run OCR on image bytes trying multiple engines (PaddleOCR → EasyOCR → Tesseract).
    Returns (text, avg_confidence).
    """
    text = _ocr_image_bytes_paddle(image_bytes)
    if text:
        return text, 0.85
    logger.debug("PaddleOCR returned no text, trying EasyOCR fallback.")
    text = _ocr_image_bytes_easy(image_bytes)
    if text:
        return text, 0.80
    logger.debug("EasyOCR returned no text, trying Tesseract fallback.")
    text = _ocr_image_bytes_tesseract(image_bytes)
    if text:
        return text, 0.75
    logger.warning("All OCR engines failed for image.")
    return "", 0.0


def _get_text_from_page(page) -> str:
    """
    Extract text from a PyMuPDF page using multiple methods.
    First tries 'text' mode, then 'rawdict' for non-standard encodings.
    """
    text = page.get_text("text").strip()
    if len(text) >= 20:
        return text
    # rawdict extracts all text objects including those with custom fonts
    blocks = page.get_text("rawdict").get("blocks", [])
    raw_lines = []
    for blk in blocks:
        if blk.get("type") == 0:  # text block
            for line in blk.get("lines", []):
                for span in line.get("spans", []):
                    t = (span.get("text") or "").strip()
                    if t:
                        raw_lines.append(t)
    raw_text = "\n".join(raw_lines).strip()
    if len(raw_text) > len(text):
        return raw_text
    return text


def _is_scanned_page(page) -> bool:
    """
    Detect whether a PyMuPDF page is scanned (image-only, no selectable text).
    Only considers pages with ZERO extractable text as scanned.
    When text < 20 but > 0, uses it directly instead of forcing OCR.
    """
    text = page.get_text("text").strip()
    if len(text) == 0:
        # Also check rawdict
        blocks = page.get_text("rawdict").get("blocks", [])
        has_any_text = any(
            blk.get("type") == 0
            for blk in blocks
        )
        if not has_any_text:
            images = page.get_images(full=True)
            if images:
                return True
    return False


def _try_pypdf_fallback(file_path: str) -> Optional[List[Dict[str, Any]]]:
    """
    Try extracting text using pypdf (pure Python) when PyMuPDF fails.
    Returns None if pypdf is not available.
    """
    try:
        import pypdf
        reader = pypdf.PdfReader(file_path)
        pages = []
        for i, pdf_page in enumerate(reader.pages, start=1):
            text = (pdf_page.extract_text() or "").strip()
            if text:
                pages.append({"page": i, "text": text, "ocr_confidence": 1.0})
        if pages:
            logger.info("pypdf fallback: extracted %d pages from %s.", len(pages), Path(file_path).name)
            return pages
    except ImportError:
        pass
    except Exception as e:
        logger.debug("pypdf fallback failed: %s", e)
    return None


def extract_pdf(file_path: str) -> List[Dict[str, Any]]:
    """
    Extract text from a PDF file, page by page.
    Uses PyMuPDF for digital text; falls back to OCR for scanned pages.
    Last resort tries pypdf if PyMuPDF returns no pages at all.

    Returns: [{"page": int, "text": str}, ...]
    """
    import fitz  # PyMuPDF

    doc = fitz.open(file_path)
    pages: List[Dict[str, Any]] = []

    for page_num in range(len(doc)):
        page = doc[page_num]

        if _is_scanned_page(page):
            logger.debug("Page %d is scanned — using OCR.", page_num + 1)
            pix = page.get_pixmap(dpi=300)
            img_bytes = pix.tobytes("png")
            text, conf = _ocr_image_bytes_fallback(img_bytes)
        else:
            text = _get_text_from_page(page)
            conf = 1.0

        text = text.strip()
        if text:
            pages.append({"page": page_num + 1, "text": text, "ocr_confidence": conf})
        else:
            logger.info("Page %d yielded no text; skipping.", page_num + 1)

    doc.close()

    # If PyMuPDF got zero pages, try pypdf as a pure-Python fallback
    if not pages:
        logger.info("PyMuPDF extracted no text from %s, trying pypdf fallback.", Path(file_path).name)
        pypdf_result = _try_pypdf_fallback(file_path)
        if pypdf_result:
            return pypdf_result

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
            chunks.append({"page": page_num, "text": "\n".join(current_page), "ocr_confidence": 1.0})
            current_page = []
            current_len = 0
            page_num += 1

    if current_page:
        chunks.append({"page": page_num, "text": "\n".join(current_page), "ocr_confidence": 1.0})

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
    return [{"page": 1, "text": text, "ocr_confidence": 1.0}]


def extract_image(file_path: str) -> List[Dict[str, Any]]:
    """OCR a standalone image file (JPEG, PNG)."""
    with open(file_path, "rb") as f:
        img_bytes = f.read()
    text, conf = _ocr_image_bytes(img_bytes)
    if not text.strip():
        return []
    logger.info("Image %s: OCR extracted %d characters.", Path(file_path).name, len(text))
    return [{"page": 1, "text": text, "ocr_confidence": conf}]


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

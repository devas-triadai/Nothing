"""
AGRA — Document Image Extractor (Phase 4)
Extracts images and diagrams from uploaded PDF and DOCX documents.
Images can be described via VLM and injected into RAG context.
"""
import base64
import io
import logging
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("agra.image_extractor")

# VLM prompt for describing embedded document images (diagrams, charts, drawings)
_IMAGE_DESCRIPTION_PROMPT = """You are an AI assistant analyzing an image embedded in a document.
Describe this image in detail. Focus on:
1. What type of image it is (diagram, chart, photograph, table, engineering drawing, map, etc.)
2. All visible text, labels, numbers, and annotations
3. Relationships between elements (arrows, connections, hierarchies)
4. Colors, shapes, and spatial layout
5. Any data or measurements shown
6. The overall purpose or message of this image

Be thorough and specific. Write in complete sentences."""


def _get_output_dir() -> Path:
    """Get the extracted images output directory."""
    import os
    data_dir = Path(os.environ.get("AGRA_DATA_DIR", "/workspace/agra_data"))
    if not data_dir.exists():
        data_dir = Path(__file__).resolve().parent.parent.parent / "agra_data"
    img_dir = data_dir / "outputs" / "extracted_images"
    img_dir.mkdir(parents=True, exist_ok=True)
    return img_dir


def extract_images_from_pdf(
    pdf_path: str,
    min_width: int = 100,
    min_height: int = 100,
    max_images: int = 10,
) -> List[Dict[str, Any]]:
    """
    Extract images from a PDF file.

    Args:
        pdf_path: Path to the PDF file.
        min_width: Minimum image width to include (filters out tiny icons).
        min_height: Minimum image height to include.
        max_images: Maximum number of images to extract.

    Returns:
        List of dicts: [{"path": str, "page": int, "width": int, "height": int}, ...]
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        try:
            import pymupdf as fitz
        except ImportError:
            logger.warning("PyMuPDF not available — cannot extract images from PDFs.")
            return []

    results = []
    output_dir = _get_output_dir()

    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        logger.error("Cannot open PDF %s: %s", pdf_path, e)
        return []

    for page_num in range(len(doc)):
        if len(results) >= max_images:
            break

        page = doc[page_num]
        image_list = page.get_images(full=True)

        for img_index, img_info in enumerate(image_list):
            if len(results) >= max_images:
                break

            xref = img_info[0]
            try:
                base_image = doc.extract_image(xref)
                if not base_image:
                    continue

                width = base_image.get("width", 0)
                height = base_image.get("height", 0)

                # Filter out tiny images (icons, bullets, etc.)
                if width < min_width or height < min_height:
                    continue

                # Save image
                ext = base_image.get("ext", "png")
                img_filename = f"extracted_{uuid.uuid4().hex[:8]}.{ext}"
                img_path = output_dir / img_filename

                with open(img_path, "wb") as f:
                    f.write(base_image["image"])

                results.append({
                    "path": str(img_path),
                    "page": page_num + 1,
                    "width": width,
                    "height": height,
                    "size_bytes": len(base_image["image"]),
                })

                logger.debug(
                    "Extracted image from page %d: %dx%d (%s)",
                    page_num + 1, width, height, img_filename,
                )

            except Exception as e:
                logger.debug("Failed to extract image xref=%d: %s", xref, e)
                continue

    doc.close()
    logger.info("Extracted %d images from %s", len(results), pdf_path)
    return results


def extract_images_from_doc(doc_id: str) -> List[Dict[str, Any]]:
    """
    Extract images from an uploaded document by its doc_id.
    Looks up the file path from the uploads directory.

    Args:
        doc_id: The document ID used during ingestion.

    Returns:
        List of extracted image info dicts.
    """
    import os
    data_dir = Path(os.environ.get("AGRA_DATA_DIR", "/workspace/agra_data"))
    if not data_dir.exists():
        data_dir = Path(__file__).resolve().parent.parent.parent / "agra_data"
    uploads_dir = data_dir / "uploads"

    if not uploads_dir.exists():
        logger.warning("Uploads directory not found: %s", uploads_dir)
        return []

    # Find the file matching this doc_id
    matching_files = list(uploads_dir.glob(f"{doc_id}_*"))
    if not matching_files:
        # Also try without prefix
        matching_files = list(uploads_dir.glob(f"*{doc_id}*"))

    for file_path in matching_files:
        if file_path.suffix.lower() == ".pdf":
            return extract_images_from_pdf(str(file_path))

    logger.info("No PDF found for doc_id=%s — no images to extract.", doc_id)
    return []


def get_best_images_for_topic(
    doc_ids: List[str],
    max_total: int = 5,
) -> List[Dict[str, Any]]:
    """
    Extract the best images from multiple documents for PPT insertion.

    Strategy:
    - Extract from all provided doc_ids
    - Sort by image size (larger images are usually more important diagrams)
    - Return top N

    Args:
        doc_ids: List of document IDs to search.
        max_total: Maximum number of images to return.

    Returns:
        List of image info dicts, sorted by relevance (size).
    """
    all_images = []
    for doc_id in doc_ids:
        images = extract_images_from_doc(doc_id)
        all_images.extend(images)

    # Sort by pixel area (larger = more likely a diagram/chart)
    all_images.sort(key=lambda x: x.get("width", 0) * x.get("height", 0), reverse=True)

    return all_images[:max_total]


def _image_bytes_to_data_uri(image_bytes: bytes, ext: str = "png") -> str:
    """Convert raw image bytes to a base64 data URI for VLM input."""
    mime_map = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                 "gif": "image/gif", "webp": "image/webp", "bmp": "image/bmp"}
    mime = mime_map.get(ext.lower(), "image/png")
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:{mime};base64,{b64}"


def _extract_images_from_docx(file_path: str) -> List[Dict[str, Any]]:
    """
    Extract embedded images from a DOCX file.
    Returns list of dicts with {path, page, width, height, size_bytes, image_bytes}.
    Page is approximate (paragraph index-based grouping).
    """
    results = []
    try:
        from docx import Document
        from docx.opc.constants import RELATIONSHIP_TYPE as RT
        import zipfile
    except ImportError:
        logger.warning("python-docx not available — cannot extract images from DOCX.")
        return []

    output_dir = _get_output_dir()
    try:
        doc = Document(file_path)
    except Exception as e:
        logger.error("Cannot open DOCX %s: %s", file_path, e)
        return []

    # Map relationship IDs to image blobs by reading the zip directly
    image_map = {}
    try:
        with zipfile.ZipFile(file_path) as z:
            for name in z.namelist():
                if name.startswith("word/media/") and not name.endswith("/"):
                    image_map[name] = z.read(name)
    except Exception as e:
        logger.warning("Failed to read DOCX zip for images: %s", e)
        return results

    if not image_map:
        return results

    # Group images roughly by paragraphs (every ~50 paragraphs = ~1 page)
    para_count = len(doc.paragraphs)
    images_per_page = max(1, len(image_map) // max(1, para_count // 50))
    page = 1
    for i, (img_rel_path, img_bytes) in enumerate(image_map.items()):
        ext = Path(img_rel_path).suffix.lstrip(".") or "png"
        if not ext:
            ext = "png"
        img_filename = f"docx_img_{uuid.uuid4().hex[:8]}.{ext}"
        img_path = output_dir / img_filename
        try:
            with open(img_path, "wb") as f:
                f.write(img_bytes)
            results.append({
                "path": str(img_path),
                "page": page,
                "width": 0,
                "height": 0,
                "size_bytes": len(img_bytes),
                "image_bytes": img_bytes,
                "ext": ext,
            })
        except Exception as e:
            logger.debug("Failed to save DOCX image %s: %s", img_rel_path, e)
        if (i + 1) % images_per_page == 0:
            page += 1

    doc.close()
    logger.info("Extracted %d images from DOCX %s", len(results), file_path)
    return results


def describe_image_with_vlm(
    image_bytes: bytes,
    ext: str = "png",
    max_retries: int = 2,
) -> Optional[str]:
    """
    Send an image to the VLM and return a text description.
    Uses the existing llm_engine.generate() with a multimodal message.
    Returns None if description fails.
    """
    data_uri = _image_bytes_to_data_uri(image_bytes, ext)
    messages = [
        {"role": "system", "content": "You extract detailed text descriptions of images, diagrams, and drawings embedded in documents."},
        {"role": "user", "content": [
            {"type": "text", "text": _IMAGE_DESCRIPTION_PROMPT},
            {"type": "image_url", "image_url": {"url": data_uri}},
        ]},
    ]
    for attempt in range(max_retries):
        try:
            from api.rag import llm as llm_engine
            raw = llm_engine.generate(messages, max_tokens=512, temperature=0.1, raw=True)
            if raw and raw.strip():
                return raw.strip()
        except Exception as e:
            logger.warning("VLM image description attempt %d/%d failed: %s", attempt + 1, max_retries, e)
    return None


def extract_and_describe_images(
    file_path: str,
    pages: List[Dict[str, Any]],
    filename: str,
) -> Dict[int, str]:
    """
    Extract embedded images from a document and describe them via VLM.
    
    Args:
        file_path: Path to the uploaded document file.
        pages: List of page dicts from OCR extraction (for page numbering reference).
        filename: Original filename for logging.
    
    Returns:
        Dict mapping page numbers (1-based) to concatenated image descriptions for that page.
    """
    suffix = Path(file_path).suffix.lower()
    images = []
    if suffix == ".pdf":
        images = extract_images_from_pdf(file_path, min_width=80, min_height=80, max_images=20)
        # Read actual image bytes from saved paths
        for img in images:
            try:
                with open(img["path"], "rb") as f:
                    img["image_bytes"] = f.read()
                img["ext"] = Path(img["path"]).suffix.lstrip(".") or "png"
            except Exception:
                img["image_bytes"] = b""
                img["ext"] = "png"
    elif suffix in (".docx", ".doc"):
        images = _extract_images_from_docx(file_path)
    else:
        return {}

    if not images:
        logger.info("No embedded images found in %s", filename)
        return {}

    logger.info("Found %d embedded images in %s — describing via VLM…", len(images), filename)
    # Safety limits: max 15 images total, max 2MB per image
    MAX_IMAGES = 15
    MAX_IMAGE_BYTES = 2 * 1024 * 1024
    images = images[:MAX_IMAGES]
    page_descriptions: Dict[int, List[str]] = {}
    for img in images:
        page_num = img.get("page", 1)
        img_bytes = img.get("image_bytes", b"")
        img_ext = img.get("ext", "png")
        if not img_bytes:
            continue
        if len(img_bytes) > MAX_IMAGE_BYTES:
            logger.debug("Page %d image: skipping (%d bytes exceeds limit)", page_num, len(img_bytes))
            continue
        description = describe_image_with_vlm(img_bytes, img_ext)
        if description:
            page_descriptions.setdefault(page_num, []).append(description)
            logger.debug("Page %d image: %s", page_num, description[:100])
        else:
            logger.debug("Page %d image: description failed", page_num)

    result = {}
    for page_num, descs in page_descriptions.items():
        result[page_num] = "[EMBEDDED IMAGE]\n" + "\n\n".join(descs)

    logger.info("Described %d pages with embedded images in %s", len(result), filename)
    return result

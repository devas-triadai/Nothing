"""
AGRA — Document Image Extractor (Phase 4)
Extracts images and diagrams from uploaded PDF documents using PyMuPDF (fitz).
Retrieved images can be inserted into generated PowerPoint slides.
"""

import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("agra.image_extractor")


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

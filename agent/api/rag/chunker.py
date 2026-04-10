"""
AGRA Phase 2 — RAG: Text Chunker
Splits document text into overlapping chunks of ~512 tokens,
respecting paragraph boundaries where possible.
Uses tiktoken cl100k_base for accurate token counting.
"""

import logging
from typing import Dict, List, Any

import tiktoken

logger = logging.getLogger("agra.chunker")

_ENCODING = tiktoken.get_encoding("cl100k_base")
_MAX_TOKENS = 512
_OVERLAP_TOKENS = 64


def _token_len(text: str) -> int:
    """Count tokens in a string using cl100k_base."""
    return len(_ENCODING.encode(text, disallowed_special=()))


def _split_paragraph_if_needed(paragraph: str) -> List[str]:
    """
    If a single paragraph exceeds _MAX_TOKENS, split it on sentence
    boundaries. Fallback: split at hard token limit.
    """
    if _token_len(paragraph) <= _MAX_TOKENS:
        return [paragraph]

    # Try sentence splitting first
    import re
    sentences = re.split(r'(?<=[.!?])\s+', paragraph)
    if len(sentences) <= 1:
        # No sentence boundaries — force-split by token count
        tokens = _ENCODING.encode(paragraph, disallowed_special=())
        parts = []
        for i in range(0, len(tokens), _MAX_TOKENS - _OVERLAP_TOKENS):
            chunk_tokens = tokens[i:i + _MAX_TOKENS]
            parts.append(_ENCODING.decode(chunk_tokens))
        return parts

    # Greedily group sentences up to _MAX_TOKENS
    groups: List[str] = []
    current: List[str] = []
    current_len = 0
    for sent in sentences:
        sent_len = _token_len(sent)
        if current_len + sent_len > _MAX_TOKENS and current:
            groups.append(" ".join(current))
            # Keep overlap from end of current group
            overlap_text = " ".join(current)
            overlap_tokens = _ENCODING.encode(overlap_text, disallowed_special=())
            if len(overlap_tokens) > _OVERLAP_TOKENS:
                overlap_decoded = _ENCODING.decode(overlap_tokens[-_OVERLAP_TOKENS:])
                current = [overlap_decoded]
                current_len = _OVERLAP_TOKENS
            else:
                current = []
                current_len = 0
        current.append(sent)
        current_len += sent_len
    if current:
        groups.append(" ".join(current))
    return groups


def chunk_text(
    text: str,
    doc_id: str,
    filename: str,
    page_number: int = 1,
) -> List[Dict[str, Any]]:
    """
    Chunk a block of text into segments of ~512 tokens with 64-token overlap.

    Args:
        text:        Raw text content.
        doc_id:      Unique document identifier.
        filename:    Original filename.
        page_number: Source page number (1-based).

    Returns:
        List of chunk dicts:
        [{"text": str, "metadata": {"doc_id", "filename", "page", "chunk_index"}}]
    """
    if not text or not text.strip():
        return []

    # Split into paragraphs (double newline or single newline with indent)
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [p.strip() for p in text.split("\n") if p.strip()]

    # Expand long paragraphs
    segments: List[str] = []
    for para in paragraphs:
        segments.extend(_split_paragraph_if_needed(para))

    # Merge small segments into chunks respecting _MAX_TOKENS
    chunks: List[Dict[str, Any]] = []
    current_parts: List[str] = []
    current_len = 0
    chunk_index = 0

    def _flush():
        nonlocal chunk_index
        if not current_parts:
            return
        chunk_text_joined = "\n\n".join(current_parts).strip()
        if chunk_text_joined:
            chunks.append({
                "text": chunk_text_joined,
                "metadata": {
                    "doc_id": doc_id,
                    "filename": filename,
                    "page": page_number,
                    "chunk_index": chunk_index,
                },
            })
            chunk_index += 1

    for seg in segments:
        seg_len = _token_len(seg)
        if current_len + seg_len > _MAX_TOKENS and current_parts:
            _flush()
            # Overlap: keep tail tokens from previous chunk
            prev_text = "\n\n".join(current_parts)
            prev_tokens = _ENCODING.encode(prev_text, disallowed_special=())
            if len(prev_tokens) > _OVERLAP_TOKENS:
                overlap = _ENCODING.decode(prev_tokens[-_OVERLAP_TOKENS:])
                current_parts = [overlap]
                current_len = _OVERLAP_TOKENS
            else:
                current_parts = []
                current_len = 0
        current_parts.append(seg)
        current_len += seg_len

    _flush()

    logger.debug(
        "Chunked %s page %d → %d chunks (doc_id=%s)",
        filename, page_number, len(chunks), doc_id,
    )
    return chunks


def chunk_pages(
    pages: List[Dict[str, Any]],
    doc_id: str,
    filename: str,
) -> List[Dict[str, Any]]:
    """
    Chunk multiple pages at once.

    Args:
        pages:    List of {"page": int, "text": str} from OCR/extractor.
        doc_id:   Unique document identifier.
        filename: Original filename.

    Returns:
        Flat list of chunk dicts across all pages, with sequential chunk_index.
    """
    all_chunks: List[Dict[str, Any]] = []
    global_index = 0

    for page_data in pages:
        page_num = page_data.get("page", 1)
        page_text = page_data.get("text", "")
        page_chunks = chunk_text(page_text, doc_id, filename, page_num)

        # Re-index globally
        for chunk in page_chunks:
            chunk["metadata"]["chunk_index"] = global_index
            global_index += 1
            all_chunks.append(chunk)

    logger.info(
        "Total chunks for %s: %d across %d pages",
        filename, len(all_chunks), len(pages),
    )
    return all_chunks

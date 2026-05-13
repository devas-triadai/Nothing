"""
AGRA Phase 2 — RAG: LLM Engine (Gemma 4 31B-IT via llama-server)
Lightweight HTTP client that forwards all inference requests to the
native llama.cpp server (llama-server).  The C++ server handles
continuous batching (--parallel N) for true concurrent inference.

Vision (VLM) is fully supported — llama-server accepts multimodal
messages with image_url when launched with --mmproj.
"""

import json
import logging
import os
from typing import Generator, List, Dict, Any, Optional

import requests  # stdlib-compatible HTTP — no async needed
import httpx

logger = logging.getLogger("agra.llm")

# ── llama-server connection ──
_LLAMA_SERVER_URL = os.getenv("LLAMA_SERVER_URL", "http://localhost:8080")
_CHAT_ENDPOINT = f"{_LLAMA_SERVER_URL}/v1/chat/completions"

_MAX_TOKENS_DEFAULT = 2048


def _wait_for_server(timeout: int = 300) -> bool:
    """Block until llama-server is ready (called once at startup)."""
    import time
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"{_LLAMA_SERVER_URL}/health", timeout=5)
            if r.status_code == 200:
                data = r.json()
                status = data.get("status", "")
                if status == "ok" or status == "no slot available":
                    logger.info("llama-server is ready at %s", _LLAMA_SERVER_URL)
                    return True
        except Exception:
            pass
        logger.info("Waiting for llama-server at %s …", _LLAMA_SERVER_URL)
        time.sleep(5)
    logger.error("llama-server did not become ready within %ds!", timeout)
    return False


def load_llm() -> None:
    """Wait for the external llama-server to be ready (call at startup)."""
    _wait_for_server()


def generate(
    messages: List[Dict[str, Any]],
    max_tokens: int = _MAX_TOKENS_DEFAULT,
    temperature: float = 0.3,
    top_p: float = 0.9,
    stop: Optional[List[str]] = None,
    **kwargs,
) -> str:
    """
    Blocking generation — sends chat messages, returns full response string.
    No lock needed; llama-server handles concurrency internally.
    """
    payload = {
        "model": "local-model",
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": top_p,
        "stream": False,
    }
    if stop:
        payload["stop"] = stop

    logger.debug("generate() → POST %s (max_tokens=%d)", _CHAT_ENDPOINT, max_tokens)
    resp = requests.post(_CHAT_ENDPOINT, json=payload, timeout=300)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


def stream_generate(
    messages: List[Dict[str, Any]],
    max_tokens: int = _MAX_TOKENS_DEFAULT,
    temperature: float = 0.3,
    top_p: float = 0.9,
    stop: Optional[List[str]] = None,
    **kwargs,
) -> Generator[str, None, None]:
    """
    Streaming generation — yields tokens one by one.
    No lock needed; llama-server handles concurrency internally.
    """
    payload = {
        "model": "local-model",
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": top_p,
        "stream": True,
    }
    if stop:
        payload["stop"] = stop

    logger.debug("stream_generate() → POST %s (max_tokens=%d, stream=True)", _CHAT_ENDPOINT, max_tokens)
    resp = requests.post(_CHAT_ENDPOINT, json=payload, stream=True, timeout=300)
    resp.raise_for_status()

    for line in resp.iter_lines(decode_unicode=True):
        if not line:
            continue
        if line.startswith("data: "):
            data_str = line[6:].strip()
            if data_str == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                token = delta.get("content", "")
                if token:
                    yield token
            except json.JSONDecodeError:
                logger.warning("Failed to parse SSE chunk: %s", data_str)

async def generate_hyde_document(query: str) -> str:
    """
    Generate a hypothetical answer/document for the given query using the LLM.
    This text will be embedded and used for vector search.
    """
    system_prompt = "You are an expert maritime and Coast Guard technical writer."
    prompt = (
        "Please write a short, precise paragraph that answers the following question or addresses the topic. "
        "Write it as if it were an official technical document or regulation. Do not use conversational filler, "
        "just output the raw factual or technical content that would perfectly answer the query.\n\n"
        f"Topic/Question: {query}"
    )

    try:
        # Non-streaming call for HyDE
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{_LLAMA_SERVER_URL}/v1/chat/completions",
                json={
                    "model": "local-model",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.4,  # Increased slightly to avoid deterministic empty outputs
                    "max_tokens": 150,
                    "stream": False
                }
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"].get("content", "").strip()
            
            if not content:
                logger.warning("LLM returned empty content for HyDE. Raw response: %s", data)
                return query
                
            return content
    except Exception as e:
        logger.warning("HyDE generation failed, falling back to raw query. Error: %s", e)
        return query

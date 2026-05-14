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
import re
from typing import Generator, List, Dict, Any, Optional

import requests  # stdlib-compatible HTTP — no async needed
import httpx

logger = logging.getLogger("agra.llm")

# ── llama-server connection ──
_LLAMA_SERVER_URL = os.getenv("LLAMA_SERVER_URL", "http://localhost:8080")
_CHAT_ENDPOINT = f"{_LLAMA_SERVER_URL}/v1/chat/completions"

_MAX_TOKENS_DEFAULT = 2048


# ─────────────────────────────────────────────────────────────────────
#  Text sanitization — mojibake (UTF-8 misinterpreted as cp1252) and
#  LaTeX → Unicode. Applied to all LLM output before the user sees it.
# ─────────────────────────────────────────────────────────────────────

# Common UTF-8 → cp1252 mojibake mappings observed in production
_MOJIBAKE_MAP = {
    "â\u0080\u0093": "\u2013",  # en-dash –
    "â\u0080\u0094": "\u2014",  # em-dash —
    "â\u0080\u0098": "\u2018",  # left single quote '
    "â\u0080\u0099": "\u2019",  # right single quote '
    "â\u0080\u009c": "\u201c",  # left double quote "
    "â\u0080\u009d": "\u201d",  # right double quote "
    "â\u0080\u00a2": "\u2022",  # bullet •
    "â\u0080\u00a6": "\u2026",  # ellipsis …
    "Î©": "\u03a9",              # ohm Ω
    "Î¼": "\u03bc",              # mu μ
    "Î±": "\u03b1",              # alpha α
    "Î²": "\u03b2",              # beta β
    "Î³": "\u03b3",              # gamma γ
    "Î´": "\u03b4",              # delta δ
    "Ï\u0080": "\u03c0",          # pi π
    "Â°": "\u00b0",              # degree °
    "Â±": "\u00b1",              # plus-minus ±
    "Â§": "\u00a7",              # section §
    "Ã©": "\u00e9",              # e-acute é
    "Ã¨": "\u00e8",              # e-grave è
    "Ã ": "\u00e0",              # a-grave à
    "Ã¶": "\u00f6",              # o-umlaut ö
    "Ã¼": "\u00fc",              # u-umlaut ü
    "Ã¤": "\u00e4",              # a-umlaut ä
    "Ã±": "\u00f1",              # n-tilde ñ
}

# LaTeX command → Unicode replacements
_LATEX_MAP = {
    r"\ge": "\u2265", r"\geq": "\u2265",       # ≥
    r"\le": "\u2264", r"\leq": "\u2264",       # ≤
    r"\ne": "\u2260", r"\neq": "\u2260",       # ≠
    r"\pm": "\u00b1",                            # ±
    r"\mp": "\u2213",                            # ∓
    r"\times": "\u00d7",                         # ×
    r"\div": "\u00f7",                           # ÷
    r"\to": "\u2192", r"\rightarrow": "\u2192", # →
    r"\leftarrow": "\u2190",                     # ←
    r"\Rightarrow": "\u21d2", r"\Leftarrow": "\u21d0",
    r"\infty": "\u221e",                         # ∞
    r"\sum": "\u2211", r"\prod": "\u220f",      # ∑ ∏
    r"\int": "\u222b",                           # ∫
    r"\partial": "\u2202",                       # ∂
    r"\nabla": "\u2207",                         # ∇
    r"\sqrt": "\u221a",                          # √
    r"\approx": "\u2248", r"\sim": "\u223c",    # ≈ ∼
    r"\equiv": "\u2261",                         # ≡
    r"\propto": "\u221d",                        # ∝
    r"\degree": "\u00b0",                        # °
    r"\alpha": "\u03b1", r"\beta": "\u03b2",
    r"\gamma": "\u03b3", r"\delta": "\u03b4",
    r"\epsilon": "\u03b5", r"\zeta": "\u03b6",
    r"\eta": "\u03b7", r"\theta": "\u03b8",
    r"\iota": "\u03b9", r"\kappa": "\u03ba",
    r"\lambda": "\u03bb", r"\mu": "\u03bc",
    r"\nu": "\u03bd", r"\xi": "\u03be",
    r"\pi": "\u03c0", r"\rho": "\u03c1",
    r"\sigma": "\u03c3", r"\tau": "\u03c4",
    r"\phi": "\u03c6", r"\chi": "\u03c7",
    r"\psi": "\u03c8", r"\omega": "\u03c9",
    r"\Gamma": "\u0393", r"\Delta": "\u0394",
    r"\Theta": "\u0398", r"\Lambda": "\u039b",
    r"\Xi": "\u039e", r"\Pi": "\u03a0",
    r"\Sigma": "\u03a3", r"\Phi": "\u03a6",
    r"\Psi": "\u03a8", r"\Omega": "\u03a9",
}


def sanitize_text(text: str) -> str:
    """
    Repair encoding mojibake and convert inline LaTeX to Unicode.
    Safe to call on any LLM output (chat, summary, exec_summary, etc.).
    """
    if not text:
        return text

    # 1. Try to repair UTF-8 misinterpreted as cp1252 (the source of "â" garbage)
    #    If the string contains the Â or â mojibake markers, attempt round-trip.
    if "Â" in text or "â" in text or "Ã" in text or "Î" in text:
        try:
            repaired = text.encode("cp1252", errors="strict").decode("utf-8", errors="strict")
            text = repaired
        except (UnicodeEncodeError, UnicodeDecodeError):
            # Fallback: targeted replacements
            for bad, good in _MOJIBAKE_MAP.items():
                if bad in text:
                    text = text.replace(bad, good)

    # 2. Convert LaTeX inline math to Unicode
    #    Handle `$\foo$`, `\(\foo\)`, and bare `\foo` (with word boundary).
    def _latex_dollar(m: "re.Match[str]") -> str:
        inner = m.group(1).strip()
        return _LATEX_MAP.get(inner, m.group(0))

    # `$\command$` and `$\command{...}$` styles
    text = re.sub(
        r"\$\s*(\\[a-zA-Z]+(?:\s*\{[^}]*\})?)\s*\$",
        _latex_dollar,
        text,
    )
    # `\( ... \)` style
    text = re.sub(
        r"\\\(\s*(\\[a-zA-Z]+(?:\s*\{[^}]*\})?)\s*\\\)",
        _latex_dollar,
        text,
    )

    # Bare LaTeX commands (e.g., `temp \ge 50`)
    for cmd, uni in _LATEX_MAP.items():
        # Use word boundary to avoid matching inside longer commands
        text = re.sub(re.escape(cmd) + r"(?![a-zA-Z])", uni, text)

    # 3. Strip stray double dollar signs around plain text
    text = re.sub(r"\$\$([^$]+)\$\$", r"\1", text)

    return text


def clean_llm_output(text: str) -> str:
    """
    Sanitize and lightly clean LLM output. Removes <thought> blocks and
    obvious metadata leakage but preserves multi-paragraph structure.
    """
    if not text:
        return ""

    # 1. Remove explicit reasoning/thinking blocks
    text = re.sub(r"<thought>.*?</thought>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)

    # 2. Sanitize encoding and LaTeX (always)
    text = sanitize_text(text)

    # 3. Strip lines that look like leaked prompt scaffolding (very conservative)
    leak_markers = (
        "User Context:", "User Question:", "REWRITTEN SEARCH QUERY:",
        "Goal:", "Constraints:", "Thinking:", "Role:", "Task:",
    )
    lines = text.split("\n")
    cleaned_lines = [l for l in lines if not any(m in l for m in leak_markers)]
    return "\n".join(cleaned_lines).strip()



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
    response_format: Optional[Dict[str, str]] = None,
    raw: bool = False,
    **kwargs,
) -> str:
    """
    Blocking generation — sends chat messages, returns full response string.
    No lock needed; llama-server handles concurrency internally.

    Args:
        response_format: e.g. {"type": "json_object"} to force JSON output
                         (llama-server OpenAI-compatible API).
        raw: If True, skip clean_llm_output() and return the raw response.
             Use this for structured generation (JSON, code, etc.).
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
    if response_format:
        payload["response_format"] = response_format

    logger.debug("generate() → POST %s (max_tokens=%d raw=%s)", _CHAT_ENDPOINT, max_tokens, raw)
    resp = requests.post(_CHAT_ENDPOINT, json=payload, timeout=300)
    resp.raise_for_status()
    data = resp.json()
    msg = data["choices"][0]["message"]
    content = msg.get("content", "")
    # Fallback for reasoning models that put output in reasoning_content
    if not content.strip() and "reasoning_content" in msg:
        content = msg["reasoning_content"]

    if raw:
        return content
    return clean_llm_output(content)


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
    try:
        resp.raise_for_status()
    except requests.exceptions.HTTPError as e:
        try:
            err_body = resp.text[:500]
        except Exception:
            err_body = "<unreadable>"
        logger.error("LLM stream_generate HTTP %s: %s | Body: %s", resp.status_code, e, err_body)
        raise

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
        # Non-streaming call for HyDE - increased timeout for reasoning models
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{_LLAMA_SERVER_URL}/v1/chat/completions",
                json={
                    "model": "local-model",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.4,
                    "max_tokens": 1024,
                    "stream": False
                }
            )
            resp.raise_for_status()
            data = resp.json()
            msg = data["choices"][0]["message"]
            content = msg.get("content", "").strip()
            
            # Fallback for reasoning models
            if not content and "reasoning_content" in msg:
                content = msg["reasoning_content"].strip()
            
            if not content:
                logger.warning("LLM returned empty content for HyDE. Raw response: %s", data)
                return query
                
            return clean_llm_output(content)
    except Exception as e:
        logger.warning("HyDE generation failed (%s: %s), falling back to raw query.", type(e).__name__, e)
        return query

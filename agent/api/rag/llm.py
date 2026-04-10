"""
AGRA Phase 2 — RAG: LLM Engine (Gemma 4 31B-IT via llama-cpp-python)
Singleton loader for the GGUF model with blocking and streaming generation.
Uses the native Jinja2/minja chat template embedded in the GGUF metadata.
"""

import glob
import logging
import threading
from pathlib import Path
from typing import Generator, List, Dict, Any, Optional

logger = logging.getLogger("agra.llm")

_MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "models"
_GEMMA_DIR = _MODELS_DIR / "gemma4-31b-it"
_GGUF_PATTERN = "google_gemma-4-31B-it-Q4_K_L.gguf"

# LLM configuration
_N_GPU_LAYERS = -1      # Offload all layers to GPU
_N_CTX = 32768          # 32k context window
_MAX_TOKENS_DEFAULT = 2048


def _find_gguf_path() -> str:
    """Locate the GGUF file, handling potential subdirectory structures."""
    # Direct match
    direct = _GEMMA_DIR / _GGUF_PATTERN
    if direct.exists():
        return str(direct)

    # Search recursively
    matches = list(_GEMMA_DIR.rglob("*.gguf"))
    if matches:
        # Prefer the Q4_K_L file
        for m in matches:
            if "Q4_K_L" in m.name:
                return str(m)
        return str(matches[0])

    raise FileNotFoundError(
        f"No GGUF file found in {_GEMMA_DIR}. "
        f"Run download_models.sh first."
    )


class _LLMSingleton:
    """Thread-safe singleton wrapping the llama-cpp-python Llama instance."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._llm = None
        return cls._instance

    def load(self) -> None:
        if self._llm is not None:
            return
        from llama_cpp import Llama

        gguf_path = _find_gguf_path()
        logger.info("Loading Gemma 4 31B-IT from %s …", gguf_path)
        logger.info("Config: n_gpu_layers=%d, n_ctx=%d", _N_GPU_LAYERS, _N_CTX)

        self._llm = Llama(
            model_path=gguf_path,
            n_gpu_layers=_N_GPU_LAYERS,
            n_ctx=_N_CTX,
            verbose=False,
            # Let llama.cpp use the Jinja2 chat template from GGUF metadata
            chat_format=None,
        )
        logger.info("Gemma 4 31B-IT loaded successfully.")

    @property
    def llm(self):
        if self._llm is None:
            self.load()
        return self._llm

    def generate(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = _MAX_TOKENS_DEFAULT,
        temperature: float = 0.3,
        top_p: float = 0.9,
        stop: Optional[List[str]] = None,
    ) -> str:
        """
        Blocking generation — sends chat messages, returns full response string.

        Args:
            messages: List of {"role": "system"|"user"|"assistant", "content": str}
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature.
            top_p: Nucleus sampling threshold.
            stop: Optional stop sequences.

        Returns:
            Generated text as a single string.
        """
        response = self.llm.create_chat_completion(
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            stop=stop or [],
        )
        choice = response["choices"][0]
        return choice["message"]["content"].strip()

    def stream_generate(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = _MAX_TOKENS_DEFAULT,
        temperature: float = 0.3,
        top_p: float = 0.9,
        stop: Optional[List[str]] = None,
    ) -> Generator[str, None, None]:
        """
        Streaming generation — yields tokens one by one.

        Args:
            messages: Chat messages list.
            max_tokens: Maximum tokens to generate.

        Yields:
            Individual token strings as they are generated.
        """
        stream = self.llm.create_chat_completion(
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            stop=stop or [],
            stream=True,
        )
        for chunk in stream:
            delta = chunk["choices"][0].get("delta", {})
            token = delta.get("content", "")
            if token:
                yield token


# ── Module-level singleton ──
_llm_instance = _LLMSingleton()


def load_llm() -> None:
    """Pre-load the LLM into GPU memory (call at startup)."""
    _llm_instance.load()


def generate(
    messages: List[Dict[str, str]],
    max_tokens: int = _MAX_TOKENS_DEFAULT,
    temperature: float = 0.3,
    **kwargs,
) -> str:
    """Blocking generation → full response string."""
    return _llm_instance.generate(messages, max_tokens, temperature, **kwargs)


def stream_generate(
    messages: List[Dict[str, str]],
    max_tokens: int = _MAX_TOKENS_DEFAULT,
    temperature: float = 0.3,
    **kwargs,
) -> Generator[str, None, None]:
    """Streaming generation → yields tokens."""
    return _llm_instance.stream_generate(messages, max_tokens, temperature, **kwargs)

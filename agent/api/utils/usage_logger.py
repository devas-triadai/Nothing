"""
AGRA Phase 2 — Usage Logger
Fire-and-forget utility to POST usage events to the backend analytics service.
Runs in a background thread so it never blocks the main request.
"""

import logging
import os
import threading
from typing import Optional

import requests

logger = logging.getLogger("agra.usage_logger")

# Backend URL — default to localhost:8000, override via env
_BACKEND_URL = os.getenv("AGRA_BACKEND_URL", "http://localhost:8000")
_USAGE_ENDPOINT = f"{_BACKEND_URL}/api/usage/log"

# Timeout for the POST (seconds)
_TIMEOUT = 5


def log_usage(
    action_type: str,
    module: str,
    token: str,
    response_time_ms: float = 0.0,
    input_tokens: int = 0,
    output_tokens: int = 0,
    status: str = "success",
    user_id: Optional[int] = None,
    metadata_: Optional[str] = None,
) -> None:
    """
    Log a usage event to the backend analytics service.
    
    This is fire-and-forget: runs in a daemon thread, never blocks the caller,
    and silently handles any errors (network issues, backend downtime, etc.).
    
    Args:
        action_type: Type of action (e.g. 'chat', 'ppt', 'quiz', 'summary', 'compliance')
        module:      Module name (e.g. 'rag', 'generate', 'compliance')
        token:       JWT token for authentication
        response_time_ms: How long the operation took
        input_tokens:  Approximate input token count
        output_tokens: Approximate output token count
        status:      'success' or 'error'
        user_id:     Optional explicit user ID override
    """
    def _send():
        try:
            payload = {
                "action_type": action_type,
                "module": module,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "response_time_ms": response_time_ms,
                "status": status,
            }
            if user_id is not None:
                payload["user_id"] = user_id
            if metadata_ is not None:
                payload["metadata_"] = metadata_

            headers = {
                "Content-Type": "application/json",
            }
            if token:
                headers["Authorization"] = f"Bearer {token}"

            resp = requests.post(
                _USAGE_ENDPOINT,
                json=payload,
                headers=headers,
                timeout=_TIMEOUT,
            )
            if resp.status_code == 201:
                logger.debug("Usage logged: %s/%s (%.0fms)", action_type, module, response_time_ms)
            else:
                logger.warning(
                    "Usage log returned %d: %s",
                    resp.status_code,
                    resp.text[:200],
                )
        except requests.exceptions.ConnectionError:
            logger.debug("Usage logger: backend unreachable at %s (non-blocking)", _USAGE_ENDPOINT)
        except Exception as e:
            logger.debug("Usage logger error (non-blocking): %s", e)

    thread = threading.Thread(target=_send, daemon=True)
    thread.start()

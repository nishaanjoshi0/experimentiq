"""Rate limiting helpers for the ExperimentIQ API."""

from __future__ import annotations

from typing import Any, Final

from slowapi import Limiter
from starlette.requests import Request


DEFAULT_RATE_LIMIT: Final[str] = "60/minute"
LLM_RATE_LIMIT: Final[str] = "10/minute"
ANONYMOUS_RATE_LIMIT_KEY: Final[str] = "anonymous"


def get_rate_limit_key(request: Request) -> str:
    """Return the authenticated user identifier for rate limiting."""
    user_id = getattr(request.state, "user_id", None)
    if user_id:
        return str(user_id)
    return ANONYMOUS_RATE_LIMIT_KEY


limiter = Limiter(key_func=get_rate_limit_key, default_limits=[DEFAULT_RATE_LIMIT])


def llm_limit() -> Any:
    """Return a stricter limit decorator for LLM-powered endpoints."""
    return limiter.limit(LLM_RATE_LIMIT)

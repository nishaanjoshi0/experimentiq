"""Structured request logging middleware for the ExperimentIQ API."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Final

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


LOGGER_NAME: Final[str] = "experimentiq.api"
LOG_LEVEL_ENV_VAR: Final[str] = "LOG_LEVEL"
DEFAULT_LOG_LEVEL: Final[str] = "INFO"
UTF8_ENCODING: Final[str] = "utf-8"


def configure_logging() -> None:
    """Configure the application logger using the LOG_LEVEL environment variable."""
    log_level = os.getenv(LOG_LEVEL_ENV_VAR, DEFAULT_LOG_LEVEL).upper()
    logging.basicConfig(level=getattr(logging, log_level, logging.INFO), format="%(message)s")


def hash_user_id(user_id: str | None) -> str | None:
    """Return a SHA-256 hash of the user identifier for privacy-safe logging."""
    if user_id is None:
        return None
    return hashlib.sha256(user_id.encode(UTF8_ENCODING)).hexdigest()


def build_log_payload(
    request: Request,
    response: Response,
    latency_ms: float,
    hashed_user_id: str | None,
) -> dict[str, Any]:
    """Build the structured request log payload."""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "method": request.method,
        "path": request.url.path,
        "status_code": response.status_code,
        "latency_ms": round(latency_ms, 2),
        "hashed_user_id": hashed_user_id,
    }


class StructuredLoggingMiddleware(BaseHTTPMiddleware):
    """Log request metadata as a structured JSON object."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        """Log request metadata after the downstream response is produced."""
        started_at = time.perf_counter()
        response = await call_next(request)
        latency_ms = (time.perf_counter() - started_at) * 1000
        user_id = getattr(request.state, "user_id", None)
        payload = build_log_payload(request, response, latency_ms, hash_user_id(user_id))
        logging.getLogger(LOGGER_NAME).info(json.dumps(payload))
        return response

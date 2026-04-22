"""Health check routes for the ExperimentIQ API."""

from __future__ import annotations

import os
from typing import Final

from fastapi import APIRouter


ROUTE_PATH: Final[str] = "/health"
STATUS_VALUE: Final[str] = "ok"
VERSION_VALUE: Final[str] = "0.1.0"
ENVIRONMENT_ENV_VAR: Final[str] = "ENVIRONMENT"
DEFAULT_ENVIRONMENT: Final[str] = "development"

router = APIRouter(tags=["health"])


@router.get(ROUTE_PATH)
async def health_check() -> dict[str, str]:
    """Return the service health status and runtime environment."""
    return {
        "status": STATUS_VALUE,
        "version": VERSION_VALUE,
        "environment": os.getenv(ENVIRONMENT_ENV_VAR, DEFAULT_ENVIRONMENT),
    }

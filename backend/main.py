"""FastAPI application entrypoint for the ExperimentIQ API."""

from __future__ import annotations

from contextlib import asynccontextmanager
import logging
import os
from typing import Final

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from api.experiments import router as experiments_router
from api.health import router as health_router
from api.interpretation import router as interpretation_router
from api.monitoring import router as monitoring_router
from middleware.auth import ClerkAuthMiddleware
from middleware.logging import StructuredLoggingMiddleware, configure_logging
from middleware.rate_limit import limiter


APP_TITLE: Final[str] = "ExperimentIQ API"
APP_VERSION: Final[str] = "0.1.0"
API_V1_PREFIX: Final[str] = "/api/v1"
HEALTH_PREFIX: Final[str] = ""
DEVELOPMENT_ENVIRONMENT: Final[str] = "development"
ENVIRONMENT_ENV_VAR: Final[str] = "ENVIRONMENT"
DEFAULT_ENVIRONMENT: Final[str] = DEVELOPMENT_ENVIRONMENT
STARTUP_LOG_MESSAGE: Final[str] = "ExperimentIQ API started"


def load_environment() -> str:
    """Load environment variables and return the active environment name."""
    load_dotenv()
    return os.getenv(ENVIRONMENT_ENV_VAR, DEFAULT_ENVIRONMENT)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run application startup and shutdown lifecycle behavior."""
    logging.getLogger(__name__).info(
        STARTUP_LOG_MESSAGE,
        extra={"environment": app.state.environment},
    )
    yield


def create_app() -> FastAPI:
    """Create and configure the ExperimentIQ FastAPI application."""
    environment = load_environment()
    configure_logging()

    app = FastAPI(title=APP_TITLE, version=APP_VERSION, lifespan=lifespan)
    app.state.environment = environment
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    api_v1_router = APIRouter(prefix=API_V1_PREFIX)

    if environment == DEVELOPMENT_ENVIRONMENT:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(ClerkAuthMiddleware)
    app.add_middleware(StructuredLoggingMiddleware)

    api_v1_router.include_router(experiments_router)
    api_v1_router.include_router(monitoring_router)
    api_v1_router.include_router(interpretation_router)

    app.include_router(api_v1_router)
    app.include_router(health_router, prefix=HEALTH_PREFIX)

    return app


app = create_app()

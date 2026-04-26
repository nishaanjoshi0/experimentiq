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

from api.analytics import router as analytics_router
from api.auth_google import router as auth_google_router
from api.datasets_api import router as datasets_router
from api.experiment_interpret import router as experiment_interpret_router
from api.experiments import router as experiments_router
from api.health import router as health_router
from api.interpretation import router as interpretation_router
from api.monitoring import router as monitoring_router
from api.opportunities import router as opportunities_router
from api.start_experiment import router as start_experiment_router
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
DEFAULT_DEV_ORIGIN: Final[str] = "http://localhost:3001"


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

    is_dev = environment == DEVELOPMENT_ENVIRONMENT

    # Disable interactive docs in production — never expose the full API schema publicly.
    docs_url = "/docs" if is_dev else None
    redoc_url = "/redoc" if is_dev else None
    openapi_url = "/openapi.json" if is_dev else None

    app = FastAPI(
        title=APP_TITLE,
        version=APP_VERSION,
        lifespan=lifespan,
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
    )
    app.state.environment = environment
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    api_v1_router = APIRouter(prefix=API_V1_PREFIX)

    # Always require an explicit origins list — never allow wildcard.
    # In dev, defaults to localhost:3001 if ALLOWED_ORIGINS is not set.
    # In production, ALLOWED_ORIGINS must be set or the middleware rejects all cross-origin requests.
    raw_origins = os.getenv("ALLOWED_ORIGINS", DEFAULT_DEV_ORIGIN if is_dev else "")
    allowed_origins = [o.strip() for o in raw_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(ClerkAuthMiddleware)
    app.add_middleware(StructuredLoggingMiddleware)

    api_v1_router.include_router(experiments_router)
    api_v1_router.include_router(experiment_interpret_router)
    api_v1_router.include_router(start_experiment_router)
    api_v1_router.include_router(monitoring_router)
    api_v1_router.include_router(interpretation_router)
    api_v1_router.include_router(opportunities_router)
    api_v1_router.include_router(analytics_router)
    api_v1_router.include_router(auth_google_router)
    api_v1_router.include_router(datasets_router)

    app.include_router(api_v1_router)
    app.include_router(health_router, prefix=HEALTH_PREFIX)

    return app


app = create_app()

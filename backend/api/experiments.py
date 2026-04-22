"""Experiment-related API routes for the ExperimentIQ backend."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from api.utils import hash_value
from agents.framing_agent import ExperimentDesign, run_framing_agent
from middleware.rate_limit import llm_limit
from services.bigquery import BigQueryServiceError
from services.growthbook import GrowthBookAPIError, GrowthBookClient, get_growthbook_client


LOGGER_NAME = "experimentiq.api.experiments"
EXPERIMENTS_PREFIX = "/experiments"
FRAME_PATH = "/frame"
EXPERIMENT_ID_PATH = "/{experiment_id}"
INTERNAL_SERVER_ERROR_MESSAGE = "An unexpected error occurred."
UPSTREAM_ERROR_MESSAGE = "A required upstream service failed to respond successfully."

router = APIRouter(prefix=EXPERIMENTS_PREFIX, tags=["experiments"])


class FrameRequest(BaseModel):
    """Request body for experiment framing."""

    hypothesis: str


def get_growthbook_dependency() -> GrowthBookClient:
    """Return the shared GrowthBook client dependency."""
    return get_growthbook_client()


def log_hypothesis_debug(hypothesis: str) -> None:
    """Log a hashed hypothesis identifier at debug level."""
    logging.getLogger(LOGGER_NAME).debug(
        "Framing request received",
        extra={"hypothesis_hash": hash_value(hypothesis)},
    )


def log_experiment_debug(experiment_id: str) -> None:
    """Log a hashed experiment identifier at debug level."""
    logging.getLogger(LOGGER_NAME).debug(
        "Experiment request received",
        extra={"experiment_id_hash": hash_value(experiment_id)},
    )


def map_growthbook_error(error: GrowthBookAPIError) -> HTTPException:
    """Convert a GrowthBook service error into an HTTPException."""
    if error.status_code == status.HTTP_404_NOT_FOUND:
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error.message)
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=UPSTREAM_ERROR_MESSAGE)


@router.post(FRAME_PATH, response_model=ExperimentDesign)
@llm_limit()
async def frame_experiment(request: Request, payload: FrameRequest) -> ExperimentDesign:
    """Frame an experiment design from a vague hypothesis."""
    _ = request
    log_hypothesis_debug(payload.hypothesis)
    try:
        return await run_framing_agent(payload.hypothesis)
    except BigQueryServiceError:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=UPSTREAM_ERROR_MESSAGE) from None
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=INTERNAL_SERVER_ERROR_MESSAGE,
        ) from None


@router.get("", response_model=list[dict[str, Any]])
async def list_experiments(
    limit: int = 20,
    offset: int = 0,
    growthbook_client: GrowthBookClient = Depends(get_growthbook_dependency),
) -> list[dict[str, Any]]:
    """List experiments from GrowthBook."""
    try:
        return await growthbook_client.list_experiments(limit=limit, offset=offset)
    except GrowthBookAPIError as error:
        raise map_growthbook_error(error) from None
    except BigQueryServiceError:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=UPSTREAM_ERROR_MESSAGE) from None
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=INTERNAL_SERVER_ERROR_MESSAGE,
        ) from None


@router.get(EXPERIMENT_ID_PATH, response_model=dict[str, Any])
async def get_experiment(
    experiment_id: str,
    growthbook_client: GrowthBookClient = Depends(get_growthbook_dependency),
) -> dict[str, Any]:
    """Return a single experiment by identifier."""
    log_experiment_debug(experiment_id)
    try:
        return await growthbook_client.get_experiment(experiment_id)
    except GrowthBookAPIError as error:
        raise map_growthbook_error(error) from None
    except BigQueryServiceError:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=UPSTREAM_ERROR_MESSAGE) from None
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=INTERNAL_SERVER_ERROR_MESSAGE,
        ) from None

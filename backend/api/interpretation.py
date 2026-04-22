"""Interpretation API routes for the ExperimentIQ backend."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, status

from api.utils import hash_value
from agents.interpretation_agent import Recommendation, run_interpretation_agent
from middleware.rate_limit import llm_limit
from services.bigquery import BigQueryServiceError
from services.growthbook import GrowthBookAPIError


LOGGER_NAME = "experimentiq.api.interpretation"
INTERPRET_PATH = "/experiments/{experiment_id}/interpret"
RECOMMENDATION_PATH = "/experiments/{experiment_id}/recommendation"
INTERNAL_SERVER_ERROR_MESSAGE = "An unexpected error occurred."
UPSTREAM_ERROR_MESSAGE = "A required upstream service failed to respond successfully."

router = APIRouter(tags=["interpretation"])


def log_experiment_debug(experiment_id: str) -> None:
    """Log a hashed experiment identifier at debug level."""
    logging.getLogger(LOGGER_NAME).debug(
        "Interpretation request received",
        extra={"experiment_id_hash": hash_value(experiment_id)},
    )


def map_error(error: GrowthBookAPIError) -> HTTPException:
    """Convert a GrowthBook error into an HTTPException."""
    if error.status_code == status.HTTP_404_NOT_FOUND:
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error.message)
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=UPSTREAM_ERROR_MESSAGE)


@router.post(INTERPRET_PATH, response_model=Recommendation)
@llm_limit()
async def interpret_experiment(request: Request, experiment_id: str) -> Recommendation:
    """Generate a recommendation for a completed experiment."""
    _ = request
    log_experiment_debug(experiment_id)
    try:
        return await run_interpretation_agent(experiment_id)
    except GrowthBookAPIError as error:
        raise map_error(error) from None
    except BigQueryServiceError:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=UPSTREAM_ERROR_MESSAGE) from None
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=INTERNAL_SERVER_ERROR_MESSAGE,
        ) from None


@router.get(RECOMMENDATION_PATH, response_model=Recommendation)
async def get_recommendation(experiment_id: str) -> Recommendation:
    """Return the latest recommendation for an experiment by rerunning interpretation."""
    log_experiment_debug(experiment_id)
    try:
        return await run_interpretation_agent(experiment_id)
    except GrowthBookAPIError as error:
        raise map_error(error) from None
    except BigQueryServiceError:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=UPSTREAM_ERROR_MESSAGE) from None
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=INTERNAL_SERVER_ERROR_MESSAGE,
        ) from None

"""Monitoring API routes for the ExperimentIQ backend."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, status

from api.utils import hash_value
from agents.monitoring_agent import MonitoringReport, run_monitoring_agent
from middleware.rate_limit import llm_limit
from services.bigquery import BigQueryServiceError
from services.growthbook import GrowthBookAPIError


LOGGER_NAME = "experimentiq.api.monitoring"
MONITOR_PATH = "/experiments/{experiment_id}/monitor"
INTERNAL_SERVER_ERROR_MESSAGE = "An unexpected error occurred."
UPSTREAM_ERROR_MESSAGE = "A required upstream service failed to respond successfully."

router = APIRouter(tags=["monitoring"])


@router.get(MONITOR_PATH, response_model=MonitoringReport)
@llm_limit()
async def get_monitoring_report(request: Request, experiment_id: str) -> MonitoringReport:
    """Generate a monitoring report for an experiment."""
    _ = request
    logging.getLogger(LOGGER_NAME).debug(
        "Monitoring request received",
        extra={"experiment_id_hash": hash_value(experiment_id)},
    )
    try:
        return await run_monitoring_agent(experiment_id)
    except GrowthBookAPIError as error:
        if error.status_code == status.HTTP_404_NOT_FOUND:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error.message) from None
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=UPSTREAM_ERROR_MESSAGE) from None
    except BigQueryServiceError:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=UPSTREAM_ERROR_MESSAGE) from None
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=INTERNAL_SERVER_ERROR_MESSAGE,
        ) from None

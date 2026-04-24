"""Opportunity discovery API route for the ExperimentIQ backend."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from agents.opportunity_agent import OpportunityReport, run_opportunity_agent
from middleware.rate_limit import llm_limit


LOGGER_NAME = "experimentiq.api.opportunities"
OPPORTUNITIES_PREFIX = "/opportunities"
DISCOVER_PATH = "/discover"
INTERNAL_SERVER_ERROR_MESSAGE = "An unexpected error occurred."

router = APIRouter(prefix=OPPORTUNITIES_PREFIX, tags=["opportunities"])


class OpportunityRequest(BaseModel):
    """Request body for opportunity discovery."""

    company_description: str = ""
    current_metrics: dict[str, float] = {}
    data_source: str = "demo"
    csv_content: str | None = None


@router.post(DISCOVER_PATH, response_model=OpportunityReport)
@llm_limit()
async def discover_opportunities(
    request: Request,
    payload: OpportunityRequest,
) -> OpportunityReport:
    """Run the opportunity discovery agent and return ranked experiment opportunities."""
    _ = request
    logger = logging.getLogger(LOGGER_NAME)

    if payload.data_source not in ("demo", "csv"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="data_source must be 'demo' or 'csv'.",
        )
    if payload.data_source == "csv" and not payload.csv_content:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="csv_content is required when data_source is 'csv'.",
        )

    logger.debug(
        "Opportunity discovery request received",
        extra={"data_source": payload.data_source},
    )

    try:
        return await run_opportunity_agent(
            company_description=payload.company_description,
            current_metrics=payload.current_metrics,
            data_source=payload.data_source,
            csv_content=payload.csv_content,
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=INTERNAL_SERVER_ERROR_MESSAGE,
        ) from None

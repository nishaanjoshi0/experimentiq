"""Analytics platform API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

import httpx

from agents.opportunity_agent import OpportunityReport, run_opportunity_agent
from middleware.rate_limit import llm_limit
from services.analytics_ingestion import ingest_demo
from services.ga4 import build_analytics_summary_from_ga4
from services.oauth_store import get_ga4_connection


ANALYTICS_PREFIX = "/analytics"
router = APIRouter(prefix=ANALYTICS_PREFIX, tags=["analytics"])


class GA4RecommendationsRequest(BaseModel):
    company_description: str = ""
    current_metrics: dict[str, float] = {}


@router.post("/ga4/recommendations", response_model=OpportunityReport)
@llm_limit()
async def get_ga4_recommendations(
    request: Request,
    payload: GA4RecommendationsRequest,
) -> OpportunityReport:
    """Pull live GA4 data and return ranked experiment opportunities."""
    user_id = getattr(request.state, "user_id", "anonymous")
    conn = get_ga4_connection(user_id)

    if not conn:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="GA4 not connected. Connect your analytics account first.",
        )

    try:
        analytics_summary = await build_analytics_summary_from_ga4(
            access_token=conn.access_token,
            property_id=conn.property_id,
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 429:
            analytics_summary = ingest_demo()
        else:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to fetch GA4 data: {exc}",
            ) from None
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch GA4 data: {exc}",
        ) from None

    return await run_opportunity_agent(
        company_description=payload.company_description,
        current_metrics=payload.current_metrics,
        data_source="ga4",
        analytics_summary=analytics_summary,
    )

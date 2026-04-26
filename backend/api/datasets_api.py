"""Dataset management API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from agents.opportunity_agent import OpportunityReport, run_opportunity_agent
from middleware.rate_limit import llm_limit
from services.csv_ingestion import ingest_csv_universal
from services.dataset_adapters import DATASET_REGISTRY


DATASETS_PREFIX = "/datasets"
router = APIRouter(prefix=DATASETS_PREFIX, tags=["datasets"])


class DatasetAnalyzeRequest(BaseModel):
    csv_content: str
    dataset_type: str | None = None
    company_description: str = ""
    current_metrics: dict[str, float] = {}


@router.get("", response_model=list[dict[str, Any]])
async def list_datasets() -> list[dict[str, Any]]:
    return DATASET_REGISTRY


@router.post("/analyze", response_model=OpportunityReport)
@llm_limit()
async def analyze_dataset(
    request: Request,
    payload: DatasetAnalyzeRequest,
) -> OpportunityReport:
    _ = request
    if not payload.csv_content.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="csv_content is required.",
        )

    try:
        analytics_summary = await ingest_csv_universal(
            payload.csv_content,
            payload.company_description,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to parse dataset: {exc}",
        ) from None

    return await run_opportunity_agent(
        company_description=payload.company_description,
        current_metrics=payload.current_metrics,
        data_source=payload.dataset_type or "upload",
        analytics_summary=analytics_summary,
    )

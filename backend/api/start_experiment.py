"""Start-experiment route — creates an experiment in GrowthBook from a design."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from services.growthbook import GrowthBookAPIError, GrowthBookClient, get_growthbook_client


START_PREFIX = "/experiments"
router = APIRouter(prefix=START_PREFIX, tags=["experiments"])


class StartExperimentRequest(BaseModel):
    name: str
    hypothesis: str
    description: str = ""
    tags: list[str] = []


class StartExperimentResponse(BaseModel):
    experiment_id: str
    name: str
    growthbook_url: str


def _get_growthbook() -> GrowthBookClient:
    return get_growthbook_client()


@router.post("/start", response_model=StartExperimentResponse)
async def start_experiment(
    request: Request,
    payload: StartExperimentRequest,
    growthbook: GrowthBookClient = Depends(_get_growthbook),
) -> StartExperimentResponse:
    """Create a new experiment in GrowthBook from an experiment design."""
    _ = request
    try:
        created = await growthbook.create_experiment(
            name=payload.name,
            hypothesis=payload.hypothesis,
            description=payload.description,
            tags=payload.tags or ["experimentiq"],
        )
    except GrowthBookAPIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"GrowthBook experiment creation failed: {exc.message}",
        ) from None
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GrowthBook is not configured. Set GROWTHBOOK_API_URL and GROWTHBOOK_API_KEY.",
        ) from None
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred.",
        ) from None

    experiment_id = created.get("id", "")
    import os
    gb_url = os.getenv("GROWTHBOOK_API_URL", "http://localhost:3000")
    return StartExperimentResponse(
        experiment_id=experiment_id,
        name=created.get("name", payload.name),
        growthbook_url=f"{gb_url}/experiment/{experiment_id}",
    )

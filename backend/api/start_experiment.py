"""Start-experiment route — creates an experiment in GrowthBook, LaunchDarkly, or Statsig."""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel

from services.growthbook import GrowthBookAPIError, GrowthBookClient, get_growthbook_client
from services.launchdarkly import LaunchDarklyAPIError, LaunchDarklyClient
from services.oauth_store import get_exp_platform_connection


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
    platform: str
    platform_url: str
    # keep legacy field for backward compat with frontend
    growthbook_url: str = ""


def _get_growthbook() -> GrowthBookClient:
    return get_growthbook_client()


@router.post("/start", response_model=StartExperimentResponse)
async def start_experiment(
    request: Request,
    payload: StartExperimentRequest,
    platform: str = Query(default="growthbook"),
    growthbook: GrowthBookClient = Depends(_get_growthbook),
) -> StartExperimentResponse:
    """Create a new experiment in the selected platform."""
    user_id = getattr(request.state, "user_id", "anonymous")

    # ── GrowthBook ────────────────────────────────────────────────────────────
    if platform == "growthbook":
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
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="GrowthBook is not configured.",
            ) from None
        except Exception:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error.") from None

        experiment_id = created.get("id", "")
        gb_url = os.getenv("GROWTHBOOK_API_URL", "http://localhost:3000")
        url = f"{gb_url}/experiment/{experiment_id}"
        return StartExperimentResponse(
            experiment_id=experiment_id,
            name=created.get("name", payload.name),
            platform="growthbook",
            platform_url=url,
            growthbook_url=url,
        )

    # ── LaunchDarkly ──────────────────────────────────────────────────────────
    if platform == "launchdarkly":
        conn = get_exp_platform_connection(user_id, "launchdarkly")
        if not conn:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="LaunchDarkly not connected.",
            )
        try:
            client = LaunchDarklyClient(
                access_token=conn.api_key,
                project_key=conn.extra.get("project_key") or "default",
                environment_key=conn.extra.get("environment_key") or "test",
            )
            created = await client.create_experiment(
                name=payload.name,
                hypothesis=payload.hypothesis,
                description=payload.description,
            )
            await client.close()
        except LaunchDarklyAPIError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"LaunchDarkly experiment creation failed: {exc.message}",
            ) from None
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"LaunchDarkly error: {exc}",
            ) from None

        project_key = conn.extra.get("project_key") or "default"
        environment_key = conn.extra.get("environment_key") or "test"
        experiment_key = created.get("key") or created.get("id") or ""
        ld_url = f"https://app.launchdarkly.com/{project_key}/{environment_key}/experiments"
        return StartExperimentResponse(
            experiment_id=experiment_key,
            name=created.get("name", payload.name),
            platform="launchdarkly",
            platform_url=ld_url,
        )

    # ── Statsig ───────────────────────────────────────────────────────────────
    if platform == "statsig":
        conn = get_exp_platform_connection(user_id, "statsig")
        if not conn:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Statsig not connected.",
            )
        # Statsig experiment creation requires a Pro Console API key.
        # Return a deep-link so the user can finish setup in the Statsig UI.
        statsig_url = "https://console.statsig.com/experiments/new"
        return StartExperimentResponse(
            experiment_id="",
            name=payload.name,
            platform="statsig",
            platform_url=statsig_url,
        )

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown platform: {platform}")

"""Experiment-related API routes for the ExperimentIQ backend."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel

from api.utils import hash_value
from agents.framing_agent import ExperimentDesign, run_framing_agent
from middleware.rate_limit import llm_limit
from services.bigquery import BigQueryServiceError
from services.growthbook import GrowthBookAPIError, GrowthBookClient, get_growthbook_client
from services.launchdarkly import LaunchDarklyAPIError, LaunchDarklyClient
from services.statsig import StatsigAPIError, StatsigClient
from services.oauth_store import (
    ApiKeyConnection,
    delete_exp_platform_connection,
    get_exp_platform_connection,
    list_exp_platform_connections,
    save_exp_platform_connection,
)


LOGGER_NAME = "experimentiq.api.experiments"
EXPERIMENTS_PREFIX = "/experiments"
FRAME_PATH = "/frame"
EXPERIMENT_ID_PATH = "/{experiment_id}"
INTERNAL_SERVER_ERROR_MESSAGE = "An unexpected error occurred."
UPSTREAM_ERROR_MESSAGE = "A required upstream service failed to respond successfully."

router = APIRouter(prefix=EXPERIMENTS_PREFIX, tags=["experiments"])


# ── Request / response models ─────────────────────────────────────────────────

class FrameRequest(BaseModel):
    hypothesis: str


class LaunchDarklyConnectRequest(BaseModel):
    access_token: str
    project_key: str = "default"
    environment_key: str = "test"


class StatsigConnectRequest(BaseModel):
    server_secret: str


class PlatformStatusResponse(BaseModel):
    platform: str
    connected: bool
    connected_at: str | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_growthbook_dependency() -> GrowthBookClient:
    return get_growthbook_client()


def log_hypothesis_debug(hypothesis: str) -> None:
    logging.getLogger(LOGGER_NAME).debug(
        "Framing request received",
        extra={"hypothesis_hash": hash_value(hypothesis)},
    )


def log_experiment_debug(experiment_id: str) -> None:
    logging.getLogger(LOGGER_NAME).debug(
        "Experiment request received",
        extra={"experiment_id_hash": hash_value(experiment_id)},
    )


def map_growthbook_error(error: GrowthBookAPIError) -> HTTPException:
    if error.status_code == status.HTTP_404_NOT_FOUND:
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error.message)
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=UPSTREAM_ERROR_MESSAGE)


# ── Platform connect / disconnect / status ────────────────────────────────────

@router.post("/platforms/launchdarkly/connect", response_model=PlatformStatusResponse)
async def connect_launchdarkly(request: Request, payload: LaunchDarklyConnectRequest) -> PlatformStatusResponse:
    """Validate and store LaunchDarkly credentials for this user."""
    user_id = getattr(request.state, "user_id", "anonymous")
    try:
        client = LaunchDarklyClient(
            access_token=payload.access_token,
            project_key=payload.project_key,
            environment_key=payload.environment_key,
        )
        await client.list_experiments()
        await client.close()
    except LaunchDarklyAPIError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid LaunchDarkly credentials: {exc.message}") from None
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Could not connect to LaunchDarkly: {exc}") from None

    conn = ApiKeyConnection.create(
        platform="launchdarkly",
        api_key=payload.access_token,
        extra={"project_key": payload.project_key, "environment_key": payload.environment_key},
    )
    save_exp_platform_connection(user_id, conn)
    return PlatformStatusResponse(platform="launchdarkly", connected=True, connected_at=conn.connected_at)


@router.delete("/platforms/launchdarkly/disconnect", response_model=PlatformStatusResponse)
async def disconnect_launchdarkly(request: Request) -> PlatformStatusResponse:
    user_id = getattr(request.state, "user_id", "anonymous")
    delete_exp_platform_connection(user_id, "launchdarkly")
    return PlatformStatusResponse(platform="launchdarkly", connected=False)


@router.post("/platforms/statsig/connect", response_model=PlatformStatusResponse)
async def connect_statsig(request: Request, payload: StatsigConnectRequest) -> PlatformStatusResponse:
    """Validate and store Statsig credentials for this user."""
    user_id = getattr(request.state, "user_id", "anonymous")
    try:
        client = StatsigClient(secret=payload.server_secret)
        await client.list_experiments()
        await client.close()
    except StatsigAPIError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid Statsig credentials: {exc.message}") from None
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Could not connect to Statsig: {exc}") from None

    conn = ApiKeyConnection.create(
        platform="statsig",
        api_key=payload.server_secret,
    )
    save_exp_platform_connection(user_id, conn)
    return PlatformStatusResponse(platform="statsig", connected=True, connected_at=conn.connected_at)


@router.delete("/platforms/statsig/disconnect", response_model=PlatformStatusResponse)
async def disconnect_statsig(request: Request) -> PlatformStatusResponse:
    user_id = getattr(request.state, "user_id", "anonymous")
    delete_exp_platform_connection(user_id, "statsig")
    return PlatformStatusResponse(platform="statsig", connected=False)


@router.get("/platforms/status")
async def get_experiment_platform_statuses(request: Request) -> dict:
    """Return connection status for all experiment platforms."""
    user_id = getattr(request.state, "user_id", "anonymous")
    connections = list_exp_platform_connections(user_id)
    return {
        "growthbook": {"connected": True},  # always available (self-hosted)
        "launchdarkly": {
            "connected": "launchdarkly" in connections,
            "connected_at": connections.get("launchdarkly"),
        },
        "statsig": {
            "connected": "statsig" in connections,
            "connected_at": connections.get("statsig"),
        },
    }


# ── Experiment framing ────────────────────────────────────────────────────────

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
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=INTERNAL_SERVER_ERROR_MESSAGE) from None


# ── List experiments ──────────────────────────────────────────────────────────

@router.get("", response_model=list[dict[str, Any]])
async def list_experiments(
    request: Request,
    limit: int = 20,
    offset: int = 0,
    platform: str = Query(default="growthbook"),
    growthbook_client: GrowthBookClient = Depends(get_growthbook_dependency),
) -> list[dict[str, Any]]:
    """List experiments from the selected platform using per-user credentials."""
    user_id = getattr(request.state, "user_id", "anonymous")

    try:
        if platform == "launchdarkly":
            conn = get_exp_platform_connection(user_id, "launchdarkly")
            if not conn:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="LaunchDarkly not connected. Connect your account first.",
                )
            client = LaunchDarklyClient(
                access_token=conn.api_key,
                project_key=conn.extra.get("project_key") or "default",
                environment_key=conn.extra.get("environment_key") or "test",
            )
            result = await client.list_experiments()
            await client.close()
            return result

        if platform == "statsig":
            conn = get_exp_platform_connection(user_id, "statsig")
            if not conn:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Statsig not connected. Connect your account first.",
                )
            client = StatsigClient(secret=conn.api_key)
            result = await client.list_experiments()
            await client.close()
            return result

        return await growthbook_client.list_experiments(limit=limit, offset=offset)

    except HTTPException:
        raise
    except (GrowthBookAPIError, LaunchDarklyAPIError, StatsigAPIError) as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from None
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=INTERNAL_SERVER_ERROR_MESSAGE) from None


# ── Single experiment ─────────────────────────────────────────────────────────

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
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=INTERNAL_SERVER_ERROR_MESSAGE) from None

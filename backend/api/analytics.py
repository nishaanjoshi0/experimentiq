"""Analytics platform API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

import httpx

from agents.opportunity_agent import OpportunityReport, run_opportunity_agent
from middleware.rate_limit import llm_limit
from services.analytics_ingestion import ingest_demo
from services.amplitude import build_analytics_summary_from_amplitude, validate_amplitude_credentials
from services.ga4 import build_analytics_summary_from_ga4
from services.mixpanel import build_analytics_summary_from_mixpanel, validate_mixpanel_credentials
from services.oauth_store import (
    ApiKeyConnection,
    delete_platform_connection,
    get_ga4_connection,
    get_platform_connection,
    list_platform_connections,
    save_platform_connection,
)


ANALYTICS_PREFIX = "/analytics"
router = APIRouter(prefix=ANALYTICS_PREFIX, tags=["analytics"])


# ── Request / response models ─────────────────────────────────────────────────

class RecommendationsRequest(BaseModel):
    company_description: str = ""
    current_metrics: dict[str, float] = {}


class GA4RecommendationsRequest(BaseModel):
    company_description: str = ""
    current_metrics: dict[str, float] = {}


class AmplitudeConnectRequest(BaseModel):
    api_key: str
    api_secret: str


class MixpanelConnectRequest(BaseModel):
    username: str
    secret: str
    project_id: str = ""


class PlatformStatusResponse(BaseModel):
    platform: str
    connected: bool
    connected_at: str | None = None


# ── GA4 (existing) ────────────────────────────────────────────────────────────

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


# ── Amplitude ─────────────────────────────────────────────────────────────────

@router.post("/amplitude/connect", response_model=PlatformStatusResponse)
async def connect_amplitude(request: Request, payload: AmplitudeConnectRequest) -> PlatformStatusResponse:
    """Validate and store Amplitude credentials."""
    user_id = getattr(request.state, "user_id", "anonymous")
    try:
        valid = await validate_amplitude_credentials(payload.api_key, payload.api_secret)
    except Exception:
        valid = False

    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Amplitude credentials. Check your API Key and Secret Key.",
        )

    conn = ApiKeyConnection.create(
        platform="amplitude",
        api_key=payload.api_key,
        secret=payload.api_secret,
    )
    save_platform_connection(user_id, conn)
    return PlatformStatusResponse(platform="amplitude", connected=True, connected_at=conn.connected_at)


@router.delete("/amplitude/disconnect", response_model=PlatformStatusResponse)
async def disconnect_amplitude(request: Request) -> PlatformStatusResponse:
    user_id = getattr(request.state, "user_id", "anonymous")
    delete_platform_connection(user_id, "amplitude")
    return PlatformStatusResponse(platform="amplitude", connected=False)


@router.post("/amplitude/recommendations", response_model=OpportunityReport)
@llm_limit()
async def get_amplitude_recommendations(
    request: Request,
    payload: RecommendationsRequest,
) -> OpportunityReport:
    """Pull Amplitude data and return ranked experiment opportunities."""
    user_id = getattr(request.state, "user_id", "anonymous")
    conn = get_platform_connection(user_id, "amplitude")

    if not conn:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Amplitude not connected. Connect your account first.",
        )

    try:
        summary = await build_analytics_summary_from_amplitude(
            api_key=conn.api_key,
            api_secret=conn.secret or "",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch Amplitude data: {exc}",
        ) from None

    return await run_opportunity_agent(
        company_description=payload.company_description,
        current_metrics=payload.current_metrics,
        data_source="amplitude",
        analytics_summary=summary,
    )


# ── Mixpanel ──────────────────────────────────────────────────────────────────

@router.post("/mixpanel/connect", response_model=PlatformStatusResponse)
async def connect_mixpanel(request: Request, payload: MixpanelConnectRequest) -> PlatformStatusResponse:
    """Validate and store Mixpanel credentials."""
    user_id = getattr(request.state, "user_id", "anonymous")
    try:
        valid = await validate_mixpanel_credentials(payload.username, payload.secret, payload.project_id)
    except Exception:
        valid = False

    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Mixpanel credentials. Check your Service Account username and secret.",
        )

    conn = ApiKeyConnection.create(
        platform="mixpanel",
        api_key=payload.username,
        secret=payload.secret,
        extra={"project_id": payload.project_id},
    )
    save_platform_connection(user_id, conn)
    return PlatformStatusResponse(platform="mixpanel", connected=True, connected_at=conn.connected_at)


@router.delete("/mixpanel/disconnect", response_model=PlatformStatusResponse)
async def disconnect_mixpanel(request: Request) -> PlatformStatusResponse:
    user_id = getattr(request.state, "user_id", "anonymous")
    delete_platform_connection(user_id, "mixpanel")
    return PlatformStatusResponse(platform="mixpanel", connected=False)


@router.post("/mixpanel/recommendations", response_model=OpportunityReport)
@llm_limit()
async def get_mixpanel_recommendations(
    request: Request,
    payload: RecommendationsRequest,
) -> OpportunityReport:
    """Pull Mixpanel data and return ranked experiment opportunities."""
    user_id = getattr(request.state, "user_id", "anonymous")
    conn = get_platform_connection(user_id, "mixpanel")

    if not conn:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Mixpanel not connected. Connect your account first.",
        )

    try:
        summary = await build_analytics_summary_from_mixpanel(
            username=conn.api_key,
            secret=conn.secret or "",
            project_id=conn.extra.get("project_id", ""),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch Mixpanel data: {exc}",
        ) from None

    return await run_opportunity_agent(
        company_description=payload.company_description,
        current_metrics=payload.current_metrics,
        data_source="mixpanel",
        analytics_summary=summary,
    )


# ── Platform status (all) ─────────────────────────────────────────────────────

@router.get("/platforms/status")
async def get_all_platform_statuses(request: Request) -> dict:
    """Return connection status for all analytics platforms for this user."""
    user_id = getattr(request.state, "user_id", "anonymous")
    from services.oauth_store import is_ga4_connected
    connections = list_platform_connections(user_id)
    return {
        "ga4": {"connected": is_ga4_connected(user_id)},
        "amplitude": {
            "connected": "amplitude" in connections,
            "connected_at": connections.get("amplitude"),
        },
        "mixpanel": {
            "connected": "mixpanel" in connections,
            "connected_at": connections.get("mixpanel"),
        },
    }

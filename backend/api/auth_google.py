"""Google OAuth routes for GA4 integration."""

from __future__ import annotations

import logging
import os
import urllib.parse

import httpx
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from services.oauth_store import (
    GA4Connection,
    consume_oauth_nonce,
    create_oauth_nonce,
    delete_ga4_connection,
    get_ga4_connection,
    save_ga4_connection,
)


LOGGER_NAME = "experimentiq.auth_google"
AUTH_PREFIX = "/auth/google"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
SCOPES = "https://www.googleapis.com/auth/analytics.readonly openid email"

router = APIRouter(prefix=AUTH_PREFIX, tags=["auth"])


def _oauth_config() -> tuple[str, str, str]:
    client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")
    client_secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")
    redirect_uri = os.getenv(
        "GOOGLE_OAUTH_REDIRECT_URI",
        "http://localhost:3001/api/auth/callback/google",
    )
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Google OAuth not configured. Set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET.",
        )
    return client_id, client_secret, redirect_uri


class InitiateResponse(BaseModel):
    auth_url: str


class CallbackRequest(BaseModel):
    code: str
    state: str | None = None


class ConnectionStatus(BaseModel):
    connected: bool
    email: str = ""
    property_id: str = ""
    connected_at: str = ""


@router.get("/initiate", response_model=InitiateResponse)
async def initiate_google_oauth(request: Request) -> InitiateResponse:
    """Return the Google OAuth authorization URL for the frontend to redirect to."""
    client_id, _, redirect_uri = _oauth_config()
    user_id = getattr(request.state, "user_id", "anonymous")

    # Issue a server-side nonce as the state parameter.
    # The nonce maps to the user_id and is validated on callback —
    # an attacker cannot forge a state value to hijack another user's connection.
    nonce = create_oauth_nonce(user_id)

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",
        "prompt": "consent",
        "state": nonce,
    }
    auth_url = f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"
    return InitiateResponse(auth_url=auth_url)


@router.post("/callback", response_model=ConnectionStatus)
async def handle_google_callback(
    request: Request, payload: CallbackRequest
) -> ConnectionStatus:
    """Exchange auth code for tokens and persist the GA4 connection."""
    client_id, client_secret, redirect_uri = _oauth_config()

    # Validate the state nonce server-side.
    # consume_oauth_nonce checks the nonce exists, hasn't expired, and deletes it
    # on first use — replay attacks and forged state values both return None.
    user_id = consume_oauth_nonce(payload.state or "")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth state parameter.",
        )

    property_id = os.getenv("GA4_DEMO_PROPERTY_ID", "213025502")

    async with httpx.AsyncClient(timeout=15.0) as client:
        token_resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": payload.code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        if token_resp.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Token exchange failed: {token_resp.text}",
            )
        tokens = token_resp.json()

        email = ""
        try:
            userinfo = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {tokens['access_token']}"},
            )
            email = userinfo.json().get("email", "")
        except Exception:
            pass

    connection = GA4Connection.create(
        access_token=tokens["access_token"],
        refresh_token=tokens.get("refresh_token"),
        property_id=property_id,
        email=email,
    )
    save_ga4_connection(user_id, connection)

    logging.getLogger(LOGGER_NAME).info(
        "GA4 connected",
        extra={"user_prefix": user_id[:8], "property_id": property_id},
    )

    return ConnectionStatus(
        connected=True,
        email=email,
        property_id=property_id,
        connected_at=connection.connected_at,
    )


@router.get("/status", response_model=ConnectionStatus)
async def get_connection_status(request: Request) -> ConnectionStatus:
    """Return the GA4 connection status for the current user."""
    user_id = getattr(request.state, "user_id", "anonymous")
    conn = get_ga4_connection(user_id)
    if not conn:
        return ConnectionStatus(connected=False)
    return ConnectionStatus(
        connected=True,
        email=conn.email,
        property_id=conn.property_id,
        connected_at=conn.connected_at,
    )


@router.delete("/disconnect", response_model=ConnectionStatus)
async def disconnect_ga4(request: Request) -> ConnectionStatus:
    """Remove the GA4 connection for the current user."""
    user_id = getattr(request.state, "user_id", "anonymous")
    delete_ga4_connection(user_id)
    return ConnectionStatus(connected=False)

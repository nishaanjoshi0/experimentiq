"""Authentication middleware for Clerk JWT validation."""

from __future__ import annotations

import json
import os
import time
from typing import Any, Final

import httpx
import jwt
from fastapi.responses import JSONResponse
from jwt import InvalidTokenError
from jwt.algorithms import RSAAlgorithm
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


AUTHORIZATION_HEADER: Final[str] = "Authorization"
BEARER_PREFIX: Final[str] = "Bearer "
HEALTH_PATH: Final[str] = "/health"
DOCS_PATH: Final[str] = "/docs"
OPENAPI_PATH: Final[str] = "/openapi.json"
REDOC_PATH: Final[str] = "/redoc"
PUBLIC_PATHS: Final[frozenset[str]] = frozenset({HEALTH_PATH, DOCS_PATH, OPENAPI_PATH, REDOC_PATH})
JWKS_URL_ENV_VAR: Final[str] = "CLERK_JWKS_URL"
JWKS_CACHE_TTL_SECONDS: Final[int] = 300
STATUS_UNAUTHORIZED: Final[int] = 401
STATUS_FORBIDDEN: Final[int] = 403
MISSING_TOKEN_MESSAGE: Final[str] = "Missing bearer token."
INVALID_TOKEN_MESSAGE: Final[str] = "Invalid or expired token."
MISSING_AUTH_CONFIGURATION_MESSAGE: Final[str] = "Authentication configuration is missing."
UNAUTHORIZED_USER_MESSAGE: Final[str] = "Token is valid but user is not authorized."
SUBJECT_CLAIM: Final[str] = "sub"
USER_ID_CLAIM: Final[str] = "user_id"
ALGORITHMS: Final[list[str]] = ["RS256"]


def get_jwks_url() -> str | None:
    """Return the configured Clerk JWKS URL."""
    return os.getenv(JWKS_URL_ENV_VAR)


def extract_bearer_token(request: Request) -> str:
    """Extract the bearer token from the Authorization header."""
    authorization = request.headers.get(AUTHORIZATION_HEADER, "")
    if not authorization.startswith(BEARER_PREFIX):
        raise ValueError(MISSING_TOKEN_MESSAGE)
    return authorization.removeprefix(BEARER_PREFIX).strip()


def extract_user_id(claims: dict[str, Any]) -> str | None:
    """Extract the authenticated user identifier from JWT claims."""
    subject = claims.get(SUBJECT_CLAIM) or claims.get(USER_ID_CLAIM)
    return str(subject) if subject else None


class ClerkAuthMiddleware(BaseHTTPMiddleware):
    """Validate Clerk-issued JWTs against the configured JWKS endpoint."""

    def __init__(self, app: Any) -> None:
        """Initialize the middleware with empty JWKS cache state."""
        super().__init__(app)
        self._jwks_url = get_jwks_url()
        self._jwks: dict[str, Any] = {}
        self._jwks_loaded_at = 0.0

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        """Authenticate incoming requests unless the route is explicitly public."""
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        if not self._jwks_url:
            return self._json_error_response(STATUS_UNAUTHORIZED, MISSING_AUTH_CONFIGURATION_MESSAGE)

        try:
            token = extract_bearer_token(request)
            claims = await self._decode_token(token)
        except ValueError as error:
            return self._json_error_response(STATUS_UNAUTHORIZED, str(error))
        except InvalidTokenError:
            return self._json_error_response(STATUS_UNAUTHORIZED, INVALID_TOKEN_MESSAGE)
        except httpx.HTTPError:
            return self._json_error_response(STATUS_UNAUTHORIZED, INVALID_TOKEN_MESSAGE)

        user_id = extract_user_id(claims)
        if user_id is None:
            return self._json_error_response(STATUS_FORBIDDEN, UNAUTHORIZED_USER_MESSAGE)

        request.state.user_id = user_id
        request.state.jwt_claims = claims
        return await call_next(request)

    async def _decode_token(self, token: str) -> dict[str, Any]:
        """Decode and verify a JWT using the Clerk JWKS document."""
        header = jwt.get_unverified_header(token)
        key_id = header.get("kid")
        if not key_id:
            raise InvalidTokenError(INVALID_TOKEN_MESSAGE)

        jwks = await self._get_jwks()
        jwk = self._find_signing_key(jwks, key_id)
        public_key = RSAAlgorithm.from_jwk(json.dumps(jwk))

        return jwt.decode(
            token,
            key=public_key,
            algorithms=ALGORITHMS,
            options={"verify_aud": False},
        )

    async def _get_jwks(self) -> dict[str, Any]:
        """Fetch and cache the JWKS document used for signature validation."""
        now = time.time()
        if self._jwks and (now - self._jwks_loaded_at) < JWKS_CACHE_TTL_SECONDS:
            return self._jwks

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(self._jwks_url)
            response.raise_for_status()
            self._jwks = response.json()
            self._jwks_loaded_at = now

        return self._jwks

    def _find_signing_key(self, jwks: dict[str, Any], key_id: str) -> dict[str, Any]:
        """Find the JWK that matches the token key identifier."""
        keys = jwks.get("keys", [])
        for key in keys:
            if key.get("kid") == key_id:
                return key
        raise InvalidTokenError(INVALID_TOKEN_MESSAGE)

    def _json_error_response(self, status_code: int, message: str) -> JSONResponse:
        """Create a JSON error response for authentication failures."""
        return JSONResponse(status_code=status_code, content={"detail": message})

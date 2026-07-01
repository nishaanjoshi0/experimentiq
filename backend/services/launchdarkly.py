"""Async LaunchDarkly REST API client for ExperimentIQ."""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Final

import httpx


LD_API_BASE_URL: Final[str] = "https://app.launchdarkly.com"
LD_ACCESS_TOKEN_ENV_VAR: Final[str] = "LAUNCHDARKLY_ACCESS_TOKEN"
LD_PROJECT_KEY_ENV_VAR: Final[str] = "LAUNCHDARKLY_PROJECT_KEY"
LD_ENVIRONMENT_KEY_ENV_VAR: Final[str] = "LAUNCHDARKLY_ENVIRONMENT_KEY"
DEFAULT_PROJECT_KEY: Final[str] = "default"
DEFAULT_ENVIRONMENT_KEY: Final[str] = "test"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0
LOGGER_NAME: Final[str] = "experimentiq.launchdarkly"
MISSING_CONFIG_MESSAGE: Final[str] = "LAUNCHDARKLY_ACCESS_TOKEN must be set."

_ld_client: LaunchDarklyClient | None = None


class LaunchDarklyAPIError(Exception):
    """Raised when the LaunchDarkly API returns an error response."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def _normalize_status(ld_status: str) -> str:
    """Map a LaunchDarkly experiment status to the ExperimentIQ canonical status."""
    mapping: dict[str, str] = {
        "running": "running",
        "paused": "paused",
        "stopped": "stopped",
        "not_started": "draft",
    }
    return mapping.get(ld_status.lower(), ld_status)


def _normalize_experiment(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize a raw LaunchDarkly experiment object to the ExperimentIQ schema."""
    return {
        "id": raw.get("key") or raw.get("id") or "unknown",
        "name": raw.get("name") or "Untitled experiment",
        "status": _normalize_status(raw.get("currentIteration", {}).get("status", raw.get("status", ""))),
        "hypothesis": raw.get("hypothesis") or raw.get("description") or "",
        "dateCreated": raw.get("creationDate") or raw.get("created_at") or None,
        "_source": "launchdarkly",
    }


class LaunchDarklyClient:
    """Async client for the LaunchDarkly REST API."""

    def __init__(
        self,
        access_token: str | None = None,
        project_key: str | None = None,
        environment_key: str | None = None,
    ) -> None:
        token = access_token or os.getenv(LD_ACCESS_TOKEN_ENV_VAR)
        if not token:
            raise ValueError(MISSING_CONFIG_MESSAGE)

        self._project_key = project_key or os.getenv(LD_PROJECT_KEY_ENV_VAR, DEFAULT_PROJECT_KEY)
        self._env_key = environment_key or os.getenv(LD_ENVIRONMENT_KEY_ENV_VAR, DEFAULT_ENVIRONMENT_KEY)
        self._logger = logging.getLogger(LOGGER_NAME)
        self._client = httpx.AsyncClient(
            base_url=LD_API_BASE_URL,
            headers={"Authorization": token, "LD-API-Version": "20240415"},
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )

    async def __aenter__(self) -> LaunchDarklyClient:
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self.close()

    async def list_experiments(self) -> list[dict[str, Any]]:
        """Return a normalized list of LaunchDarkly experiments."""
        url = f"/api/v2/projects/{self._project_key}/environments/{self._env_key}/experiments"
        response = await self._request("GET", url)
        self._raise_for_error(response)
        payload = response.json()
        items: list[Any] = []
        if isinstance(payload, dict):
            items = payload.get("items", [])
        elif isinstance(payload, list):
            items = payload
        return [_normalize_experiment(item) for item in items if isinstance(item, dict)]

    async def get_current_member_id(self) -> str:
        """Return the first admin member ID in the account."""
        response = await self._request("GET", "/api/v2/members?limit=1")
        self._raise_for_error(response)
        payload = response.json()
        items = payload.get("items", [])
        if not items:
            raise LaunchDarklyAPIError(status_code=404, message="No members found in LaunchDarkly account.")
        return items[0].get("_id", "")

    @staticmethod
    def _slugify(name: str) -> str:
        """Convert a display name to a LD-compatible key (lowercase, hyphens, no special chars)."""
        import re
        slug = name.lower().strip()
        slug = re.sub(r"[^a-z0-9]+", "-", slug)
        slug = slug.strip("-")
        return slug[:128] or "experiment"

    async def create_experiment(
        self,
        name: str,
        hypothesis: str,
        description: str = "",
    ) -> dict[str, Any]:
        """Create a new experiment in LaunchDarkly and return the created object."""
        maintainer_id = await self.get_current_member_id()
        key = self._slugify(name)

        payload: dict[str, Any] = {
            "key": key,
            "name": name,
            "description": description,
            "hypothesis": hypothesis,
            "maintainerId": maintainer_id,
            "randomizationUnit": "user",
            "iteration": {
                "hypothesis": hypothesis,
                "canReshuffleTraffic": True,
                "metrics": [],
                "treatments": [
                    {"baseline": True, "name": "Control", "allocationPercent": "50"},
                    {"baseline": False, "name": "Treatment", "allocationPercent": "50"},
                ],
            },
        }
        url = f"/api/v2/projects/{self._project_key}/environments/{self._env_key}/experiments"
        response = await self._request("POST", url, json=payload)
        self._raise_for_error(response)
        return response.json()

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        started_at = time.perf_counter()
        response = await self._client.request(method, url, **kwargs)
        latency_ms = (time.perf_counter() - started_at) * 1000
        self._logger.debug(
            "LaunchDarkly API call",
            extra={
                "method": method,
                "url": str(response.request.url),
                "status_code": response.status_code,
                "latency_ms": round(latency_ms, 2),
            },
        )
        return response

    def _raise_for_error(self, response: httpx.Response) -> None:
        if response.is_success:
            return
        try:
            payload = response.json()
            message = payload.get("message") or payload.get("error") or f"LaunchDarkly API error {response.status_code}"
        except Exception:
            message = f"LaunchDarkly API error {response.status_code}"
        raise LaunchDarklyAPIError(status_code=response.status_code, message=message)


def get_launchdarkly_client() -> LaunchDarklyClient:
    """Return a singleton LaunchDarkly client."""
    global _ld_client
    if _ld_client is None:
        _ld_client = LaunchDarklyClient()
    return _ld_client

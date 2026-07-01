"""Async Statsig API client for ExperimentIQ.

Uses the config-spec download endpoint (works with Server Secret key, no Pro plan required).
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Final

import httpx


STATSIG_API_BASE_URL: Final[str] = "https://api.statsig.com"
STATSIG_SECRET_ENV_VAR: Final[str] = "STATSIG_SERVER_SECRET"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0
LOGGER_NAME: Final[str] = "experimentiq.statsig"
MISSING_CONFIG_MESSAGE: Final[str] = "STATSIG_SERVER_SECRET must be set."

_statsig_client: StatsigClient | None = None


class StatsigAPIError(Exception):
    """Raised when the Statsig API returns an error response."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def _normalize_experiment(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize a raw Statsig config-spec experiment to the ExperimentIQ schema."""
    is_active = raw.get("isActive", False)
    is_enabled = raw.get("enabled", True)
    if is_active and is_enabled:
        status = "running"
    elif not is_enabled:
        status = "stopped"
    else:
        status = "draft"

    return {
        "id": raw.get("name") or "unknown",
        "name": raw.get("name") or "Untitled experiment",
        "status": status,
        "hypothesis": raw.get("description") or "",
        "dateCreated": None,
        "_source": "statsig",
    }


def _is_experiment(config: dict[str, Any]) -> bool:
    """Return True if a dynamic config entry represents an experiment."""
    if config.get("isUserInExperiment"):
        return True
    entity = config.get("entity", "")
    if isinstance(entity, str) and "experiment" in entity.lower():
        return True
    if config.get("type", "") == "experiment":
        return True
    return False


class StatsigClient:
    """Async client for the Statsig config-spec API."""

    def __init__(self, secret: str | None = None) -> None:
        self._secret = secret or os.getenv(STATSIG_SECRET_ENV_VAR)
        if not self._secret:
            raise ValueError(MISSING_CONFIG_MESSAGE)

        self._logger = logging.getLogger(LOGGER_NAME)
        self._client = httpx.AsyncClient(
            base_url=STATSIG_API_BASE_URL,
            headers={"statsig-api-key": self._secret},
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )

    async def __aenter__(self) -> StatsigClient:
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self.close()

    async def list_experiments(self) -> list[dict[str, Any]]:
        """Return normalized experiments extracted from Statsig config specs."""
        response = await self._request(
            "POST",
            "/v1/download_config_specs",
            json={"sdkKey": self._secret},
        )
        self._raise_for_error(response)
        payload = response.json()

        # Statsig embeds experiments inside dynamic_configs
        dynamic_configs: list[Any] = payload.get("dynamic_configs", [])
        experiments = [c for c in dynamic_configs if isinstance(c, dict) and _is_experiment(c)]
        return [_normalize_experiment(exp) for exp in experiments]

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        started_at = time.perf_counter()
        response = await self._client.request(method, url, **kwargs)
        latency_ms = (time.perf_counter() - started_at) * 1000
        self._logger.debug(
            "Statsig API call",
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
            message = payload.get("message") or payload.get("error") or f"Statsig API error {response.status_code}"
        except Exception:
            message = f"Statsig API error {response.status_code}"
        raise StatsigAPIError(status_code=response.status_code, message=message)


def get_statsig_client() -> StatsigClient:
    """Return a singleton Statsig client."""
    global _statsig_client
    if _statsig_client is None:
        _statsig_client = StatsigClient()
    return _statsig_client

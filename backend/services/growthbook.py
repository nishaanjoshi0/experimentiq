"""Async GrowthBook REST API client for ExperimentIQ."""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Final

import httpx


GROWTHBOOK_API_URL_ENV_VAR: Final[str] = "GROWTHBOOK_API_URL"
GROWTHBOOK_API_KEY_ENV_VAR: Final[str] = "GROWTHBOOK_API_KEY"
AUTHORIZATION_HEADER: Final[str] = "Authorization"
AUTHORIZATION_PREFIX: Final[str] = "Bearer "
DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0
DEFAULT_LIMIT: Final[int] = 20
DEFAULT_OFFSET: Final[int] = 0
EXPERIMENTS_ENDPOINT: Final[str] = "/api/v1/experiments"
METRICS_ENDPOINT: Final[str] = "/api/v1/metrics"
LOGGER_NAME: Final[str] = "experimentiq.growthbook"
NOT_FOUND_STATUS_CODE: Final[int] = 404
NO_CONTENT_STATUS_CODE: Final[int] = 204
SUCCESS_STATUS_CODE: Final[int] = 200
MISSING_CONFIG_MESSAGE: Final[str] = "GROWTHBOOK_API_URL and GROWTHBOOK_API_KEY must be set."
NOT_FOUND_MESSAGE_TEMPLATE: Final[str] = "Experiment not found: {experiment_id}"

_growthbook_client: GrowthBookClient | None = None


class GrowthBookAPIError(Exception):
    """Raised when the GrowthBook API returns an error response."""

    def __init__(self, status_code: int, message: str) -> None:
        """Initialize the API error with an HTTP status code and message."""
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class GrowthBookClient:
    """Async client for interacting with the GrowthBook REST API."""

    def __init__(self) -> None:
        """Initialize the client from environment variables."""
        api_url = os.getenv(GROWTHBOOK_API_URL_ENV_VAR)
        api_key = os.getenv(GROWTHBOOK_API_KEY_ENV_VAR)
        if not api_url or not api_key:
            raise ValueError(MISSING_CONFIG_MESSAGE)

        self._logger = logging.getLogger(LOGGER_NAME)
        self._client = httpx.AsyncClient(
            base_url=api_url.rstrip("/"),
            headers={AUTHORIZATION_HEADER: f"{AUTHORIZATION_PREFIX}{api_key}"},
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )

    async def __aenter__(self) -> GrowthBookClient:
        """Return the client when entering an async context manager."""
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        """Close the underlying HTTP client when exiting an async context manager."""
        await self.close()

    async def list_experiments(
        self,
        limit: int = DEFAULT_LIMIT,
        offset: int = DEFAULT_OFFSET,
    ) -> list[dict[str, Any]]:
        """Return a paginated list of GrowthBook experiments."""
        response = await self._request(
            "GET",
            EXPERIMENTS_ENDPOINT,
            params={"limit": limit, "offset": offset},
        )
        return self._extract_list_payload(response, "experiments")

    async def get_experiment(self, experiment_id: str) -> dict[str, Any]:
        """Return a single experiment by identifier."""
        response = await self._request("GET", f"{EXPERIMENTS_ENDPOINT}/{experiment_id}")
        if response.status_code == NOT_FOUND_STATUS_CODE:
            raise GrowthBookAPIError(
                status_code=NOT_FOUND_STATUS_CODE,
                message=NOT_FOUND_MESSAGE_TEMPLATE.format(experiment_id=experiment_id),
            )
        self._raise_for_error(response)
        return self._extract_dict_payload(response, "experiment")

    async def get_experiment_results(self, experiment_id: str) -> dict[str, Any] | None:
        """Return experiment results when they are available."""
        response = await self._request("GET", f"{EXPERIMENTS_ENDPOINT}/{experiment_id}/results")
        if response.status_code == NO_CONTENT_STATUS_CODE:
            return None
        self._raise_for_error(response)
        return self._extract_dict_payload(response, "results")

    async def list_metrics(self) -> list[dict[str, Any]]:
        """Return the list of configured GrowthBook metrics."""
        response = await self._request("GET", METRICS_ENDPOINT)
        return self._extract_list_payload(response, "metrics")

    async def close(self) -> None:
        """Close the underlying async HTTP client."""
        await self._client.aclose()

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Send an HTTP request to GrowthBook and emit debug logging."""
        started_at = time.perf_counter()
        response = await self._client.request(method, url, **kwargs)
        latency_ms = (time.perf_counter() - started_at) * 1000
        self._logger.debug(
            "GrowthBook API call",
            extra={
                "method": method,
                "url": str(response.request.url),
                "status_code": response.status_code,
                "latency_ms": round(latency_ms, 2),
            },
        )
        return response

    def _raise_for_error(self, response: httpx.Response) -> None:
        """Raise a GrowthBookAPIError when the response is not successful."""
        if response.status_code == SUCCESS_STATUS_CODE:
            return

        message = self._extract_error_message(response)
        raise GrowthBookAPIError(status_code=response.status_code, message=message)

    def _extract_error_message(self, response: httpx.Response) -> str:
        """Extract a useful error message from a GrowthBook response."""
        try:
            payload = response.json()
        except ValueError:
            return f"GrowthBook API request failed with status {response.status_code}."

        if isinstance(payload, dict):
            for key in ("message", "error"):
                value = payload.get(key)
                if isinstance(value, str) and value:
                    return value

        return f"GrowthBook API request failed with status {response.status_code}."

    def _extract_list_payload(self, response: httpx.Response, key: str) -> list[dict[str, Any]]:
        """Return a list payload from a successful GrowthBook response."""
        self._raise_for_error(response)
        payload = response.json()
        if isinstance(payload, dict):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        return []

    def _extract_dict_payload(self, response: httpx.Response, key: str) -> dict[str, Any]:
        """Return a dict payload from a successful GrowthBook response."""
        self._raise_for_error(response)
        payload = response.json()
        if isinstance(payload, dict):
            value = payload.get(key)
            if isinstance(value, dict):
                return value
            return payload
        return {}


def get_growthbook_client() -> GrowthBookClient:
    """Return a singleton GrowthBook client instance."""
    global _growthbook_client
    if _growthbook_client is None:
        _growthbook_client = GrowthBookClient()
    return _growthbook_client

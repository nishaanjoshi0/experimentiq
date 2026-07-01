"""Amplitude HTTP API v2 client for ExperimentIQ.

Pulls event and segmentation data using Basic Auth (API Key + Secret Key)
and normalizes it into an AnalyticsSummary for the opportunity agent.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

import httpx

from services.analytics_ingestion import (
    AnalyticsInsight,
    AnalyticsSummary,
    FunnelStep,
    SegmentRow,
    _compute_delta_pct,
)


LOGGER_NAME = "experimentiq.amplitude"
AMPLITUDE_API_BASE = "https://amplitude.com/api/2"
DEFAULT_LOOKBACK_DAYS = 30


def _date_str(d: date) -> str:
    return d.strftime("%Y%m%d")


async def _get(
    client: httpx.AsyncClient,
    path: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    response = await client.get(f"{AMPLITUDE_API_BASE}{path}", params=params)
    response.raise_for_status()
    return response.json()


def _build_summary_from_payload(
    active_data: dict[str, Any],
    session_data: dict[str, Any] | None,
    platform_data: dict[str, Any] | None,
    source_data: dict[str, Any] | None,
) -> AnalyticsSummary:
    logger = logging.getLogger(LOGGER_NAME)

    end = date.today()
    start = end - timedelta(days=DEFAULT_LOOKBACK_DAYS)

    # Total active users from the event segmentation response
    series = active_data.get("data", {}).get("series", [[]])
    total_active = sum(series[0]) if series and series[0] else 0

    # Session counts if available
    session_series = session_data.get("data", {}).get("series", [[]]) if session_data else [[]]
    total_sessions = sum(session_series[0]) if session_series and session_series[0] else max(total_active, 1)

    # Rough conversion rate from active → session ratio (demo heuristic)
    conversion_rate = round(min(total_active / max(total_sessions, 1), 1.0), 4)

    # Device segments
    device_segments: list[SegmentRow] = []
    if platform_data:
        for segment in platform_data.get("data", {}).get("seriesCollapsed", []):
            name = segment.get("setId", "unknown")
            count = sum(segment.get("values", [0]))
            if count > 0:
                device_segments.append(SegmentRow(
                    segment_type="device",
                    segment_name=name,
                    sessions=count,
                    conversions=int(count * conversion_rate),
                    conversion_rate=conversion_rate,
                ))

    # Source segments
    source_segments: list[SegmentRow] = []
    if source_data:
        for segment in source_data.get("data", {}).get("seriesCollapsed", []):
            name = segment.get("setId", "unknown")
            count = sum(segment.get("values", [0]))
            if count > 0:
                source_segments.append(SegmentRow(
                    segment_type="source",
                    segment_name=name,
                    sessions=count,
                    conversions=int(count * conversion_rate),
                    conversion_rate=conversion_rate,
                ))

    # Build insights
    insights: list[AnalyticsInsight] = []
    if device_segments:
        rates = [s.conversion_rate for s in device_segments]
        avg_rate = sum(rates) / len(rates)
        worst = min(device_segments, key=lambda s: s.conversion_rate)
        delta = _compute_delta_pct(worst.conversion_rate, avg_rate)
        if abs(delta) > 0.05:
            insights.append(AnalyticsInsight(
                category="device",
                description=f"{worst.segment_name} users underperform average by {abs(delta):.0%}",
                metric_value=worst.conversion_rate,
                benchmark=avg_rate,
                delta_pct=delta,
                opportunity_score=min(abs(delta), 1.0),
            ))

    raw_chunks = [
        f"Total active users (last {DEFAULT_LOOKBACK_DAYS}d): {total_active}",
        f"Estimated sessions: {total_sessions}",
        f"Estimated conversion rate: {conversion_rate:.2%}",
        f"Device segments analyzed: {len(device_segments)}",
        f"Source segments analyzed: {len(source_segments)}",
    ]

    logger.info("Amplitude summary built", extra={"total_active": total_active, "insights": len(insights)})

    return AnalyticsSummary(
        overall_conversion_rate=conversion_rate,
        total_sessions=total_sessions,
        total_revenue=0.0,
        currency="USD",
        date_range=f"{start.isoformat()} to {end.isoformat()}",
        funnel_steps=[
            FunnelStep(name="Active Users", users=total_active, drop_off_rate=0.0),
            FunnelStep(name="Sessions", users=total_sessions, drop_off_rate=1 - (total_active / max(total_sessions, 1))),
        ],
        device_segments=device_segments,
        source_segments=source_segments,
        category_segments=[],
        geo_segments=[],
        insights=insights,
        raw_chunks=raw_chunks,
        metadata={"source": "amplitude", "lookback_days": DEFAULT_LOOKBACK_DAYS},
    )


async def build_analytics_summary_from_amplitude(
    api_key: str,
    api_secret: str,
) -> AnalyticsSummary:
    """Pull Amplitude event data and return a normalized AnalyticsSummary."""
    end = date.today()
    start = end - timedelta(days=DEFAULT_LOOKBACK_DAYS)
    start_str = _date_str(start)
    end_str = _date_str(end)

    async with httpx.AsyncClient(auth=(api_key, api_secret), timeout=30.0) as client:
        active_data = await _get(client, "/events/segmentation", {
            "e": '{"event_type":"_active"}',
            "start": start_str,
            "end": end_str,
            "m": "uniques",
        })

        session_data = None
        platform_data = None
        source_data = None

        try:
            session_data = await _get(client, "/events/segmentation", {
                "e": '{"event_type":"_session"}',
                "start": start_str,
                "end": end_str,
                "m": "uniques",
            })
        except Exception:
            pass

        try:
            platform_data = await _get(client, "/events/segmentation", {
                "e": '{"event_type":"_active"}',
                "start": start_str,
                "end": end_str,
                "m": "uniques",
                "s": '[{"prop":"platform","op":"is","values":["iOS","Android","Web"]}]',
                "segmentIndex": 0,
                "g": "platform",
            })
        except Exception:
            pass

        try:
            source_data = await _get(client, "/events/segmentation", {
                "e": '{"event_type":"_active"}',
                "start": start_str,
                "end": end_str,
                "m": "uniques",
                "g": "gp:utm_source",
            })
        except Exception:
            pass

    return _build_summary_from_payload(active_data, session_data, platform_data, source_data)


async def validate_amplitude_credentials(api_key: str, api_secret: str) -> bool:
    """Return True if the credentials are valid (can reach the Amplitude API)."""
    end = date.today()
    start = end - timedelta(days=1)
    async with httpx.AsyncClient(auth=(api_key, api_secret), timeout=10.0) as client:
        resp = await client.get(f"{AMPLITUDE_API_BASE}/events/segmentation", params={
            "e": '{"event_type":"_active"}',
            "start": _date_str(start),
            "end": _date_str(end),
            "m": "uniques",
        })
        return resp.status_code == 200

"""Mixpanel Data Export API client for ExperimentIQ.

Uses Service Account credentials (username + secret) with Basic Auth
to pull event segmentation data and normalize to AnalyticsSummary.
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


LOGGER_NAME = "experimentiq.mixpanel"
MIXPANEL_API_BASE = "https://data.mixpanel.com/api/2.0"
DEFAULT_LOOKBACK_DAYS = 30


def _date_str(d: date) -> str:
    return d.strftime("%Y-%m-%d")


async def _get(
    client: httpx.AsyncClient,
    path: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    response = await client.get(f"{MIXPANEL_API_BASE}{path}", params=params)
    response.raise_for_status()
    return response.json()


def _sum_values(data: dict[str, Any]) -> int:
    """Sum all daily values from a Mixpanel segmentation response."""
    try:
        series = data.get("data", {}).get("values", {})
        if isinstance(series, dict):
            total = 0
            for seg_values in series.values():
                if isinstance(seg_values, dict):
                    total += sum(seg_values.values())
                elif isinstance(seg_values, (int, float)):
                    total += int(seg_values)
            return total
        if isinstance(series, list):
            return sum(series)
    except Exception:
        pass
    return 0


def _extract_segments(data: dict[str, Any], segment_type: str, conversion_rate: float) -> list[SegmentRow]:
    rows: list[SegmentRow] = []
    try:
        series = data.get("data", {}).get("values", {})
        if isinstance(series, dict):
            for name, day_values in series.items():
                if isinstance(day_values, dict):
                    count = sum(day_values.values())
                elif isinstance(day_values, (int, float)):
                    count = int(day_values)
                else:
                    continue
                if count > 0:
                    rows.append(SegmentRow(
                        segment_type=segment_type,
                        segment_name=str(name),
                        sessions=count,
                        conversions=int(count * conversion_rate),
                        conversion_rate=conversion_rate,
                    ))
    except Exception:
        pass
    return rows


async def build_analytics_summary_from_mixpanel(
    username: str,
    secret: str,
    project_id: str = "",
) -> AnalyticsSummary:
    """Pull Mixpanel event data and return a normalized AnalyticsSummary."""
    end = date.today()
    start = end - timedelta(days=DEFAULT_LOOKBACK_DAYS)
    start_str = _date_str(start)
    end_str = _date_str(end)

    base_params: dict[str, Any] = {
        "from_date": start_str,
        "to_date": end_str,
        "unit": "day",
    }
    if project_id:
        base_params["project_id"] = project_id

    async with httpx.AsyncClient(auth=(username, secret), timeout=30.0) as client:
        # Total page views / active events
        pageview_data = await _get(client, "/segmentation", {
            **base_params,
            "event": "$pageview",
            "type": "general",
        })

        total_sessions = _sum_values(pageview_data)
        conversion_rate = 0.03  # conservative default

        device_data: dict[str, Any] = {}
        source_data: dict[str, Any] = {}

        try:
            device_data = await _get(client, "/segmentation", {
                **base_params,
                "event": "$pageview",
                "type": "general",
                "on": "properties[\"$os\"]",
            })
        except Exception:
            pass

        try:
            source_data = await _get(client, "/segmentation", {
                **base_params,
                "event": "$pageview",
                "type": "general",
                "on": "properties[\"utm_source\"]",
            })
        except Exception:
            pass

    device_segments = _extract_segments(device_data, "device", conversion_rate)
    source_segments = _extract_segments(source_data, "source", conversion_rate)

    insights: list[AnalyticsInsight] = []
    if device_segments and len(device_segments) > 1:
        avg_rate = sum(s.conversion_rate for s in device_segments) / len(device_segments)
        worst = min(device_segments, key=lambda s: s.sessions)
        delta = _compute_delta_pct(worst.sessions, sum(s.sessions for s in device_segments) / len(device_segments))
        if abs(delta) > 0.2:
            insights.append(AnalyticsInsight(
                category="device",
                description=f"{worst.segment_name} has significantly fewer pageviews than average ({abs(delta):.0%} gap)",
                metric_value=float(worst.sessions),
                benchmark=float(sum(s.sessions for s in device_segments) / len(device_segments)),
                delta_pct=delta,
                opportunity_score=min(abs(delta), 1.0),
            ))

    raw_chunks = [
        f"Total pageviews (last {DEFAULT_LOOKBACK_DAYS}d): {total_sessions}",
        f"Estimated conversion rate: {conversion_rate:.2%}",
        f"Device OS segments analyzed: {len(device_segments)}",
        f"Source segments analyzed: {len(source_segments)}",
    ]

    logging.getLogger(LOGGER_NAME).info(
        "Mixpanel summary built",
        extra={"total_sessions": total_sessions, "insights": len(insights)},
    )

    return AnalyticsSummary(
        overall_conversion_rate=conversion_rate,
        total_sessions=max(total_sessions, 1),
        total_revenue=0.0,
        currency="USD",
        date_range=f"{start_str} to {end_str}",
        funnel_steps=[
            FunnelStep(name="Pageviews", users=total_sessions, drop_off_rate=0.0),
            FunnelStep(name="Conversions", users=int(total_sessions * conversion_rate), drop_off_rate=1 - conversion_rate),
        ],
        device_segments=device_segments,
        source_segments=source_segments,
        category_segments=[],
        geo_segments=[],
        insights=insights,
        raw_chunks=raw_chunks,
        metadata={"source": "mixpanel", "lookback_days": DEFAULT_LOOKBACK_DAYS},
    )


async def validate_mixpanel_credentials(username: str, secret: str, project_id: str = "") -> bool:
    """Return True if the Mixpanel credentials are valid."""
    end = date.today()
    start = end - timedelta(days=1)
    params: dict[str, Any] = {
        "from_date": _date_str(start),
        "to_date": _date_str(end),
        "event": "$pageview",
        "type": "general",
        "unit": "day",
    }
    if project_id:
        params["project_id"] = project_id
    async with httpx.AsyncClient(auth=(username, secret), timeout=10.0) as client:
        resp = await client.get(f"{MIXPANEL_API_BASE}/segmentation", params=params)
        return resp.status_code == 200

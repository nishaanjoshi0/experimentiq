"""Google Analytics Data API v1 client.

Pulls session and conversion data from a GA4 property using a user's
OAuth access token and normalizes the response into an AnalyticsSummary
for the opportunity agent.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from services.analytics_ingestion import (
    AnalyticsInsight,
    AnalyticsSummary,
    SegmentRow,
    _build_raw_chunks,
    _compute_delta_pct,
)


LOGGER_NAME = "experimentiq.ga4"
GA4_API_BASE = "https://analyticsdata.googleapis.com/v1beta"


async def _run_report(
    access_token: str,
    property_id: str,
    dimensions: list[dict[str, str]],
    metrics: list[dict[str, str]],
    date_range: str = "90daysAgo",
) -> dict[str, Any]:
    url = f"{GA4_API_BASE}/properties/{property_id}:runReport"
    payload: dict[str, Any] = {
        "dateRanges": [{"startDate": date_range, "endDate": "today"}],
        "metrics": metrics,
    }
    if dimensions:
        payload["dimensions"] = dimensions

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        response.raise_for_status()
        return response.json()


def _mv(row: dict[str, Any], idx: int, default: str = "0") -> str:
    try:
        return row["metricValues"][idx]["value"]
    except (IndexError, KeyError):
        return default


def _dv(row: dict[str, Any], idx: int, default: str = "") -> str:
    try:
        return row["dimensionValues"][idx]["value"]
    except (IndexError, KeyError):
        return default


async def build_analytics_summary_from_ga4(
    access_token: str,
    property_id: str,
) -> AnalyticsSummary:
    """Pull GA4 metrics and produce a normalized AnalyticsSummary."""
    logger = logging.getLogger(LOGGER_NAME)

    overall_report, device_report, source_report = await _fetch_all_reports(
        access_token, property_id
    )

    # Overall totals
    overall_rows = overall_report.get("rows", [{}])
    total_sessions = int(_mv(overall_rows[0], 0)) if overall_rows else 0
    total_conversions = int(_mv(overall_rows[0], 1)) if overall_rows else 0
    total_revenue = float(_mv(overall_rows[0], 2)) if overall_rows else 0.0
    overall_cr = total_conversions / total_sessions if total_sessions else 0.0

    # Device segments
    device_segments: list[SegmentRow] = []
    for row in device_report.get("rows", []):
        device = _dv(row, 0) or "unknown"
        sessions = int(_mv(row, 0))
        conversions = int(_mv(row, 1))
        bounce_rate = float(_mv(row, 2)) / 100
        avg_duration = float(_mv(row, 3))
        cr = conversions / sessions if sessions else 0.0
        device_segments.append(
            SegmentRow(
                segment_type="device",
                segment_name=device,
                sessions=sessions,
                conversions=conversions,
                conversion_rate=cr,
                extra={
                    "bounce_rate": bounce_rate,
                    "avg_session_duration_sec": avg_duration,
                },
            )
        )

    # Source segments
    source_segments: list[SegmentRow] = []
    for row in source_report.get("rows", []):
        source = _dv(row, 0) or "unknown"
        sessions = int(_mv(row, 0))
        conversions = int(_mv(row, 1))
        source_segments.append(
            SegmentRow(
                segment_type="source",
                segment_name=source,
                sessions=sessions,
                conversions=conversions,
                conversion_rate=conversions / sessions if sessions else 0.0,
            )
        )

    insights = _extract_insights(device_segments, total_sessions)

    summary = AnalyticsSummary(
        overall_conversion_rate=overall_cr,
        total_sessions=total_sessions,
        total_revenue=total_revenue,
        currency="USD",
        date_range="Last 90 days (GA4 live)",
        funnel_steps=[],
        device_segments=device_segments,
        source_segments=source_segments,
        category_segments=[],
        geo_segments=[],
        insights=insights,
        raw_chunks=[],
        metadata={"source": "ga4_live", "property_id": property_id},
    )
    summary.raw_chunks = _build_raw_chunks(summary)

    logger.info(
        "GA4 summary built",
        extra={"property_id": property_id, "total_sessions": total_sessions},
    )
    return summary


async def _fetch_all_reports(
    access_token: str, property_id: str
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    overall = await _run_report(
        access_token,
        property_id,
        dimensions=[],
        metrics=[
            {"name": "sessions"},
            {"name": "conversions"},
            {"name": "totalRevenue"},
        ],
    )
    device = await _run_report(
        access_token,
        property_id,
        dimensions=[{"name": "deviceCategory"}],
        metrics=[
            {"name": "sessions"},
            {"name": "conversions"},
            {"name": "bounceRate"},
            {"name": "averageSessionDuration"},
        ],
    )
    source = await _run_report(
        access_token,
        property_id,
        dimensions=[{"name": "sessionDefaultChannelGroup"}],
        metrics=[
            {"name": "sessions"},
            {"name": "conversions"},
        ],
    )
    return overall, device, source


def _extract_insights(
    device_segments: list[SegmentRow], total_sessions: int
) -> list[AnalyticsInsight]:
    insights: list[AnalyticsInsight] = []
    device_map = {d.segment_name.lower(): d for d in device_segments}
    desktop = device_map.get("desktop")
    mobile = device_map.get("mobile")

    if desktop and mobile and desktop.conversion_rate > 0:
        gap = _compute_delta_pct(mobile.conversion_rate, desktop.conversion_rate)
        mobile_share = mobile.sessions / total_sessions if total_sessions else 0
        insights.append(
            AnalyticsInsight(
                category="device_gap",
                description=(
                    f"Mobile conversion rate ({mobile.conversion_rate:.1%}) is "
                    f"{abs(gap):.0%} lower than desktop ({desktop.conversion_rate:.1%}). "
                    f"Mobile accounts for {mobile_share:.0%} of all sessions."
                ),
                metric_value=mobile.conversion_rate,
                benchmark=desktop.conversion_rate,
                delta_pct=gap,
                opportunity_score=min(1.0, abs(gap) * 0.5 + 0.3),
            )
        )

    if mobile:
        bounce = mobile.extra.get("bounce_rate", 0)
        duration = mobile.extra.get("avg_session_duration_sec", 0)
        insights.append(
            AnalyticsInsight(
                category="mobile_engagement",
                description=(
                    f"Mobile bounce rate: {bounce:.0%}. "
                    f"Avg mobile session duration: {duration:.0f}s. "
                    "Low engagement on mobile suggests UX or page speed issues."
                ),
                metric_value=bounce,
                benchmark=0.50,
                delta_pct=_compute_delta_pct(bounce, 0.50),
                opportunity_score=0.70,
            )
        )

    return insights

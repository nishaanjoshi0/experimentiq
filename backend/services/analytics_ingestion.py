"""Analytics data ingestion and normalization for the opportunity discovery agent.

Accepts either raw CSV data (GA4-compatible export format) or the built-in
Google Merchandise Store demo dataset, and produces a normalized AnalyticsSummary
that the opportunity agent can reason over.
"""

from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass, field
from typing import Any

from data.google_merch_demo import get_demo_dataset


LOGGER_NAME = "experimentiq.analytics_ingestion"


@dataclass
class FunnelStep:
    name: str
    users: int
    drop_off_rate: float


@dataclass
class SegmentRow:
    segment_type: str
    segment_name: str
    sessions: int
    conversions: int
    conversion_rate: float
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class AnalyticsInsight:
    """A single observation extracted from the data that hints at an experiment opportunity."""
    category: str
    description: str
    metric_value: float
    benchmark: float
    delta_pct: float
    opportunity_score: float  # 0–1, higher = stronger signal


@dataclass
class AnalyticsSummary:
    """Normalized analytics summary used as input to the opportunity agent."""
    overall_conversion_rate: float
    total_sessions: int
    total_revenue: float
    currency: str
    date_range: str
    funnel_steps: list[FunnelStep]
    device_segments: list[SegmentRow]
    source_segments: list[SegmentRow]
    category_segments: list[SegmentRow]
    geo_segments: list[SegmentRow]
    insights: list[AnalyticsInsight]
    raw_chunks: list[str]
    metadata: dict[str, Any]


def _compute_delta_pct(value: float, benchmark: float) -> float:
    if benchmark == 0:
        return 0.0
    return (value - benchmark) / benchmark


def _funnel_from_demo(demo_steps: list[dict[str, Any]]) -> list[FunnelStep]:
    return [
        FunnelStep(
            name=s["step"],
            users=s["users"],
            drop_off_rate=s["drop_off_rate"],
        )
        for s in demo_steps
    ]


def _device_segments_from_demo(devices: list[dict[str, Any]]) -> list[SegmentRow]:
    return [
        SegmentRow(
            segment_type="device",
            segment_name=d["device_category"],
            sessions=d["sessions"],
            conversions=d["conversions"],
            conversion_rate=d["conversion_rate"],
            extra={
                "bounce_rate": d["bounce_rate"],
                "avg_session_duration_sec": d["avg_session_duration_sec"],
                "revenue": d["revenue"],
            },
        )
        for d in devices
    ]


def _source_segments_from_demo(sources: list[dict[str, Any]]) -> list[SegmentRow]:
    return [
        SegmentRow(
            segment_type="source",
            segment_name=s["source_medium"],
            sessions=s["sessions"],
            conversions=s["conversions"],
            conversion_rate=s["conversion_rate"],
            extra={"revenue": s["revenue"]},
        )
        for s in sources
    ]


def _category_segments_from_demo(categories: list[dict[str, Any]]) -> list[SegmentRow]:
    return [
        SegmentRow(
            segment_type="category",
            segment_name=c["category"],
            sessions=c["product_views"],
            conversions=c["purchases"],
            conversion_rate=c["purchases"] / c["product_views"] if c["product_views"] else 0,
            extra={
                "cart_to_purchase_rate": c["cart_to_purchase_rate"],
                "revenue": c["revenue"],
                "add_to_cart": c["add_to_cart"],
            },
        )
        for c in categories
    ]


def _geo_segments_from_demo(geo: list[dict[str, Any]]) -> list[SegmentRow]:
    return [
        SegmentRow(
            segment_type="geography",
            segment_name=g["country"],
            sessions=g["sessions"],
            conversions=g["conversions"],
            conversion_rate=g["conversion_rate"],
            extra={"revenue": g["revenue"]},
        )
        for g in geo
    ]


def _extract_insights_from_demo(demo: dict[str, Any]) -> list[AnalyticsInsight]:
    insights: list[AnalyticsInsight] = []
    overall_cr = demo["metadata"]["overall_conversion_rate"]

    # Mobile vs desktop conversion gap
    devices = {d["device_category"]: d for d in demo["sessions_by_device"]}
    desktop_cr = devices["desktop"]["conversion_rate"]
    mobile_cr = devices["mobile"]["conversion_rate"]
    gap_pct = _compute_delta_pct(mobile_cr, desktop_cr)
    insights.append(AnalyticsInsight(
        category="device_gap",
        description=(
            f"Mobile conversion rate ({mobile_cr:.1%}) is {abs(gap_pct):.0%} lower than "
            f"desktop ({desktop_cr:.1%}). Mobile represents "
            f"{devices['mobile']['sessions'] / demo['metadata']['total_sessions']:.0%} of sessions."
        ),
        metric_value=mobile_cr,
        benchmark=desktop_cr,
        delta_pct=gap_pct,
        opportunity_score=min(1.0, abs(gap_pct) * 0.5 + 0.4),
    ))

    # Mobile page speed
    page_speed = demo["page_speed"]
    mobile_lcp = page_speed["lcp_mobile_sec"]
    insights.append(AnalyticsInsight(
        category="page_speed",
        description=(
            f"Mobile LCP is {mobile_lcp:.1f}s (poor, threshold is 2.5s). "
            f"{page_speed['sessions_with_slow_mobile_pct']:.0%} of mobile sessions experience slow load times. "
            f"Mobile avg page load: {page_speed['avg_page_load_mobile_sec']}s vs desktop {page_speed['avg_page_load_desktop_sec']}s."
        ),
        metric_value=mobile_lcp,
        benchmark=2.5,
        delta_pct=_compute_delta_pct(mobile_lcp, 2.5),
        opportunity_score=0.85,
    ))

    # Cart abandonment
    cart = demo["cart_abandonment"]
    funnel = demo["funnel_steps"]
    checkout_step = next((s for s in funnel if s["step"] == "begin_checkout"), None)
    product_view_step = next((s for s in funnel if s["step"] == "product_view"), None)
    cart_step = next((s for s in funnel if s["step"] == "add_to_cart"), None)
    if checkout_step and cart_step:
        checkout_drop = 1 - (checkout_step["users"] / cart_step["users"]) if cart_step["users"] else 0
        insights.append(AnalyticsInsight(
            category="cart_abandonment",
            description=(
                f"Cart abandonment rate is {cart['overall_cart_abandonment_rate']:.1%} overall. "
                f"Mobile cart abandonment ({cart['mobile_cart_abandonment_rate']:.1%}) is "
                f"{_compute_delta_pct(cart['mobile_cart_abandonment_rate'], cart['desktop_cart_abandonment_rate']):.0%} "
                f"higher than desktop ({cart['desktop_cart_abandonment_rate']:.1%}). "
                f"{checkout_drop:.0%} of users who add to cart abandon at the checkout step."
            ),
            metric_value=cart["overall_cart_abandonment_rate"],
            benchmark=0.70,
            delta_pct=_compute_delta_pct(cart["overall_cart_abandonment_rate"], 0.70),
            opportunity_score=0.82,
        ))

    # Product view to cart drop
    if product_view_step and cart_step:
        view_to_cart = cart_step["users"] / product_view_step["users"] if product_view_step["users"] else 0
        insights.append(AnalyticsInsight(
            category="product_page",
            description=(
                f"Only {view_to_cart:.1%} of product view sessions result in an add-to-cart. "
                f"Of {product_view_step['users']:,} users viewing products, only "
                f"{cart_step['users']:,} add to cart."
            ),
            metric_value=view_to_cart,
            benchmark=0.45,
            delta_pct=_compute_delta_pct(view_to_cart, 0.45),
            opportunity_score=0.72,
        ))

    # Site search uplift
    search = demo["search_data"]
    search_uplift = _compute_delta_pct(search["search_conversion_rate"], search["non_search_conversion_rate"])
    insights.append(AnalyticsInsight(
        category="site_search",
        description=(
            f"Users who use site search convert at {search['search_conversion_rate']:.1%} vs "
            f"{search['non_search_conversion_rate']:.1%} for non-search users — "
            f"a {search_uplift:.0%} lift. Only {search['site_search_usage_rate']:.0%} of sessions "
            f"use site search. Zero-results rate: {search['search_zero_results_rate']:.0%}."
        ),
        metric_value=search["search_conversion_rate"],
        benchmark=search["non_search_conversion_rate"],
        delta_pct=search_uplift,
        opportunity_score=0.78,
    ))

    # Returning users
    ret = demo["returning_users"]
    ret_uplift = _compute_delta_pct(ret["returning_user_conversion_rate"], ret["new_user_conversion_rate"])
    insights.append(AnalyticsInsight(
        category="user_retention",
        description=(
            f"Returning users convert at {ret['returning_user_conversion_rate']:.1%} vs "
            f"{ret['new_user_conversion_rate']:.1%} for new users ({ret_uplift:.0%} difference). "
            f"Returning users are only {ret['returning_user_pct']:.0%} of the user base. "
            f"Email subscribers convert at {ret['email_subscriber_conversion_rate']:.1%}."
        ),
        metric_value=ret["returning_user_conversion_rate"],
        benchmark=ret["new_user_conversion_rate"],
        delta_pct=ret_uplift,
        opportunity_score=0.68,
    ))

    # Mobile bounce rate
    mobile_bounce = devices["mobile"]["bounce_rate"]
    desktop_bounce = devices["desktop"]["bounce_rate"]
    insights.append(AnalyticsInsight(
        category="engagement",
        description=(
            f"Mobile bounce rate is {mobile_bounce:.0%} vs desktop {desktop_bounce:.0%}. "
            f"Mobile avg session duration is {devices['mobile']['avg_session_duration_sec']}s "
            f"vs {devices['desktop']['avg_session_duration_sec']}s on desktop."
        ),
        metric_value=mobile_bounce,
        benchmark=desktop_bounce,
        delta_pct=_compute_delta_pct(mobile_bounce, desktop_bounce),
        opportunity_score=0.65,
    ))

    return sorted(insights, key=lambda x: x.opportunity_score, reverse=True)


def _build_raw_chunks(summary: AnalyticsSummary) -> list[str]:
    """Build text chunks for vector store indexing."""
    chunks = []

    chunks.append(
        f"Overall performance: {summary.total_sessions:,} sessions, "
        f"{summary.overall_conversion_rate:.1%} conversion rate, "
        f"${summary.total_revenue:,.0f} revenue. Period: {summary.date_range}."
    )

    for device in summary.device_segments:
        chunks.append(
            f"Device segment {device.segment_name}: {device.sessions:,} sessions, "
            f"{device.conversion_rate:.1%} conversion rate. "
            f"Bounce rate: {device.extra.get('bounce_rate', 'n/a'):.0%}. "
            f"Avg session: {device.extra.get('avg_session_duration_sec', 'n/a')}s."
        )

    funnel_text = " → ".join(
        f"{s.name} ({s.users:,} users, {s.drop_off_rate:.0%} drop-off)"
        for s in summary.funnel_steps
    )
    chunks.append(f"Conversion funnel: {funnel_text}")

    for insight in summary.insights:
        chunks.append(f"Insight [{insight.category}]: {insight.description}")

    for source in summary.source_segments:
        chunks.append(
            f"Traffic source {source.segment_name}: {source.sessions:,} sessions, "
            f"{source.conversion_rate:.1%} conversion."
        )

    for cat in summary.category_segments:
        chunks.append(
            f"Product category {cat.segment_name}: {cat.sessions:,} views, "
            f"{cat.conversion_rate:.1%} purchase rate, "
            f"${cat.extra.get('revenue', 0):,.0f} revenue."
        )

    return chunks


def ingest_demo() -> AnalyticsSummary:
    """Ingest the built-in Google Merchandise Store demo dataset."""
    demo = get_demo_dataset()
    meta = demo["metadata"]

    funnel_steps = _funnel_from_demo(demo["funnel_steps"])
    device_segments = _device_segments_from_demo(demo["sessions_by_device"])
    source_segments = _source_segments_from_demo(demo["traffic_sources"])
    category_segments = _category_segments_from_demo(demo["top_categories"])
    geo_segments = _geo_segments_from_demo(demo["geography"])
    insights = _extract_insights_from_demo(demo)

    summary = AnalyticsSummary(
        overall_conversion_rate=meta["overall_conversion_rate"],
        total_sessions=meta["total_sessions"],
        total_revenue=meta["total_revenue"],
        currency=meta["currency"],
        date_range=meta["date_range"],
        funnel_steps=funnel_steps,
        device_segments=device_segments,
        source_segments=source_segments,
        category_segments=category_segments,
        geo_segments=geo_segments,
        insights=insights,
        raw_chunks=[],
        metadata=meta,
    )
    summary.raw_chunks = _build_raw_chunks(summary)
    return summary


def _parse_csv_rows(csv_content: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(csv_content.strip()))
    return list(reader)


def _safe_float(val: str | None, default: float = 0.0) -> float:
    try:
        return float(str(val).replace(",", "").replace("%", "")) if val else default
    except ValueError:
        return default


def _safe_int(val: str | None, default: int = 0) -> int:
    try:
        return int(str(val).replace(",", "")) if val else default
    except ValueError:
        return default


def ingest_csv(csv_content: str, company_description: str = "") -> AnalyticsSummary:
    """Ingest a GA4-style CSV export and produce a normalized AnalyticsSummary.

    Expected CSV columns (case-insensitive, extras ignored):
      device_category, sessions, users, conversions, conversion_rate, bounce_rate,
      avg_session_duration_sec, revenue

    Falls back to demo dataset on parse failure.
    """
    logger = logging.getLogger(LOGGER_NAME)
    try:
        rows = _parse_csv_rows(csv_content)
        if not rows:
            logger.warning("Empty CSV, falling back to demo dataset")
            return ingest_demo()

        headers_lower = {k.lower().strip() for k in rows[0].keys()}
        required = {"sessions", "conversions"}
        if not required.issubset(headers_lower):
            logger.warning("CSV missing required columns, falling back to demo")
            return ingest_demo()

        def get(row: dict[str, str], *keys: str) -> str | None:
            for k in keys:
                for rk, rv in row.items():
                    if rk.lower().strip() == k:
                        return rv
            return None

        device_segments: list[SegmentRow] = []
        total_sessions = 0
        total_conversions = 0
        total_revenue = 0.0

        for row in rows:
            sessions = _safe_int(get(row, "sessions"))
            conversions = _safe_int(get(row, "conversions"))
            cr_raw = _safe_float(get(row, "conversion_rate"))
            cr = cr_raw / 100 if cr_raw > 1 else cr_raw
            revenue = _safe_float(get(row, "revenue"))
            device = get(row, "device_category", "device") or "unknown"

            total_sessions += sessions
            total_conversions += conversions
            total_revenue += revenue

            device_segments.append(SegmentRow(
                segment_type="device",
                segment_name=device,
                sessions=sessions,
                conversions=conversions,
                conversion_rate=cr or (conversions / sessions if sessions else 0),
                extra={
                    "bounce_rate": _safe_float(get(row, "bounce_rate")) / 100,
                    "avg_session_duration_sec": _safe_int(get(row, "avg_session_duration_sec")),
                    "revenue": revenue,
                },
            ))

        overall_cr = total_conversions / total_sessions if total_sessions else 0

        summary = AnalyticsSummary(
            overall_conversion_rate=overall_cr,
            total_sessions=total_sessions,
            total_revenue=total_revenue,
            currency="USD",
            date_range="uploaded data",
            funnel_steps=[],
            device_segments=device_segments,
            source_segments=[],
            category_segments=[],
            geo_segments=[],
            insights=[],
            raw_chunks=[],
            metadata={"source": "csv_upload", "company_description": company_description},
        )
        summary.raw_chunks = _build_raw_chunks(summary)
        return summary

    except Exception as exc:
        logger.warning("CSV ingestion failed: %s. Falling back to demo.", exc)
        return ingest_demo()

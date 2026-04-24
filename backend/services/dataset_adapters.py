"""Dataset-specific adapters that normalize uploaded CSVs into AnalyticsSummary.

Each adapter recognizes its dataset by column headers and produces a normalized
AnalyticsSummary that the opportunity agent can reason over without knowing
which dataset it came from.
"""

from __future__ import annotations

import csv
import io
from typing import Any

from services.analytics_ingestion import (
    AnalyticsInsight,
    AnalyticsSummary,
    FunnelStep,
    SegmentRow,
    _build_raw_chunks,
    _compute_delta_pct,
    ingest_csv,
    ingest_demo,
)


DATASET_REGISTRY: list[dict[str, Any]] = [
    {
        "id": "google_merch",
        "name": "Google Merchandise Store",
        "description": (
            "Real GA4 e-commerce data from Google's public demo account. "
            "50K+ sessions with device segments, funnel steps, and revenue."
        ),
        "size": "~2 MB",
        "use_case": "E-commerce conversion optimization",
        "download_url": "https://analytics.google.com/analytics/web/demoAccount",
        "download_instructions": (
            "Request access to the Google Analytics demo account. "
            "Then export a device-level session report as CSV from GA4 → Reports → Acquisition."
        ),
        "columns_hint": "device_category, sessions, conversions, bounce_rate, revenue",
        "industry": "e-commerce",
    },
    {
        "id": "olist",
        "name": "Olist Brazilian E-Commerce",
        "description": (
            "100K orders from a Brazilian marketplace with order status, "
            "delivery data, customer geography, and product categories."
        ),
        "size": "~43 MB",
        "use_case": "Marketplace growth and retention",
        "download_url": "https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce",
        "download_instructions": (
            "Download olist_orders_dataset.csv from Kaggle. "
            "Upload that file here."
        ),
        "columns_hint": "order_id, customer_id, order_status, customer_state",
        "industry": "marketplace",
    },
    {
        "id": "instacart",
        "name": "Instacart Market Basket",
        "description": (
            "3M+ order-product rows with reorder signals, cart position, "
            "and product affinity data."
        ),
        "size": "~1.2 GB",
        "use_case": "Engagement and reorder optimization",
        "download_url": "https://www.kaggle.com/datasets/psparks/instacart-market-basket-analysis",
        "download_instructions": (
            "Download order_products__prior.csv from Kaggle. "
            "Upload that file here."
        ),
        "columns_hint": "order_id, product_id, add_to_cart_order, reordered",
        "industry": "grocery",
    },
    {
        "id": "telco_churn",
        "name": "Telco Customer Churn",
        "description": (
            "7K customer records with subscription type, tenure, monthly charges, "
            "and churn labels by segment."
        ),
        "size": "~1 MB",
        "use_case": "Retention and churn reduction",
        "download_url": "https://www.kaggle.com/datasets/blastchar/telco-customer-churn",
        "download_instructions": (
            "Download WA_Fn-UseC_-Telco-Customer-Churn.csv from Kaggle. "
            "Upload that file here."
        ),
        "columns_hint": "customerID, Churn, Contract, tenure, MonthlyCharges",
        "industry": "saas/subscription",
    },
]

_COLUMN_SIGNATURES: dict[str, set[str]] = {
    "olist": {"order_id", "customer_id", "order_status"},
    "instacart": {"order_id", "product_id", "reordered"},
    "telco_churn": {"customerid", "churn", "contract"},
    "google_merch": {"device_category", "sessions", "conversions"},
}


def detect_dataset_type(csv_content: str) -> str | None:
    try:
        reader = csv.DictReader(io.StringIO(csv_content[:4000]))
        headers = {(k or "").lower().strip() for k in (reader.fieldnames or [])}
        for dataset_id, sig in _COLUMN_SIGNATURES.items():
            if sig.issubset(headers):
                return dataset_id
    except Exception:
        pass
    return None


def _parse_csv(content: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(content.strip()))
    return list(reader)


def _sf(val: Any, default: float = 0.0) -> float:
    try:
        return float(str(val).replace(",", "").replace("%", "")) if val else default
    except (ValueError, TypeError):
        return default


def _si(val: Any, default: int = 0) -> int:
    try:
        return int(str(val).replace(",", "")) if val else default
    except (ValueError, TypeError):
        return default


# ---------------------------------------------------------------------------
# Olist adapter
# ---------------------------------------------------------------------------

def _adapt_olist(rows: list[dict[str, str]]) -> AnalyticsSummary:
    total = len(rows)
    delivered = sum(1 for r in rows if r.get("order_status", "").lower() == "delivered")
    cancelled = sum(1 for r in rows if r.get("order_status", "").lower() in ("canceled", "cancelled"))
    cancel_rate = cancelled / total if total else 0.0
    delivery_rate = delivered / total if total else 0.0

    state_map: dict[str, dict[str, int]] = {}
    for row in rows:
        state = row.get("customer_state", "unknown")
        if state not in state_map:
            state_map[state] = {"total": 0, "delivered": 0}
        state_map[state]["total"] += 1
        if row.get("order_status", "").lower() == "delivered":
            state_map[state]["delivered"] += 1

    geo_segments = [
        SegmentRow(
            segment_type="geography",
            segment_name=state,
            sessions=c["total"],
            conversions=c["delivered"],
            conversion_rate=c["delivered"] / c["total"] if c["total"] else 0.0,
        )
        for state, c in sorted(state_map.items(), key=lambda x: -x[1]["total"])[:10]
    ]

    insights = [
        AnalyticsInsight(
            category="order_completion",
            description=(
                f"Order delivery rate is {delivery_rate:.1%} across {total:,} orders. "
                f"Cancellation rate is {cancel_rate:.1%}. "
                "Reducing cancellations through better product descriptions or delivery estimates "
                "would directly lift completion rate."
            ),
            metric_value=delivery_rate,
            benchmark=0.92,
            delta_pct=_compute_delta_pct(delivery_rate, 0.92),
            opportunity_score=0.82,
        ),
        AnalyticsInsight(
            category="cancellation",
            description=(
                f"{cancel_rate:.1%} of orders are cancelled before delivery. "
                "Checkout experience, payment friction, or estimated delivery accuracy "
                "are the most common causes."
            ),
            metric_value=cancel_rate,
            benchmark=0.03,
            delta_pct=_compute_delta_pct(cancel_rate, 0.03),
            opportunity_score=0.76,
        ),
    ]

    summary = AnalyticsSummary(
        overall_conversion_rate=delivery_rate,
        total_sessions=total,
        total_revenue=0.0,
        currency="BRL",
        date_range="full dataset",
        funnel_steps=[
            FunnelStep("order_placed", total, 0.0),
            FunnelStep("delivered", delivered, 1 - delivery_rate),
        ],
        device_segments=[],
        source_segments=[],
        category_segments=[],
        geo_segments=geo_segments,
        insights=insights,
        raw_chunks=[],
        metadata={"source": "olist", "industry": "marketplace"},
    )
    summary.raw_chunks = _build_raw_chunks(summary)
    return summary


# ---------------------------------------------------------------------------
# Instacart adapter
# ---------------------------------------------------------------------------

def _adapt_instacart(rows: list[dict[str, str]]) -> AnalyticsSummary:
    total = len(rows)
    reordered = sum(1 for r in rows if _si(r.get("reordered")) == 1)
    reorder_rate = reordered / total if total else 0.0

    cart_positions = [_si(r.get("add_to_cart_order")) for r in rows if r.get("add_to_cart_order")]
    avg_cart_pos = sum(cart_positions) / len(cart_positions) if cart_positions else 0.0
    late_add_pct = sum(1 for p in cart_positions if p > 10) / len(cart_positions) if cart_positions else 0.0

    insights = [
        AnalyticsInsight(
            category="reorder_rate",
            description=(
                f"Reorder rate is {reorder_rate:.1%} — {reordered:,} of {total:,} items "
                "are reorders. Strong reorder signal indicates retention but may mean "
                "new product discovery is low."
            ),
            metric_value=reorder_rate,
            benchmark=0.59,
            delta_pct=_compute_delta_pct(reorder_rate, 0.59),
            opportunity_score=0.78,
        ),
        AnalyticsInsight(
            category="cart_discovery",
            description=(
                f"Avg add-to-cart position is {avg_cart_pos:.1f}. "
                f"{late_add_pct:.0%} of items are added after position 10, "
                "suggesting weak product discovery for long-tail items."
            ),
            metric_value=avg_cart_pos,
            benchmark=5.0,
            delta_pct=0.0,
            opportunity_score=0.65,
        ),
    ]

    summary = AnalyticsSummary(
        overall_conversion_rate=reorder_rate,
        total_sessions=total,
        total_revenue=0.0,
        currency="USD",
        date_range="full dataset",
        funnel_steps=[
            FunnelStep("item_added_to_cart", total, 0.0),
            FunnelStep("reordered_item", reordered, 1 - reorder_rate),
        ],
        device_segments=[],
        source_segments=[],
        category_segments=[],
        geo_segments=[],
        insights=insights,
        raw_chunks=[],
        metadata={"source": "instacart", "industry": "grocery"},
    )
    summary.raw_chunks = _build_raw_chunks(summary)
    return summary


# ---------------------------------------------------------------------------
# Telco Churn adapter
# ---------------------------------------------------------------------------

def _adapt_telco(rows: list[dict[str, str]]) -> AnalyticsSummary:
    total = len(rows)
    churned = sum(1 for r in rows if r.get("Churn", "").lower() == "yes")
    churn_rate = churned / total if total else 0.0
    retain_rate = 1 - churn_rate

    contract_map: dict[str, dict[str, int]] = {}
    for row in rows:
        contract = row.get("Contract", "unknown")
        if contract not in contract_map:
            contract_map[contract] = {"total": 0, "churned": 0}
        contract_map[contract]["total"] += 1
        if row.get("Churn", "").lower() == "yes":
            contract_map[contract]["churned"] += 1

    segments = [
        SegmentRow(
            segment_type="contract",
            segment_name=contract,
            sessions=c["total"],
            conversions=c["total"] - c["churned"],
            conversion_rate=1 - (c["churned"] / c["total"]) if c["total"] else 0.0,
            extra={"churn_rate": c["churned"] / c["total"] if c["total"] else 0.0},
        )
        for contract, c in contract_map.items()
    ]

    tenures = [_sf(r.get("tenure")) for r in rows if r.get("tenure")]
    avg_tenure = sum(tenures) / len(tenures) if tenures else 0.0
    charges = [_sf(r.get("MonthlyCharges")) for r in rows if r.get("MonthlyCharges")]
    avg_charge = sum(charges) / len(charges) if charges else 0.0

    mtm_churn = 0.0
    if "Month-to-month" in contract_map:
        c = contract_map["Month-to-month"]
        mtm_churn = c["churned"] / c["total"] if c["total"] else 0.0

    insights = [
        AnalyticsInsight(
            category="churn_rate",
            description=(
                f"Overall churn rate is {churn_rate:.1%}. "
                f"Month-to-month customers churn at {mtm_churn:.1%}. "
                f"Avg tenure: {avg_tenure:.0f} months, avg monthly charge: ${avg_charge:.2f}."
            ),
            metric_value=churn_rate,
            benchmark=0.05,
            delta_pct=_compute_delta_pct(churn_rate, 0.05),
            opportunity_score=0.88,
        ),
        AnalyticsInsight(
            category="contract_upgrade",
            description=(
                f"Month-to-month churn ({mtm_churn:.1%}) is significantly higher than "
                "annual contract churn. Contract upgrade incentive tests could "
                "materially reduce overall churn rate."
            ),
            metric_value=mtm_churn,
            benchmark=0.05,
            delta_pct=_compute_delta_pct(mtm_churn, 0.05),
            opportunity_score=0.85,
        ),
    ]

    summary = AnalyticsSummary(
        overall_conversion_rate=retain_rate,
        total_sessions=total,
        total_revenue=0.0,
        currency="USD",
        date_range="full dataset",
        funnel_steps=[
            FunnelStep("active_customers", total, 0.0),
            FunnelStep("retained", total - churned, churn_rate),
        ],
        device_segments=segments,
        source_segments=[],
        category_segments=[],
        geo_segments=[],
        insights=insights,
        raw_chunks=[],
        metadata={"source": "telco_churn", "industry": "saas/subscription"},
    )
    summary.raw_chunks = _build_raw_chunks(summary)
    return summary


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def adapt_dataset(
    csv_content: str,
    dataset_type: str | None = None,
) -> AnalyticsSummary:
    """Detect dataset type and run the appropriate adapter.

    Falls back to generic CSV ingestion, then demo data on failure.
    """
    detected = dataset_type or detect_dataset_type(csv_content)
    rows = _parse_csv(csv_content)

    if not rows:
        return ingest_demo()

    if detected == "olist":
        return _adapt_olist(rows)
    if detected == "instacart":
        return _adapt_instacart(rows)
    if detected == "telco_churn":
        return _adapt_telco(rows)

    return ingest_csv(csv_content)

"""Google Merchandise Store demo dataset in GA4-normalized format.

Mirrors the publicly available Google Analytics demo account data shape.
Used when data_source="demo" so the opportunity agent has realistic behavioral
data to reason over without requiring real GA4 credentials.
"""

from __future__ import annotations

from typing import Any

DEMO_SESSIONS_BY_DEVICE: list[dict[str, Any]] = [
    {"device_category": "desktop", "sessions": 22400, "users": 18200, "new_users": 12300,
     "bounces": 9856, "bounce_rate": 0.44, "avg_session_duration_sec": 214,
     "conversions": 851, "conversion_rate": 0.038, "revenue": 72835.0},
    {"device_category": "mobile", "sessions": 24100, "users": 20800, "new_users": 16500,
     "bounces": 16387, "bounce_rate": 0.68, "avg_session_duration_sec": 98,
     "conversions": 289, "conversion_rate": 0.012, "revenue": 18124.0},
    {"device_category": "tablet", "sessions": 3900, "users": 3200, "new_users": 2100,
     "bounces": 1638, "bounce_rate": 0.42, "avg_session_duration_sec": 187,
     "conversions": 82, "conversion_rate": 0.021, "revenue": 6724.0},
]

DEMO_FUNNEL_STEPS: list[dict[str, Any]] = [
    {"step": "session_start",   "users": 50400, "drop_off_rate": 0.0},
    {"step": "product_view",    "users": 28224, "drop_off_rate": 0.44},
    {"step": "add_to_cart",     "users": 9879,  "drop_off_rate": 0.65},
    {"step": "begin_checkout",  "users": 2175,  "drop_off_rate": 0.78},
    {"step": "purchase",        "users": 1222,  "drop_off_rate": 0.44},
]

DEMO_FUNNEL_BY_DEVICE: list[dict[str, Any]] = [
    {"device_category": "desktop",
     "steps": [
         {"step": "session_start",  "users": 22400},
         {"step": "product_view",   "users": 14784},
         {"step": "add_to_cart",    "users": 5913},
         {"step": "begin_checkout", "users": 1478},
         {"step": "purchase",       "users": 851},
     ]},
    {"device_category": "mobile",
     "steps": [
         {"step": "session_start",  "users": 24100},
         {"step": "product_view",   "users": 11568},
         {"step": "add_to_cart",    "users": 3470},
         {"step": "begin_checkout", "users": 578},
         {"step": "purchase",       "users": 289},
     ]},
    {"device_category": "tablet",
     "steps": [
         {"step": "session_start",  "users": 3900},
         {"step": "product_view",   "users": 2184},
         {"step": "add_to_cart",    "users": 699},
         {"step": "begin_checkout", "users": 167},
         {"step": "purchase",       "users": 82},
     ]},
]

DEMO_TRAFFIC_SOURCES: list[dict[str, Any]] = [
    {"source_medium": "google / organic",    "sessions": 17640, "conversions": 534, "conversion_rate": 0.030, "revenue": 43250.0},
    {"source_medium": "google / cpc",        "sessions": 14112, "conversions": 395, "conversion_rate": 0.028, "revenue": 32100.0},
    {"source_medium": "(direct) / (none)",   "sessions": 11088, "conversions": 222, "conversion_rate": 0.020, "revenue": 16890.0},
    {"source_medium": "youtube.com / referral", "sessions": 4032, "conversions": 36,  "conversion_rate": 0.009, "revenue": 2940.0},
    {"source_medium": "facebook / social",   "sessions": 2520, "conversions": 25,  "conversion_rate": 0.010, "revenue": 1820.0},
    {"source_medium": "email / newsletter",  "sessions": 1008, "conversions": 10,  "conversion_rate": 0.010, "revenue": 683.0},
]

DEMO_TOP_CATEGORIES: list[dict[str, Any]] = [
    {"category": "Apparel",     "product_views": 9856,  "add_to_cart": 2957,  "purchases": 442, "revenue": 28080.0, "cart_to_purchase_rate": 0.149},
    {"category": "Drinkware",   "product_views": 6272,  "add_to_cart": 2196,  "purchases": 372, "revenue": 14148.0, "cart_to_purchase_rate": 0.169},
    {"category": "Electronics", "product_views": 5040,  "add_to_cart": 756,   "purchases": 114, "revenue": 27360.0, "cart_to_purchase_rate": 0.151},
    {"category": "Office",      "product_views": 3528,  "add_to_cart": 882,   "purchases": 166, "revenue": 9960.0,  "cart_to_purchase_rate": 0.188},
    {"category": "YouTube",     "product_views": 2520,  "add_to_cart": 882,   "purchases": 128, "revenue": 7296.0,  "cart_to_purchase_rate": 0.145},
]

DEMO_GEOGRAPHY: list[dict[str, Any]] = [
    {"country": "United States", "sessions": 21168, "conversions": 587, "conversion_rate": 0.028, "revenue": 47683.0},
    {"country": "United Kingdom","sessions": 7560,  "conversions": 168, "conversion_rate": 0.022, "revenue": 12474.0},
    {"country": "Germany",       "sessions": 6048,  "conversions": 109, "conversion_rate": 0.018, "revenue": 8178.0},
    {"country": "Canada",        "sessions": 5040,  "conversions": 121, "conversion_rate": 0.024, "revenue": 9074.0},
    {"country": "Australia",     "sessions": 4032,  "conversions": 81,  "conversion_rate": 0.020, "revenue": 5913.0},
    {"country": "Other",         "sessions": 6552,  "conversions": 156, "conversion_rate": 0.024, "revenue": 14361.0},
]

DEMO_MONTHLY_TRENDS: list[dict[str, Any]] = [
    {"month": "2024-01", "sessions": 16128, "conversions": 371, "conversion_rate": 0.023, "revenue": 30452.0},
    {"month": "2024-02", "sessions": 16632, "conversions": 408, "conversion_rate": 0.025, "revenue": 33456.0},
    {"month": "2024-03", "sessions": 17640, "conversions": 443, "conversion_rate": 0.025, "revenue": 33775.0},
]

DEMO_CART_ABANDONMENT: dict[str, Any] = {
    "overall_cart_abandonment_rate": 0.876,
    "desktop_cart_abandonment_rate": 0.856,
    "mobile_cart_abandonment_rate": 0.917,
    "tablet_cart_abandonment_rate": 0.883,
    "top_abandonment_page": "begin_checkout",
    "abandonment_at_checkout_rate": 0.438,
}

DEMO_SEARCH_DATA: dict[str, Any] = {
    "site_search_usage_rate": 0.14,
    "search_conversion_rate": 0.048,
    "non_search_conversion_rate": 0.021,
    "top_search_terms": ["mug", "hoodie", "shirt", "hat", "bottle"],
    "search_zero_results_rate": 0.11,
}

DEMO_PAGE_SPEED: dict[str, Any] = {
    "avg_page_load_desktop_sec": 2.1,
    "avg_page_load_mobile_sec": 4.8,
    "lcp_mobile_sec": 5.2,
    "cls_mobile": 0.18,
    "sessions_with_slow_mobile_pct": 0.41,
}

DEMO_RETURNING_USERS: dict[str, Any] = {
    "returning_user_conversion_rate": 0.062,
    "new_user_conversion_rate": 0.014,
    "returning_user_pct": 0.32,
    "email_subscriber_conversion_rate": 0.071,
}

DEMO_METADATA: dict[str, Any] = {
    "source": "Google Merchandise Store (demo)",
    "date_range": "2024-01-01 to 2024-03-31",
    "total_sessions": 50400,
    "total_users": 42200,
    "total_conversions": 1222,
    "total_revenue": 97683.0,
    "overall_conversion_rate": 0.024,
    "currency": "USD",
    "industry": "e-commerce",
    "product_type": "branded merchandise",
}


def get_demo_dataset() -> dict[str, Any]:
    """Return the full Google Merchandise Store demo dataset."""
    return {
        "metadata": DEMO_METADATA,
        "sessions_by_device": DEMO_SESSIONS_BY_DEVICE,
        "funnel_steps": DEMO_FUNNEL_STEPS,
        "funnel_by_device": DEMO_FUNNEL_BY_DEVICE,
        "traffic_sources": DEMO_TRAFFIC_SOURCES,
        "top_categories": DEMO_TOP_CATEGORIES,
        "geography": DEMO_GEOGRAPHY,
        "monthly_trends": DEMO_MONTHLY_TRENDS,
        "cart_abandonment": DEMO_CART_ABANDONMENT,
        "search_data": DEMO_SEARCH_DATA,
        "page_speed": DEMO_PAGE_SPEED,
        "returning_users": DEMO_RETURNING_USERS,
    }

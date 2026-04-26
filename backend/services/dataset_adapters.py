"""Dataset registry — UI metadata for pre-built datasets with download links."""

from __future__ import annotations

from typing import Any


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

"""Universal CSV ingestion via Claude.

Replaces per-dataset adapters. Sends a CSV sample to Claude, which extracts
a normalized AnalyticsSummary regardless of column schema.
"""

from __future__ import annotations

import csv
import io
import json
import os
from typing import Any

from anthropic import AsyncAnthropic
from dotenv import load_dotenv

from services.analytics_ingestion import (
    AnalyticsInsight,
    AnalyticsSummary,
    FunnelStep,
    SegmentRow,
    _build_raw_chunks,
)

load_dotenv()

_SAMPLE_ROWS = 80
_MAX_TOKENS = 2048

_SCHEMA = {
    "dataset_type": "short label, e.g. 'e-commerce', 'subscription/churn', 'marketplace', 'grocery'",
    "total_records": "int — total number of rows",
    "key_metric_name": "what the primary conversion/success metric is for this dataset",
    "overall_conversion_rate": "float 0–1 representing the primary success rate across all records",
    "total_revenue": "float, 0 if not present",
    "currency": "ISO currency code or 'USD'",
    "date_range": "inferred date range string, or 'full dataset'",
    "funnel_steps": [
        {"name": "stage name", "users": "int", "drop_off_rate": "float 0–1"}
    ],
    "segments": [
        {
            "type": "e.g. device | contract | category | geography | source",
            "name": "segment label",
            "sessions": "int record count",
            "conversion_rate": "float 0–1",
        }
    ],
    "insights": [
        {
            "category": "short slug, e.g. churn_rate | device_gap | cart_abandonment",
            "description": "1–2 sentence finding with specific numbers from the data",
            "metric_value": "float — the key number",
            "benchmark": "float — a reasonable industry benchmark or dataset average to compare against",
            "opportunity_score": "float 0–1 — how strong an experiment signal this is",
        }
    ],
}

_SYSTEM = (
    "You are a senior growth analyst. Given a CSV sample you extract a structured "
    "analytics summary. Be specific and quantitative — use actual numbers from the data."
)


def _sample_csv(csv_content: str) -> tuple[list[str], list[dict[str, str]]]:
    reader = csv.DictReader(io.StringIO(csv_content.strip()))
    rows = list(reader)
    headers = reader.fieldnames or []
    return list(headers), rows[:_SAMPLE_ROWS]


def _build_prompt(headers: list[str], rows: list[dict[str, str]], total_rows: int) -> str:
    sample_text = "\n".join(
        ",".join(str(r.get(h, "")) for h in headers)
        for r in rows[:20]
    )
    return (
        f"Dataset: {total_rows:,} total rows.\n"
        f"Columns: {', '.join(headers)}\n\n"
        f"First 20 rows sample:\n{headers[0] if headers else ''},{','.join(headers[1:])}\n{sample_text}\n\n"
        f"Analyze the full column list and sample to extract a structured analytics summary.\n"
        f"Return JSON only matching this schema:\n{json.dumps(_SCHEMA, indent=2)}\n\n"
        "Rules:\n"
        "- overall_conversion_rate: infer the primary success rate (e.g. delivery rate, retention rate, purchase rate)\n"
        "- funnel_steps: 2–4 logical stages with user counts and drop-off\n"
        "- segments: up to 6 meaningful breakdowns from the data columns\n"
        "- insights: 3–5 specific findings with numbers, each a strong experiment signal\n"
        "- Return JSON only. No markdown fences."
    )


def _parse_response(data: dict[str, Any], total_rows: int) -> AnalyticsSummary:
    funnel_steps = [
        FunnelStep(
            name=s.get("name", "step"),
            users=int(s.get("users", 0)),
            drop_off_rate=float(s.get("drop_off_rate", 0.0)),
        )
        for s in data.get("funnel_steps", [])
    ]

    segments = [
        SegmentRow(
            segment_type=s.get("type", "segment"),
            segment_name=s.get("name", "unknown"),
            sessions=int(s.get("sessions", 0)),
            conversions=int(s.get("sessions", 0) * float(s.get("conversion_rate", 0))),
            conversion_rate=float(s.get("conversion_rate", 0.0)),
        )
        for s in data.get("segments", [])
    ]

    insights = [
        AnalyticsInsight(
            category=ins.get("category", "insight"),
            description=ins.get("description", ""),
            metric_value=float(ins.get("metric_value", 0.0)),
            benchmark=float(ins.get("benchmark", 0.0)),
            delta_pct=(
                (float(ins.get("metric_value", 0)) - float(ins.get("benchmark", 0)))
                / float(ins.get("benchmark", 1))
                if float(ins.get("benchmark", 0)) != 0 else 0.0
            ),
            opportunity_score=min(1.0, max(0.0, float(ins.get("opportunity_score", 0.5)))),
        )
        for ins in data.get("insights", [])
    ]

    summary = AnalyticsSummary(
        overall_conversion_rate=float(data.get("overall_conversion_rate", 0.0)),
        total_sessions=int(data.get("total_records", total_rows)),
        total_revenue=float(data.get("total_revenue", 0.0)),
        currency=str(data.get("currency", "USD")),
        date_range=str(data.get("date_range", "full dataset")),
        funnel_steps=funnel_steps,
        device_segments=segments,
        source_segments=[],
        category_segments=[],
        geo_segments=[],
        insights=insights,
        raw_chunks=[],
        metadata={
            "source": "csv_upload",
            "dataset_type": data.get("dataset_type", "unknown"),
            "key_metric": data.get("key_metric_name", "conversion"),
        },
    )
    summary.raw_chunks = _build_raw_chunks(summary)
    return summary


async def ingest_csv_universal(
    csv_content: str,
    company_description: str = "",
) -> AnalyticsSummary:
    """Send any CSV to Claude and get back a normalized AnalyticsSummary."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY must be set.")

    headers, sample_rows = _sample_csv(csv_content)
    all_rows = list(csv.DictReader(io.StringIO(csv_content.strip())))
    total_rows = len(all_rows)

    if not headers or total_rows == 0:
        raise ValueError("CSV appears to be empty or has no headers.")

    prompt = _build_prompt(headers, sample_rows, total_rows)
    if company_description:
        prompt = f"Company context: {company_description}\n\n{prompt}"

    client = AsyncAnthropic(api_key=api_key)
    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=_MAX_TOKENS,
        system=_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )

    text = next(
        (block.text for block in response.content if getattr(block, "type", "") == "text"),
        "",
    ).strip()

    # Strip markdown fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    data = json.loads(text)
    return _parse_response(data, total_rows)

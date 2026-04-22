"""LangGraph monitoring agent for ExperimentIQ experiment health checks."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Final, TypedDict

from anthropic import AsyncAnthropic
from dotenv import load_dotenv
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from services.bigquery import BigQueryService, BigQueryServiceError, get_bigquery_service
from services.growthbook import GrowthBookAPIError, GrowthBookClient, get_growthbook_client
from services.stats import (
    DataQualityResult,
    NoveltyResult,
    SRMResult,
    SequentialTestResult,
    StatsService,
    get_stats_service,
)


LOGGER_NAME: Final[str] = "experimentiq.monitoring_agent"
MODEL_NAME: Final[str] = "claude-sonnet-4-5-20250929"
MAX_TOKENS: Final[int] = 4000
SYSTEM_PROMPT: Final[str] = "You are an expert experimentation analyst. Be direct, specific, and actionable."
ANTHROPIC_API_KEY_ENV_VAR: Final[str] = "ANTHROPIC_API_KEY"
HEALTHY_STATUS: Final[str] = "healthy"
WARNING_STATUS: Final[str] = "warning"
CRITICAL_STATUS: Final[str] = "critical"
STOP_ABANDON_RECOMMENDATION: Final[str] = "stop_abandon"
DEFAULT_CONFIDENCE: Final[float] = 0.0
DEFAULT_SUMMARY: Final[str] = "Monitoring report could not be generated."
SYNTHESIS_FAILURE_SUMMARY: Final[str] = "Stat checks completed, but the monitoring summary could not be synthesized."
FETCH_FAILURE_SUMMARY: Final[str] = "Monitoring failed because experiment data could not be fetched."

load_dotenv()

_anthropic_client: AsyncAnthropic | None = None


class MonitoringReport(BaseModel):
    """Structured monitoring report returned by the monitoring agent."""

    experiment_id: str
    health_status: str
    srm_check: SRMResult | None
    data_quality: DataQualityResult | None
    sequential_test: SequentialTestResult | None
    novelty_check: NoveltyResult | None
    summary: str
    suggested_actions: list[str]
    confidence: float = Field(ge=0.0, le=1.0)


class MonitoringState(TypedDict):
    """State carried across monitoring graph nodes."""

    experiment_id: str
    experiment_metadata: dict[str, Any]
    events: list[dict[str, Any]]
    metric_observations: list[dict[str, Any]]
    variation_counts: dict[str, int]
    srm_result: SRMResult | None
    data_quality_result: DataQualityResult | None
    sequential_test_result: SequentialTestResult | None
    novelty_result: NoveltyResult | None
    summary: str
    suggested_actions: list[str]
    messages: list[str]
    fetch_failed: bool
    report: MonitoringReport | None


def get_anthropic_client() -> AsyncAnthropic:
    """Return a singleton Anthropic client configured from the environment."""
    global _anthropic_client
    if _anthropic_client is None:
        api_key = os.getenv(ANTHROPIC_API_KEY_ENV_VAR)
        if not api_key:
            raise ValueError(f"{ANTHROPIC_API_KEY_ENV_VAR} must be set.")
        _anthropic_client = AsyncAnthropic(api_key=api_key)
    return _anthropic_client


async def call_claude(prompt: str) -> str:
    """Send a single stateless request to Claude and return text content."""
    client = get_anthropic_client()
    response = await client.messages.create(
        model=MODEL_NAME,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    text_blocks = [block.text for block in response.content if getattr(block, "type", "") == "text"]
    return "\n".join(text_blocks).strip()


def append_message(state: MonitoringState, label: str, content: str) -> list[str]:
    """Append a labeled step result to the graph message list."""
    return [*state["messages"], f"{label}: {content}"]


def strip_markdown_fences(text: str) -> str:
    """Strip markdown code fences from a JSON response."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:] if lines[0].startswith("```") else lines
        lines = lines[:-1] if lines and lines[-1].strip() == "```" else lines
        text = "\n".join(lines)
    return text.strip()


def safe_timestamp(value: Any) -> datetime | None:
    """Convert a supported timestamp value into a timezone-aware datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, str):
        try:
            normalized = value.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            return None
    return None


def safe_event_date(value: Any) -> datetime | None:
    """Convert an event date value into a UTC datetime at midnight."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return safe_timestamp(value)
    if hasattr(value, "year") and hasattr(value, "month") and hasattr(value, "day"):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def get_expected_splits(metadata: dict[str, Any], variation_counts: dict[str, int]) -> dict[str, float]:
    """Build expected traffic splits from experiment metadata or fall back to equal allocation."""
    variations = metadata.get("variations")
    if isinstance(variations, list):
        extracted: dict[str, float] = {}
        for item in variations:
            if not isinstance(item, dict):
                continue
            variation_id = item.get("variation_id") or item.get("id") or item.get("key")
            traffic_split = item.get("traffic_split") or item.get("weight")
            if variation_id is not None and traffic_split is not None:
                extracted[str(variation_id)] = float(traffic_split)
        if extracted and set(extracted.keys()) == set(variation_counts.keys()):
            total = sum(extracted.values())
            if total > 0:
                return {key: value / total for key, value in extracted.items()}

    variation_count = len(variation_counts)
    if variation_count == 0:
        return {}
    equal_split = 1.0 / variation_count
    return {variation_id: equal_split for variation_id in variation_counts}


def get_primary_metric_id(metadata: dict[str, Any]) -> str | None:
    """Extract a primary metric identifier from experiment metadata when available."""
    for key in ("primary_metric_id", "metric_id", "primaryMetricId"):
        value = metadata.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def get_experiment_status(metadata: dict[str, Any]) -> str | None:
    """Extract experiment status from metadata using common GrowthBook field variants."""
    for key in ("status", "phase", "experimentStatus"):
        value = metadata.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def build_critical_report(experiment_id: str, summary: str, suggested_actions: list[str]) -> MonitoringReport:
    """Build a critical monitoring report for fetch or synthesis failures."""
    return MonitoringReport(
        experiment_id=experiment_id,
        health_status=CRITICAL_STATUS,
        srm_check=None,
        data_quality=None,
        sequential_test=None,
        novelty_check=None,
        summary=summary,
        suggested_actions=suggested_actions,
        confidence=DEFAULT_CONFIDENCE,
    )


async def fetch_data(state: MonitoringState) -> dict[str, Any]:
    """Fetch experiment metadata, events, metrics, and variation counts for monitoring."""
    bigquery_service: BigQueryService = get_bigquery_service()
    growthbook_client: GrowthBookClient = get_growthbook_client()
    experiment_metadata: dict[str, Any] = {}

    try:
        experiment_metadata = await growthbook_client.get_experiment(state["experiment_id"])
    except GrowthBookAPIError as error:
        if error.status_code != 404:
            logging.getLogger(LOGGER_NAME).warning(
                "Monitoring metadata fetch failed",
                extra={"experiment_id_hash": hashlib.sha256(state["experiment_id"].encode("utf-8")).hexdigest()},
            )
            experiment_metadata = {}

    try:
        metric_id = get_primary_metric_id(experiment_metadata)
        events = await bigquery_service.get_experiment_events(state["experiment_id"])
        metric_observations = await bigquery_service.get_metric_observations(
            state["experiment_id"],
            metric_id=metric_id,
        )
        variation_counts = await bigquery_service.get_variation_user_counts(state["experiment_id"])
    except (BigQueryServiceError, ValueError) as error:
        logging.getLogger(LOGGER_NAME).warning(
            "Monitoring fetch failed",
            extra={"experiment_id_hash": hashlib.sha256(state["experiment_id"].encode("utf-8")).hexdigest()},
        )
        report = build_critical_report(
            experiment_id=state["experiment_id"],
            summary=FETCH_FAILURE_SUMMARY,
            suggested_actions=[
                "Verify GrowthBook connectivity and experiment ID correctness.",
                "Confirm BigQuery tables and dbt marts are populated for this experiment.",
                f"Retry monitoring after resolving the fetch error: {error}",
            ],
        )
        return {
            "fetch_failed": True,
            "report": report,
            "summary": report.summary,
            "suggested_actions": report.suggested_actions,
            "messages": append_message(state, "fetch_data", "fetch_failed"),
        }

    return {
        "experiment_metadata": experiment_metadata,
        "events": events,
        "metric_observations": metric_observations,
        "variation_counts": variation_counts,
        "fetch_failed": False,
        "messages": append_message(
            state,
            "fetch_data",
            f"events={len(events)}, metric_observations={len(metric_observations)}, variations={len(variation_counts)}",
        ),
    }


async def run_stat_checks(state: MonitoringState) -> dict[str, Any]:
    """Run SRM and data quality checks on the fetched monitoring inputs."""
    stats_service: StatsService = get_stats_service()
    if not state["events"]:
        data_quality_result = DataQualityResult(
            passed=False,
            checks={
                "minimum_sample_size": False,
                "data_freshness": False,
                "minimum_runtime": False,
            },
            failure_reasons=["No experiment events were found for this experiment."],
        )
        return {
            "srm_result": None,
            "data_quality_result": data_quality_result,
            "messages": append_message(state, "run_stat_checks", "no_events"),
        }

    expected_splits = get_expected_splits(state["experiment_metadata"], state["variation_counts"])
    srm_result = None
    if expected_splits and set(expected_splits.keys()) == set(state["variation_counts"].keys()):
        srm_result = stats_service.check_srm(state["variation_counts"], expected_splits)

    event_timestamps = [
        timestamp
        for timestamp in (safe_timestamp(event.get("timestamp")) for event in state["events"])
        if timestamp is not None
    ]
    if not event_timestamps:
        data_quality_result = DataQualityResult(
            passed=False,
            checks={
                "minimum_sample_size": False,
                "data_freshness": False,
                "minimum_runtime": False,
            },
            failure_reasons=["Experiment events are missing usable timestamps."],
        )
        return {
            "srm_result": srm_result,
            "data_quality_result": data_quality_result,
            "messages": append_message(state, "run_stat_checks", "invalid_timestamps"),
        }
    last_event_timestamp = max(event_timestamps)
    started_at = safe_timestamp(state["experiment_metadata"].get("startedAt"))
    if started_at is None:
        event_dates = [
            event_date
            for event_date in (safe_event_date(event.get("event_date")) for event in state["events"])
            if event_date is not None
        ]
        if not event_dates:
            data_quality_result = DataQualityResult(
                passed=False,
                checks={
                    "minimum_sample_size": False,
                    "data_freshness": False,
                    "minimum_runtime": False,
                },
                failure_reasons=["Experiment events are missing usable event dates."],
            )
            return {
                "srm_result": srm_result,
                "data_quality_result": data_quality_result,
                "messages": append_message(state, "run_stat_checks", "invalid_event_dates"),
            }
        started_at = min(event_dates)

    variation_values = list(state["variation_counts"].values())
    control_count = variation_values[0] if len(variation_values) >= 1 else 0
    treatment_count = variation_values[1] if len(variation_values) >= 2 else 0
    experiment_status = (
        get_experiment_status(state["experiment_metadata"])
        if isinstance(state["experiment_metadata"], dict)
        else None
    ) or "stopped"
    data_quality_result = stats_service.run_data_quality_gate(
        experiment_id=state["experiment_id"],
        control_count=control_count,
        treatment_count=treatment_count,
        experiment_start_timestamp=started_at,
        last_event_timestamp=last_event_timestamp,
        experiment_status=experiment_status,
    )
    return {
        "srm_result": srm_result,
        "data_quality_result": data_quality_result,
        "messages": append_message(state, "run_stat_checks", "completed"),
    }


async def run_sequential_test(state: MonitoringState) -> dict[str, Any]:
    """Run sequential testing when data quality checks pass."""
    data_quality_result = state["data_quality_result"]
    if data_quality_result is None or not data_quality_result.passed:
        return {
            "sequential_test_result": None,
            "messages": append_message(state, "run_sequential_test", "skipped"),
        }

    variation_ids = list(state["variation_counts"].keys())
    if len(variation_ids) < 2:
        return {
            "sequential_test_result": None,
            "messages": append_message(state, "run_sequential_test", "insufficient_variations"),
        }

    stats_service: StatsService = get_stats_service()
    control_id, treatment_id = variation_ids[0], variation_ids[1]
    control_values = [
        float(row["value"])
        for row in state["metric_observations"]
        if str(row.get("variation_id")) == str(control_id) and row.get("value") is not None
    ]
    treatment_values = [
        float(row["value"])
        for row in state["metric_observations"]
        if str(row.get("variation_id")) == str(treatment_id) and row.get("value") is not None
    ]
    if len(control_values) < 2 or len(treatment_values) < 2:
        return {
            "sequential_test_result": None,
            "messages": append_message(state, "run_sequential_test", "insufficient_metric_values"),
        }

    sequential_test_result = stats_service.run_sequential_test(control_values, treatment_values)
    return {
        "sequential_test_result": sequential_test_result,
        "messages": append_message(state, "run_sequential_test", sequential_test_result.recommendation),
    }


async def run_novelty_check(state: MonitoringState) -> dict[str, Any]:
    """Run novelty detection on daily conversion rates when data quality passes."""
    data_quality_result = state["data_quality_result"]
    if data_quality_result is None or not data_quality_result.passed:
        return {
            "novelty_result": None,
            "messages": append_message(state, "run_novelty_check", "skipped"),
        }

    bigquery_service: BigQueryService = get_bigquery_service()
    stats_service: StatsService = get_stats_service()
    metric_id = get_primary_metric_id(state["experiment_metadata"])
    daily_rates = await bigquery_service.get_daily_metric_rates(state["experiment_id"], metric_id=metric_id)
    variation_ids = list(state["variation_counts"].keys())
    if len(variation_ids) < 2:
        return {
            "novelty_result": None,
            "messages": append_message(state, "run_novelty_check", "insufficient_variations"),
        }

    control_rates = daily_rates.get(variation_ids[0], [])
    treatment_rates = daily_rates.get(variation_ids[1], [])
    if not control_rates or not treatment_rates:
        return {
            "novelty_result": None,
            "messages": append_message(state, "run_novelty_check", "missing_daily_rates"),
        }

    novelty_result = stats_service.check_novelty(treatment_rates, control_rates)
    return {
        "novelty_result": novelty_result,
        "messages": append_message(state, "run_novelty_check", novelty_result.message),
    }


def build_synthesis_prompt(state: MonitoringState) -> str:
    """Build the Claude prompt for summary and action synthesis."""
    srm_payload = asdict(state["srm_result"]) if state["srm_result"] is not None else None
    data_quality_payload = (
        asdict(state["data_quality_result"]) if state["data_quality_result"] is not None else None
    )
    sequential_payload = (
        asdict(state["sequential_test_result"]) if state["sequential_test_result"] is not None else None
    )
    novelty_payload = asdict(state["novelty_result"]) if state["novelty_result"] is not None else None
    prompt_payload = {
        "experiment_id": state["experiment_id"],
        "variation_counts": state["variation_counts"],
        "srm_check": srm_payload,
        "data_quality": data_quality_payload,
        "sequential_test": sequential_payload,
        "novelty_check": novelty_payload,
    }
    return (
        "Analyze the monitoring results below. Produce plain English summary text and a JSON array of suggested "
        "actions.\n"
        "Return JSON only with this schema: "
        '{"summary": "string", "suggested_actions": ["string"]}\n'
        f"{json.dumps(prompt_payload)}"
    )


async def synthesize_report(state: MonitoringState) -> dict[str, Any]:
    """Use Claude to summarize monitoring results and propose next actions."""
    if state["fetch_failed"]:
        return {}

    prompt = build_synthesis_prompt(state)
    last_error = "Unable to parse Claude response."
    for _ in range(2):
        response_text = await call_claude(prompt)
        try:
            payload = json.loads(strip_markdown_fences(response_text))
            summary = payload["summary"]
            suggested_actions = payload["suggested_actions"]
            if not isinstance(summary, str):
                raise ValueError("summary must be a string")
            if not isinstance(suggested_actions, list) or not all(
                isinstance(item, str) for item in suggested_actions
            ):
                raise ValueError("suggested_actions must be a JSON array of strings")
            return {
                "summary": summary,
                "suggested_actions": suggested_actions,
                "messages": append_message(state, "synthesize_report", "completed"),
            }
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            last_error = str(error)

    return {
        "summary": SYNTHESIS_FAILURE_SUMMARY,
        "suggested_actions": [
            "Review SRM, data quality, and sequential test outputs directly.",
            f"Retry monitoring summary synthesis after resolving the Claude response issue: {last_error}",
        ],
        "messages": append_message(state, "synthesize_report", "fallback"),
    }


def determine_health_status(state: MonitoringState) -> str:
    """Determine the final monitoring health status from computed checks."""
    if state["fetch_failed"]:
        return CRITICAL_STATUS

    if state["data_quality_result"] is not None and not state["data_quality_result"].passed:
        return CRITICAL_STATUS

    if state["srm_result"] is not None and state["srm_result"].has_srm:
        return WARNING_STATUS

    if state["novelty_result"] is not None and state["novelty_result"].has_novelty:
        return WARNING_STATUS

    sequential_test_result = state["sequential_test_result"]
    if sequential_test_result is not None and sequential_test_result.recommendation == STOP_ABANDON_RECOMMENDATION:
        return WARNING_STATUS

    return HEALTHY_STATUS

def determine_confidence(state: MonitoringState) -> float:
    """Estimate confidence in the monitoring report based on data completeness."""
    if state["fetch_failed"]:
        return 0.0

    confidence = 0.6
    if state["data_quality_result"] is not None and state["data_quality_result"].passed:
        confidence += 0.2
    if state["srm_result"] is not None:
        confidence += 0.1
    if state["sequential_test_result"] is not None:
        confidence += 0.1
    return min(confidence, 1.0)


async def build_report(state: MonitoringState) -> dict[str, Any]:
    """Assemble the final monitoring report from graph state."""
    if state["report"] is not None:
        return {"report": state["report"]}

    report = MonitoringReport(
        experiment_id=state["experiment_id"],
        health_status=determine_health_status(state),
        srm_check=state["srm_result"],
        data_quality=state["data_quality_result"],
        sequential_test=state["sequential_test_result"],
        novelty_check=state["novelty_result"],
        summary=state["summary"] or DEFAULT_SUMMARY,
        suggested_actions=state["suggested_actions"],
        confidence=determine_confidence(state),
    )
    return {
        "report": report,
        "messages": append_message(state, "build_report", report.health_status),
    }


def route_after_fetch(state: MonitoringState) -> str:
    """Route directly to report building on fetch failure, or continue analysis otherwise."""
    return "build_report" if state["fetch_failed"] else "run_stat_checks"


def compile_monitoring_graph() -> Any:
    """Build and compile the monitoring StateGraph."""
    graph = StateGraph(MonitoringState)
    graph.add_node("fetch_data", fetch_data)
    graph.add_node("run_stat_checks", run_stat_checks)
    graph.add_node("run_sequential_test", run_sequential_test)
    graph.add_node("run_novelty_check", run_novelty_check)
    graph.add_node("synthesize_report", synthesize_report)
    graph.add_node("build_report", build_report)

    graph.set_entry_point("fetch_data")
    graph.add_conditional_edges(
        "fetch_data",
        route_after_fetch,
        {
            "run_stat_checks": "run_stat_checks",
            "build_report": "build_report",
        },
    )
    graph.add_edge("run_stat_checks", "run_sequential_test")
    graph.add_edge("run_sequential_test", "run_novelty_check")
    graph.add_edge("run_novelty_check", "synthesize_report")
    graph.add_edge("synthesize_report", "build_report")
    graph.add_edge("build_report", END)
    return graph.compile()


async def run_monitoring_agent(experiment_id: str) -> MonitoringReport:
    """Run the monitoring agent graph and return a structured monitoring report."""
    graph = compile_monitoring_graph()
    initial_state: MonitoringState = {
        "experiment_id": experiment_id,
        "experiment_metadata": {},
        "events": [],
        "metric_observations": [],
        "variation_counts": {},
        "srm_result": None,
        "data_quality_result": None,
        "sequential_test_result": None,
        "novelty_result": None,
        "summary": "",
        "suggested_actions": [],
        "messages": [],
        "fetch_failed": False,
        "report": None,
    }
    result = await graph.ainvoke(initial_state)
    report = result["report"]
    if report is None:
        return build_critical_report(
            experiment_id=experiment_id,
            summary=DEFAULT_SUMMARY,
            suggested_actions=["Retry monitoring after verifying service health and dependencies."],
        )
    return report

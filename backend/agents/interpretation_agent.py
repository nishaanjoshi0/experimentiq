"""LangGraph interpretation agent for ExperimentIQ experiment recommendations."""

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
from pydantic import BaseModel, Field, ValidationError

from services.bigquery import BigQueryServiceError, get_bigquery_service
from services.growthbook import GrowthBookAPIError, get_growthbook_client
from services.stats import BasicStatsResult, get_stats_service


LOGGER_NAME: Final[str] = "experimentiq.interpretation_agent"
MODEL_NAME: Final[str] = "claude-sonnet-4-5-20250929"
MAX_TOKENS: Final[int] = 4000
SYSTEM_PROMPT: Final[str] = (
    "You are an expert experimentation analyst at a growth-stage tech company. "
    "You make clear, defensible decisions based on statistical evidence and business context."
)
ANTHROPIC_API_KEY_ENV_VAR: Final[str] = "ANTHROPIC_API_KEY"
SHIP_DECISION: Final[str] = "ship"
ITERATE_DECISION: Final[str] = "iterate"
ABANDON_DECISION: Final[str] = "abandon"
DEFAULT_PRIMARY_SUMMARY: Final[str] = "Primary metric results were unavailable."
DEFAULT_GUARDRAIL_SUMMARY: Final[str] = "Guardrail metric results were unavailable."
FETCH_FAILURE_REASONING: Final[str] = "Interpretation could not fetch the required experiment data."
PARSE_FAILURE_REASONING: Final[str] = "Interpretation could not parse a valid recommendation from the model."
INVALID_DATA_QUALITY_REASONING: Final[str] = (
    "Data quality checks did not pass, so the recommendation is forced to iterate until data issues are resolved."
)

load_dotenv()

_anthropic_client: AsyncAnthropic | None = None


class Recommendation(BaseModel):
    """Structured experiment recommendation returned by the interpretation agent."""

    experiment_id: str
    decision: str
    confidence: float = Field(ge=0.0, le=1.0)
    primary_metric_summary: str
    guardrail_summary: str
    reasoning: str
    follow_up_cuts: list[str]
    risks: list[str]
    data_quality_passed: bool
    created_at: datetime


class InterpretationState(TypedDict):
    """State carried across the interpretation graph."""

    experiment_id: str
    experiment_results: dict[str, Any]
    health: dict[str, Any]
    metric_observations: list[dict[str, Any]]
    primary_metric_id: str | None
    guardrail_metric_ids: list[str]
    guardrail_metric_results: list[dict[str, Any]]
    basic_stats: BasicStatsResult | None
    cuped_applied: bool
    guardrail_flags: list[str]
    data_quality_passed: bool
    decision: str
    confidence: float
    primary_metric_summary: str
    guardrail_summary: str
    reasoning: str
    follow_up_cuts: list[str]
    risks: list[str]
    messages: list[str]
    fetch_failed: bool
    recommendation: Recommendation | None


class RecommendationPayload(BaseModel):
    """Claude-generated recommendation payload before final assembly."""

    decision: str
    confidence: float = Field(ge=0.0, le=1.0)
    primary_metric_summary: str
    guardrail_summary: str
    reasoning: str
    follow_up_cuts: list[str]
    risks: list[str]


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


def append_message(state: InterpretationState, label: str, content: str) -> list[str]:
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


def utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


def build_fallback_recommendation(
    experiment_id: str,
    reasoning: str,
    data_quality_passed: bool,
) -> Recommendation:
    """Build a safe fallback recommendation."""
    return Recommendation(
        experiment_id=experiment_id,
        decision=ITERATE_DECISION,
        confidence=0.0,
        primary_metric_summary=DEFAULT_PRIMARY_SUMMARY,
        guardrail_summary=DEFAULT_GUARDRAIL_SUMMARY,
        reasoning=reasoning,
        follow_up_cuts=["Review raw experiment data and rerun the interpretation flow."],
        risks=["Acting without a reliable interpretation may lead to a poor product decision."],
        data_quality_passed=data_quality_passed,
        created_at=utc_now(),
    )


def extract_primary_metric_id(results: dict[str, Any]) -> str | None:
    """Extract a primary metric identifier from experiment results when available."""
    for key in ("primary_metric_id", "metric_id", "primaryMetricId"):
        value = results.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def extract_guardrail_metric_ids(results: dict[str, Any]) -> list[str]:
    """Extract guardrail metric identifiers from experiment results."""
    keys_to_check = ("guardrail_metric_ids", "guardrailMetrics", "guardrail_metrics")
    for key in keys_to_check:
        value = results.get(key)
        if isinstance(value, list):
            return [str(item) for item in value if item]
    return []


def extract_variation_ids(results: dict[str, Any], observations: list[dict[str, Any]]) -> list[str]:
    """Extract ordered variation identifiers from results or observed data."""
    variations = results.get("variations")
    if isinstance(variations, list):
        extracted = []
        for item in variations:
            if isinstance(item, dict):
                variation_id = item.get("variation_id") or item.get("id") or item.get("key")
                if variation_id is not None:
                    extracted.append(str(variation_id))
        if extracted:
            return extracted

    seen: list[str] = []
    for row in observations:
        variation_id = row.get("variation_id")
        if variation_id is not None and str(variation_id) not in seen:
            seen.append(str(variation_id))
    return seen


def safe_timestamp(value: Any) -> datetime | None:
    """Convert a timestamp-like value into a timezone-aware UTC datetime."""
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


def get_last_event_timestamp(observations: list[dict[str, Any]]) -> datetime | None:
    """Return the latest timestamp from metric observations when available."""
    timestamps = [
        timestamp
        for timestamp in (safe_timestamp(row.get("timestamp")) for row in observations)
        if timestamp is not None
    ]
    if not timestamps:
        return None
    return max(timestamps)


def get_experiment_start_timestamp(results: dict[str, Any]) -> datetime | None:
    """Extract experiment start timestamp from results payload when available."""
    for key in ("started_at", "startedAt", "start_date", "startDate"):
        timestamp = safe_timestamp(results.get(key))
        if timestamp is not None:
            return timestamp
    return None


def build_primary_summary(basic_stats: BasicStatsResult | None, cuped_applied: bool) -> str:
    """Build a plain-English primary metric summary."""
    if basic_stats is None:
        return DEFAULT_PRIMARY_SUMMARY
    significance = "statistically significant" if basic_stats.is_significant else "not statistically significant"
    cuped_note = " CUPED adjustment was applied." if cuped_applied else ""
    return (
        f"Treatment mean was {basic_stats.treatment_mean:.4f} versus {basic_stats.control_mean:.4f} for control, "
        f"an absolute lift of {basic_stats.absolute_lift:.4f} and relative lift of {basic_stats.relative_lift:.2%}. "
        f"The difference was {significance} (p={basic_stats.p_value:.4f}).{cuped_note}"
    )


def build_guardrail_summary(guardrail_flags: list[str]) -> str:
    """Build a plain-English guardrail summary."""
    if not guardrail_flags:
        return "No guardrail degradations were detected from the available results."
    return "Guardrail concerns detected: " + "; ".join(guardrail_flags)


async def fetch_results(state: InterpretationState) -> dict[str, Any]:
    """Fetch experiment results, health, and determine whether data quality passes."""
    growthbook_client = get_growthbook_client()
    bigquery_service = get_bigquery_service()
    stats_service = get_stats_service()
    experiment_results: dict[str, Any] = {}

    try:
        experiment_results = await growthbook_client.get_experiment_results(state["experiment_id"]) or {}
    except GrowthBookAPIError:
        experiment_results = {}

    try:
        health = await bigquery_service.get_experiment_health(state["experiment_id"])
        primary_metric_id = extract_primary_metric_id(experiment_results)
        if primary_metric_id is None:
            primary_metric_id = await bigquery_service.get_primary_metric_id(state["experiment_id"])
        guardrail_metrics = await bigquery_service.get_guardrail_metrics(state["experiment_id"])
        guardrail_metric_ids = [str(metric["metric_id"]) for metric in guardrail_metrics if metric.get("metric_id")]
        primary_observations = await bigquery_service.get_metric_observations(
            state["experiment_id"],
            metric_id=primary_metric_id,
        )
    except (BigQueryServiceError, ValueError) as error:
        fallback = build_fallback_recommendation(
            experiment_id=state["experiment_id"],
            reasoning=f"{FETCH_FAILURE_REASONING} {error}",
            data_quality_passed=False,
        )
        return {
            "fetch_failed": True,
            "decision": fallback.decision,
            "confidence": fallback.confidence,
            "primary_metric_summary": fallback.primary_metric_summary,
            "guardrail_summary": fallback.guardrail_summary,
            "reasoning": fallback.reasoning,
            "follow_up_cuts": fallback.follow_up_cuts,
            "risks": fallback.risks,
            "data_quality_passed": False,
            "recommendation": fallback,
            "messages": append_message(state, "fetch_results", "fetch_failed"),
        }

    if health is None:
        fallback = build_fallback_recommendation(
            experiment_id=state["experiment_id"],
            reasoning=FETCH_FAILURE_REASONING,
            data_quality_passed=False,
        )
        return {
            "fetch_failed": True,
            "decision": fallback.decision,
            "confidence": fallback.confidence,
            "primary_metric_summary": fallback.primary_metric_summary,
            "guardrail_summary": fallback.guardrail_summary,
            "reasoning": fallback.reasoning,
            "follow_up_cuts": fallback.follow_up_cuts,
            "risks": fallback.risks,
            "data_quality_passed": False,
            "recommendation": fallback,
            "messages": append_message(state, "fetch_results", "missing_results_or_health"),
        }

    last_event_timestamp = get_last_event_timestamp(primary_observations)
    experiment_start_timestamp = get_experiment_start_timestamp(experiment_results)

    if last_event_timestamp is None:
        data_quality_passed = False
    else:
        variation_ids = extract_variation_ids(experiment_results, primary_observations)
        variation_counts: dict[str, int] = {}
        for variation_id in variation_ids:
            user_ids = {
                str(row["user_id"])
                for row in primary_observations
                if str(row.get("variation_id")) == variation_id and row.get("user_id") is not None
            }
            variation_counts[variation_id] = len(user_ids)
        counts = list(variation_counts.values())
        control_count = counts[0] if len(counts) >= 1 else 0
        treatment_count = counts[1] if len(counts) >= 2 else 0
        dq_result = stats_service.run_data_quality_gate(
            experiment_id=state["experiment_id"],
            control_count=control_count,
            treatment_count=treatment_count,
            last_event_timestamp=last_event_timestamp,
            experiment_start_timestamp=experiment_start_timestamp,
            experiment_status="stopped",
        )
        data_quality_passed = dq_result.passed

    return {
        "experiment_results": experiment_results,
        "health": health,
        "metric_observations": primary_observations,
        "primary_metric_id": primary_metric_id,
        "guardrail_metric_ids": guardrail_metric_ids,
        "data_quality_passed": data_quality_passed,
        "messages": append_message(state, "fetch_results", "completed"),
    }


async def run_basic_stats(state: InterpretationState) -> dict[str, Any]:
    """Compute basic stats and apply CUPED when pre-experiment data is available."""
    if state["fetch_failed"]:
        return {}

    stats_service = get_stats_service()
    bigquery_service = get_bigquery_service()
    primary_metric_id = state["primary_metric_id"]
    if primary_metric_id is None:
        return {
            "basic_stats": None,
            "cuped_applied": False,
            "primary_metric_summary": DEFAULT_PRIMARY_SUMMARY,
            "messages": append_message(state, "run_basic_stats", "missing_primary_metric"),
        }

    observations = state["metric_observations"]
    variation_ids = extract_variation_ids(state["experiment_results"], observations)
    if len(variation_ids) < 2:
        return {
            "basic_stats": None,
            "cuped_applied": False,
            "primary_metric_summary": DEFAULT_PRIMARY_SUMMARY,
            "messages": append_message(state, "run_basic_stats", "insufficient_variations"),
        }

    variation_counts = await bigquery_service.get_variation_user_counts(state["experiment_id"])
    variation_types = await bigquery_service.get_variation_types(state["experiment_id"])
    pre_observations = await bigquery_service.get_pre_experiment_metric(
        state["experiment_id"],
        primary_metric_id,
    )
    cuped_applied = False
    adjusted_observations = observations
    if pre_observations:
        adjusted_observations = stats_service.apply_cuped(observations, pre_observations)
        cuped_applied = adjusted_observations is not observations

    control_id = next((vid for vid, vtype in variation_types.items() if vtype == "control"), variation_ids[0])
    treatment_id = next(
        (vid for vid, vtype in variation_types.items() if vtype == "treatment"),
        variation_ids[1],
    )
    filtered_observations = [
        row
        for row in adjusted_observations
        if str(row.get("metric_id")) == primary_metric_id and row.get("user_id") is not None
    ]
    control_converters = sum(1 for row in filtered_observations if str(row.get("variation_id")) == control_id)
    treatment_converters = sum(1 for row in filtered_observations if str(row.get("variation_id")) == treatment_id)
    control_total = variation_counts.get(control_id, 0)
    treatment_total = variation_counts.get(treatment_id, 0)
    control_values = [1.0] * control_converters + [0.0] * max(control_total - control_converters, 0)
    treatment_values = [1.0] * treatment_converters + [0.0] * max(treatment_total - treatment_converters, 0)
    if len(control_values) < 2 or len(treatment_values) < 2:
        return {
            "basic_stats": None,
            "cuped_applied": cuped_applied,
            "primary_metric_summary": DEFAULT_PRIMARY_SUMMARY,
            "messages": append_message(state, "run_basic_stats", "insufficient_metric_values"),
        }

    basic_stats = stats_service.compute_basic_stats(control_values, treatment_values)
    return {
        "basic_stats": basic_stats,
        "cuped_applied": cuped_applied,
        "primary_metric_summary": build_primary_summary(basic_stats, cuped_applied),
        "messages": append_message(state, "run_basic_stats", "completed"),
    }


def parse_metric_result_map(results: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Build a metric-id keyed map from an experiment results payload."""
    candidate_keys = ("metrics", "metric_results", "results")
    for key in candidate_keys:
        value = results.get(key)
        if isinstance(value, list):
            output: dict[str, dict[str, Any]] = {}
            for item in value:
                if isinstance(item, dict):
                    metric_id = item.get("metric_id") or item.get("id") or item.get("metricId")
                    if metric_id is not None:
                        output[str(metric_id)] = item
            if output:
                return output
        if isinstance(value, dict):
            output = {}
            for metric_id, metric_payload in value.items():
                if isinstance(metric_payload, dict):
                    output[str(metric_id)] = metric_payload
            if output:
                return output
    return {}


def extract_metric_delta(metric_payload: dict[str, Any]) -> float | None:
    """Extract a numeric effect delta from a metric payload when available."""
    for key in ("delta", "lift", "effect", "relative_lift", "change"):
        value = metric_payload.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return None


async def assess_guardrails(state: InterpretationState) -> dict[str, Any]:
    """Assess guardrail metrics for negative movement."""
    if state["fetch_failed"]:
        return {}

    bigquery_service = get_bigquery_service()
    variation_types = await bigquery_service.get_variation_types(state["experiment_id"])
    variation_ids = extract_variation_ids(state["experiment_results"], state["metric_observations"])
    if len(variation_ids) < 2:
        return {
            "guardrail_flags": [],
            "guardrail_metric_results": [],
            "guardrail_summary": DEFAULT_GUARDRAIL_SUMMARY,
            "messages": append_message(state, "assess_guardrails", "insufficient_variations"),
        }

    control_id = next((vid for vid, vtype in variation_types.items() if vtype == "control"), variation_ids[0])
    treatment_id = next(
        (vid for vid, vtype in variation_types.items() if vtype == "treatment"),
        variation_ids[1],
    )
    variation_counts = await bigquery_service.get_variation_user_counts(state["experiment_id"])
    guardrail_results = await bigquery_service.get_guardrail_metric_results(
        experiment_id=state["experiment_id"],
        guardrail_metric_ids=state["guardrail_metric_ids"],
        control_id=control_id,
        treatment_id=treatment_id,
        variation_counts=variation_counts,
    )

    guardrail_flags = [
        (
            f"Guardrail '{result['metric_name']}' degraded: control={result['control_rate']:.3f}, "
            f"treatment={result['treatment_rate']:.3f} ({result['relative_change']:.1%} change)"
        )
        for result in guardrail_results
        if result["degraded"]
    ]

    return {
        "guardrail_flags": guardrail_flags,
        "guardrail_metric_results": guardrail_results,
        "guardrail_summary": build_guardrail_summary(guardrail_flags),
        "messages": append_message(state, "assess_guardrails", f"{len(guardrail_flags)} guardrail flags"),
    }


def build_recommendation_prompt(state: InterpretationState) -> str:
    """Build the Claude prompt for recommendation generation."""
    health_payload = state["health"]
    sequential_context = {
        "health_status": health_payload.get("health_status") if isinstance(health_payload, dict) else None,
        "is_data_fresh": health_payload.get("is_data_fresh") if isinstance(health_payload, dict) else None,
        "has_minimum_sample": health_payload.get("has_minimum_sample") if isinstance(health_payload, dict) else None,
    }
    payload = {
        "experiment_id": state["experiment_id"],
        "data_quality_passed": state["data_quality_passed"],
        "basic_stats": asdict(state["basic_stats"]) if state["basic_stats"] is not None else None,
        "cuped_applied": state["cuped_applied"],
        "guardrail_flags": state["guardrail_flags"],
        "guardrail_metric_results": state.get("guardrail_metric_results", []),
        "sequential_test_context": sequential_context,
    }
    return (
        "Using the experiment evidence below, return JSON only with schema "
        '{"decision":"ship|iterate|abandon","confidence":0.0,"primary_metric_summary":"string",'
        '"guardrail_summary":"string","reasoning":"string","follow_up_cuts":["string"],"risks":["string"]}. '
        "Never recommend ship or abandon when data_quality_passed is false.\n"
        f"{json.dumps(payload)}"
    )


async def generate_recommendation(state: InterpretationState) -> dict[str, Any]:
    """Use Claude to synthesize a decision and supporting reasoning."""
    if state["fetch_failed"]:
        return {}

    if not state["data_quality_passed"]:
        return {
            "decision": ITERATE_DECISION,
            "confidence": 0.0,
            "reasoning": INVALID_DATA_QUALITY_REASONING,
            "primary_metric_summary": state["primary_metric_summary"] or DEFAULT_PRIMARY_SUMMARY,
            "guardrail_summary": state["guardrail_summary"] or DEFAULT_GUARDRAIL_SUMMARY,
            "follow_up_cuts": ["Resolve data quality issues before making a ship or abandon decision."],
            "risks": ["The underlying experiment data may be unreliable or incomplete."],
            "messages": append_message(state, "generate_recommendation", "forced_iterate"),
        }

    prompt = build_recommendation_prompt(state)
    last_error = PARSE_FAILURE_REASONING
    for _ in range(2):
        response_text = await call_claude(prompt)
        try:
            payload = RecommendationPayload.model_validate(
                json.loads(strip_markdown_fences(response_text))
            )
            decision = payload.decision if payload.decision in {SHIP_DECISION, ITERATE_DECISION, ABANDON_DECISION} else ITERATE_DECISION
            return {
                "decision": decision,
                "confidence": payload.confidence,
                "primary_metric_summary": payload.primary_metric_summary,
                "guardrail_summary": payload.guardrail_summary,
                "reasoning": payload.reasoning,
                "follow_up_cuts": payload.follow_up_cuts,
                "risks": payload.risks,
                "messages": append_message(state, "generate_recommendation", decision),
            }
        except (json.JSONDecodeError, ValidationError) as error:
            last_error = str(error)

    return {
        "decision": ITERATE_DECISION,
        "confidence": 0.0,
        "primary_metric_summary": state["primary_metric_summary"] or DEFAULT_PRIMARY_SUMMARY,
        "guardrail_summary": state["guardrail_summary"] or DEFAULT_GUARDRAIL_SUMMARY,
        "reasoning": f"{PARSE_FAILURE_REASONING} {last_error}",
        "follow_up_cuts": ["Review the raw results and rerun interpretation."],
        "risks": ["The recommendation model did not return valid structured output."],
        "messages": append_message(state, "generate_recommendation", "fallback"),
    }


async def build_recommendation(state: InterpretationState) -> dict[str, Any]:
    """Assemble the final Recommendation object from graph state."""
    if state["recommendation"] is not None:
        return {"recommendation": state["recommendation"]}

    decision = state["decision"]
    if not state["data_quality_passed"] and decision in {SHIP_DECISION, ABANDON_DECISION}:
        decision = ITERATE_DECISION

    recommendation = Recommendation(
        experiment_id=state["experiment_id"],
        decision=decision,
        confidence=state["confidence"],
        primary_metric_summary=state["primary_metric_summary"] or DEFAULT_PRIMARY_SUMMARY,
        guardrail_summary=state["guardrail_summary"] or DEFAULT_GUARDRAIL_SUMMARY,
        reasoning=state["reasoning"] or PARSE_FAILURE_REASONING,
        follow_up_cuts=state["follow_up_cuts"],
        risks=state["risks"],
        data_quality_passed=state["data_quality_passed"],
        created_at=utc_now(),
    )
    return {
        "recommendation": recommendation,
        "messages": append_message(state, "build_recommendation", recommendation.decision),
    }


def route_after_fetch(state: InterpretationState) -> str:
    """Route directly to final assembly on fetch failure, or continue analysis otherwise."""
    return "build_recommendation" if state["fetch_failed"] else "run_basic_stats"


def compile_interpretation_graph() -> Any:
    """Build and compile the interpretation StateGraph."""
    graph = StateGraph(InterpretationState)
    graph.add_node("fetch_results", fetch_results)
    graph.add_node("run_basic_stats", run_basic_stats)
    graph.add_node("assess_guardrails", assess_guardrails)
    graph.add_node("generate_recommendation", generate_recommendation)
    graph.add_node("build_recommendation", build_recommendation)

    graph.set_entry_point("fetch_results")
    graph.add_conditional_edges(
        "fetch_results",
        route_after_fetch,
        {
            "run_basic_stats": "run_basic_stats",
            "build_recommendation": "build_recommendation",
        },
    )
    graph.add_edge("run_basic_stats", "assess_guardrails")
    graph.add_edge("assess_guardrails", "generate_recommendation")
    graph.add_edge("generate_recommendation", "build_recommendation")
    graph.add_edge("build_recommendation", END)
    return graph.compile()


async def run_interpretation_agent(experiment_id: str) -> Recommendation:
    """Run the interpretation agent graph and return a structured recommendation."""
    graph = compile_interpretation_graph()
    initial_state: InterpretationState = {
        "experiment_id": experiment_id,
        "experiment_results": {},
        "health": {},
        "metric_observations": [],
        "primary_metric_id": None,
        "guardrail_metric_ids": [],
        "guardrail_metric_results": [],
        "basic_stats": None,
        "cuped_applied": False,
        "guardrail_flags": [],
        "data_quality_passed": False,
        "decision": ITERATE_DECISION,
        "confidence": 0.0,
        "primary_metric_summary": "",
        "guardrail_summary": "",
        "reasoning": "",
        "follow_up_cuts": [],
        "risks": [],
        "messages": [],
        "fetch_failed": False,
        "recommendation": None,
    }
    result = await graph.ainvoke(initial_state)
    recommendation = result["recommendation"]
    if recommendation is None:
        recommendation = build_fallback_recommendation(
            experiment_id=experiment_id,
            reasoning=PARSE_FAILURE_REASONING,
            data_quality_passed=False,
        )

    logging.getLogger(LOGGER_NAME).info(
        "Interpretation agent completed",
        extra={
            "experiment_id_hash": hashlib.sha256(experiment_id.encode("utf-8")).hexdigest(),
            "decision": recommendation.decision,
        },
    )
    return recommendation

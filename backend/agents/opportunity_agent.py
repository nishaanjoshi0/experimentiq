"""LangGraph opportunity discovery agent for ExperimentIQ.

Takes company context and behavioral analytics data, reasons over it with
Claude, and returns a ranked list of experiment opportunities with estimated
lift ranges, effort scores, and risk levels.

Five-node pipeline:
  ingest_and_analyze → retrieve_context → generate_candidates → score_and_rank → build_report
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Final, TypedDict

from anthropic import AsyncAnthropic
from dotenv import load_dotenv
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field, ValidationError

from services.analytics_ingestion import AnalyticsSummary, ingest_csv, ingest_demo
from services.vector_store import SimpleVectorStore


LOGGER_NAME: Final[str] = "experimentiq.opportunity_agent"
SYSTEM_PROMPT: Final[str] = (
    "You are a senior growth analytics expert. You identify high-probability experiment "
    "opportunities from behavioral data. You are evidence-driven, specific, and always "
    "ground recommendations in the data provided rather than general best practices."
)
MODEL_NAME: Final[str] = "claude-sonnet-4-6"
MAX_TOKENS: Final[int] = 4096
ANTHROPIC_API_KEY_ENV_VAR: Final[str] = "ANTHROPIC_API_KEY"
JSON_RESPONSE_INSTRUCTION: Final[str] = (
    "Return JSON only. Do not include markdown fences or any explanatory text."
)

load_dotenv()

_anthropic_client: AsyncAnthropic | None = None


class ExperimentOpportunity(BaseModel):
    """A single ranked experiment opportunity."""

    rank: int
    title: str
    hypothesis: str
    primary_metric: str
    estimated_lift_low_pct: float = Field(
        description="Conservative estimate of relative lift, as a percentage (e.g. 8.0 = 8%)"
    )
    estimated_lift_high_pct: float = Field(
        description="Optimistic estimate of relative lift, as a percentage"
    )
    risk_level: str = Field(description="low | medium | high")
    effort_level: str = Field(description="low | medium | high")
    evidence: str = Field(description="The specific data point(s) that support this opportunity")
    expected_impact_score: float = Field(ge=0.0, le=1.0)
    segment_to_watch: str = Field(description="Which user segment to analyze first for results")


class OpportunityReport(BaseModel):
    """Full output of the opportunity discovery agent."""

    opportunities: list[ExperimentOpportunity]
    data_summary: dict[str, Any]
    analysis_context: str
    generated_at: str
    confidence: float = Field(ge=0.0, le=1.0)
    data_source: str


class OpportunityState(TypedDict):
    """State threaded through the opportunity discovery graph."""

    company_description: str
    current_metrics: dict[str, float]
    data_source: str
    csv_content: str | None

    analytics_summary: AnalyticsSummary | None
    vector_store: SimpleVectorStore | None
    funnel_analysis: str
    segment_analysis: str
    rag_context: list[str]
    opportunity_candidates: str
    scored_opportunities: str

    report: OpportunityReport | None
    fetch_failed: bool
    failure_reason: str
    messages: list[str]
    _prebuilt_summary: AnalyticsSummary | None


def get_anthropic_client() -> AsyncAnthropic:
    global _anthropic_client
    if _anthropic_client is None:
        api_key = os.getenv(ANTHROPIC_API_KEY_ENV_VAR)
        if not api_key:
            raise ValueError(f"{ANTHROPIC_API_KEY_ENV_VAR} must be set.")
        _anthropic_client = AsyncAnthropic(api_key=api_key)
    return _anthropic_client


async def call_claude(prompt: str) -> str:
    client = get_anthropic_client()
    response = await client.messages.create(
        model=MODEL_NAME,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    text_blocks = [block.text for block in response.content if getattr(block, "type", "") == "text"]
    return "\n".join(text_blocks).strip()


def strip_markdown_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:] if lines[0].startswith("```") else lines
        lines = lines[:-1] if lines and lines[-1].strip() == "```" else lines
        text = "\n".join(lines)
    return text.strip()


def _append(state: OpportunityState, label: str, content: str) -> list[str]:
    return [*state["messages"], f"{label}: {content[:200]}"]


def _format_funnel(summary: AnalyticsSummary) -> str:
    if not summary.funnel_steps:
        return "Funnel data not available."
    parts = []
    for step in summary.funnel_steps:
        parts.append(
            f"  {step.name}: {step.users:,} users"
            + (f" ({step.drop_off_rate:.0%} drop-off)" if step.drop_off_rate > 0 else "")
        )
    return "\n".join(parts)


def _format_device_segments(summary: AnalyticsSummary) -> str:
    lines = []
    for seg in summary.device_segments:
        lines.append(
            f"  {seg.segment_name}: {seg.sessions:,} sessions, "
            f"{seg.conversion_rate:.1%} CVR, "
            f"bounce {seg.extra.get('bounce_rate', 0):.0%}"
        )
    return "\n".join(lines)


def _build_data_context(summary: AnalyticsSummary, company_description: str) -> str:
    insights_text = "\n".join(
        f"  [{ins.category}] {ins.description}" for ins in summary.insights[:6]
    )
    return (
        f"Company context: {company_description or 'E-commerce store (no description provided)'}\n\n"
        f"Data period: {summary.date_range}\n"
        f"Total sessions: {summary.total_sessions:,}\n"
        f"Overall conversion rate: {summary.overall_conversion_rate:.1%}\n"
        f"Total revenue: ${summary.total_revenue:,.0f}\n\n"
        f"Conversion funnel:\n{_format_funnel(summary)}\n\n"
        f"Device segments:\n{_format_device_segments(summary)}\n\n"
        f"Key insights from the data:\n{insights_text}\n"
    )


async def ingest_and_analyze(state: OpportunityState) -> dict[str, Any]:
    """Node 1: Ingest analytics data and run funnel + segment analysis with Claude."""
    logger = logging.getLogger(LOGGER_NAME)
    try:
        if state.get("_prebuilt_summary") is not None:
            summary = state["_prebuilt_summary"]
        elif state["data_source"] == "demo":
            summary = ingest_demo()
        elif state["csv_content"]:
            summary = ingest_csv(state["csv_content"], state["company_description"])
        else:
            summary = ingest_demo()

        store = SimpleVectorStore()
        store.add_documents(
            documents=summary.raw_chunks,
            metadata=[{"type": "analytics"} for _ in summary.raw_chunks],
        )

        if state["company_description"]:
            store.add_documents(
                documents=[state["company_description"]],
                metadata=[{"type": "company_context"}],
            )

        data_ctx = _build_data_context(summary, state["company_description"])

        funnel_prompt = (
            f"{data_ctx}\n\n"
            "Analyze the conversion funnel. Identify:\n"
            "1. The single biggest drop-off point and its likely cause\n"
            "2. How device type affects funnel performance\n"
            "3. The step with the most leverage for improvement\n"
            "Be specific and quantitative. Two to three paragraphs."
        )
        funnel_analysis = await call_claude(funnel_prompt)

        segment_prompt = (
            f"{data_ctx}\n\n"
            "Analyze segment-level performance. Identify:\n"
            "1. The segment with the largest gap from overall average conversion\n"
            "2. What behavioral differences explain the segment gap\n"
            "3. Which segment is highest-leverage for experimentation\n"
            "Be specific and quantitative. Two to three paragraphs."
        )
        segment_analysis = await call_claude(segment_prompt)

        logger.info(
            "Opportunity agent: data ingested",
            extra={
                "data_source": state["data_source"],
                "total_sessions": summary.total_sessions,
                "vector_store_size": len(store),
            },
        )

        return {
            "analytics_summary": summary,
            "vector_store": store,
            "funnel_analysis": funnel_analysis,
            "segment_analysis": segment_analysis,
            "fetch_failed": False,
            "messages": _append(state, "ingest_and_analyze", funnel_analysis),
        }

    except Exception as exc:
        logger.exception("ingest_and_analyze failed: %s", exc)
        return {
            "fetch_failed": True,
            "failure_reason": str(exc),
            "messages": _append(state, "ingest_and_analyze", f"ERROR: {exc}"),
        }


async def retrieve_context(state: OpportunityState) -> dict[str, Any]:
    """Node 2: Query the vector store for context relevant to each opportunity area."""
    if state.get("fetch_failed"):
        return {}

    store: SimpleVectorStore = state["vector_store"]
    queries = [
        "mobile conversion rate performance gap",
        "cart abandonment checkout drop-off rate",
        "product page add to cart rate",
        "site search usage conversion uplift",
        "returning user retention email engagement",
        "page speed load time mobile performance",
    ]
    retrieved: list[str] = []
    for query in queries:
        results = store.query(query, n_results=2, min_score=0.05)
        for doc, _, score in results:
            if doc not in retrieved:
                retrieved.append(doc)

    if len(retrieved) < 5:
        retrieved = store.get_top_documents(10)

    return {
        "rag_context": retrieved,
        "messages": _append(state, "retrieve_context", f"{len(retrieved)} context chunks retrieved"),
    }


async def generate_candidates(state: OpportunityState) -> dict[str, Any]:
    """Node 3: Generate 8–10 raw experiment hypothesis candidates from the data."""
    if state.get("fetch_failed"):
        return {}

    summary: AnalyticsSummary = state["analytics_summary"]
    rag_chunks = "\n".join(f"- {chunk}" for chunk in state["rag_context"])
    data_ctx = _build_data_context(summary, state["company_description"])

    prompt = (
        f"{data_ctx}\n\n"
        f"Funnel analysis:\n{state['funnel_analysis']}\n\n"
        f"Segment analysis:\n{state['segment_analysis']}\n\n"
        f"Retrieved analytics context:\n{rag_chunks}\n\n"
        "Generate 8 to 10 specific, testable experiment hypothesis candidates grounded in this data. "
        "Each hypothesis must reference a specific metric value from the data above as its justification. "
        "Do not include generic ideas like 'improve UX' — each must be actionable and measurable.\n\n"
        "Format as a numbered list. Each item: [Title]: [Hypothesis]. [Evidence from data]."
    )
    candidates = await call_claude(prompt)
    return {
        "opportunity_candidates": candidates,
        "messages": _append(state, "generate_candidates", candidates),
    }


def _build_opportunity_schema() -> dict[str, Any]:
    return {
        "opportunities": [
            {
                "rank": "int (1 = highest impact)",
                "title": "short title string",
                "hypothesis": "full hypothesis string",
                "primary_metric": "the metric this experiment moves",
                "estimated_lift_low_pct": "conservative relative lift estimate as a float percentage",
                "estimated_lift_high_pct": "optimistic relative lift estimate as a float percentage",
                "risk_level": "low | medium | high",
                "effort_level": "low | medium | high",
                "evidence": "specific data point from the analytics that justifies this experiment",
                "expected_impact_score": "float 0-1 representing overall value of running this experiment",
                "segment_to_watch": "which user segment to analyze first for results",
            }
        ],
        "analysis_context": "2-3 sentence summary of the overall data story",
        "confidence": "float 0-1 representing confidence in these recommendations given data quality",
    }


async def score_and_rank(state: OpportunityState) -> dict[str, Any]:
    """Node 4: Score candidates on expected impact, effort, and risk. Rank and filter to top 5."""
    if state.get("fetch_failed"):
        return {}

    summary: AnalyticsSummary = state["analytics_summary"]
    schema = _build_opportunity_schema()
    data_ctx = _build_data_context(summary, state["company_description"])

    prompt = (
        f"{data_ctx}\n\n"
        f"Candidate experiments:\n{state['opportunity_candidates']}\n\n"
        "Score and rank the top 5 experiments from the candidates above. "
        "Prioritize by: (1) size of the behavioral gap the data shows, "
        "(2) how clearly the data supports this intervention, "
        "(3) effort relative to expected lift. "
        "Lift estimates must be grounded in the gap size visible in the data "
        "(e.g. if mobile CVR is 1.2% vs desktop 3.8%, a successful mobile test "
        "could realistically achieve 15-40% relative lift on mobile CVR).\n\n"
        f"{JSON_RESPONSE_INSTRUCTION}\n"
        f"Required schema:\n{json.dumps(schema, indent=2)}"
    )

    last_error = "Unknown parse error."
    for _ in range(2):
        response_text = await call_claude(prompt)
        try:
            parsed = json.loads(strip_markdown_fences(response_text))
            return {
                "scored_opportunities": response_text,
                "messages": _append(state, "score_and_rank", response_text),
                "_parsed_opportunities": parsed,
            }
        except json.JSONDecodeError as exc:
            last_error = str(exc)

    return {
        "scored_opportunities": "",
        "fetch_failed": True,
        "failure_reason": f"JSON parse failure in score_and_rank: {last_error}",
        "messages": _append(state, "score_and_rank", f"PARSE ERROR: {last_error}"),
    }


def _fallback_report(state: OpportunityState) -> OpportunityReport:
    reason = state.get("failure_reason", "Unknown error in opportunity agent.")
    return OpportunityReport(
        opportunities=[],
        data_summary={"error": reason},
        analysis_context=(
            f"The opportunity agent could not complete analysis. Reason: {reason} "
            "Try using the demo dataset or check your CSV format."
        ),
        generated_at=datetime.now(tz=timezone.utc).isoformat(),
        confidence=0.0,
        data_source=state.get("data_source", "unknown"),
    )


async def build_report(state: OpportunityState) -> dict[str, Any]:
    """Node 5: Assemble the final OpportunityReport."""
    logger = logging.getLogger(LOGGER_NAME)

    if state.get("fetch_failed"):
        return {
            "report": _fallback_report(state),
            "messages": _append(state, "build_report", "fallback report generated"),
        }

    summary: AnalyticsSummary = state["analytics_summary"]
    parsed = state.get("_parsed_opportunities", {})

    try:
        raw_opps = parsed.get("opportunities", [])
        opportunities = []
        for raw in raw_opps:
            try:
                opp = ExperimentOpportunity.model_validate(raw)
                opportunities.append(opp)
            except ValidationError as exc:
                logger.warning("Skipping malformed opportunity: %s", exc)

        if not opportunities:
            return {
                "report": _fallback_report(state),
                "messages": _append(state, "build_report", "no valid opportunities parsed"),
            }

        data_summary: dict[str, Any] = {
            "total_sessions": summary.total_sessions,
            "overall_conversion_rate": round(summary.overall_conversion_rate, 4),
            "total_revenue": round(summary.total_revenue, 2),
            "currency": summary.currency,
            "date_range": summary.date_range,
            "top_insights": [ins.description for ins in summary.insights[:3]],
        }

        report = OpportunityReport(
            opportunities=opportunities,
            data_summary=data_summary,
            analysis_context=parsed.get("analysis_context", ""),
            generated_at=datetime.now(tz=timezone.utc).isoformat(),
            confidence=min(1.0, max(0.0, float(parsed.get("confidence", 0.7)))),
            data_source=state.get("data_source", "unknown"),
        )

        logger.info(
            "Opportunity agent completed",
            extra={
                "n_opportunities": len(opportunities),
                "confidence": report.confidence,
                "data_source": state["data_source"],
            },
        )

        return {
            "report": report,
            "messages": _append(state, "build_report", f"{len(opportunities)} opportunities generated"),
        }

    except Exception as exc:
        logger.exception("build_report failed: %s", exc)
        return {
            "report": _fallback_report(state),
            "messages": _append(state, "build_report", f"ERROR: {exc}"),
        }


def _route_after_ingest(state: OpportunityState) -> str:
    if state.get("fetch_failed"):
        return "build_report"
    return "retrieve_context"


def compile_opportunity_graph() -> Any:
    graph = StateGraph(OpportunityState)
    graph.add_node("ingest_and_analyze", ingest_and_analyze)
    graph.add_node("retrieve_context", retrieve_context)
    graph.add_node("generate_candidates", generate_candidates)
    graph.add_node("score_and_rank", score_and_rank)
    graph.add_node("build_report", build_report)

    graph.set_entry_point("ingest_and_analyze")
    graph.add_conditional_edges(
        "ingest_and_analyze",
        _route_after_ingest,
        {"retrieve_context": "retrieve_context", "build_report": "build_report"},
    )
    graph.add_edge("retrieve_context", "generate_candidates")
    graph.add_edge("generate_candidates", "score_and_rank")
    graph.add_edge("score_and_rank", "build_report")
    graph.add_edge("build_report", END)
    return graph.compile()


async def run_opportunity_agent(
    company_description: str,
    current_metrics: dict[str, float],
    data_source: str = "demo",
    csv_content: str | None = None,
    analytics_summary: AnalyticsSummary | None = None,
) -> OpportunityReport:
    """Run the full opportunity discovery graph and return the ranked report."""
    graph = compile_opportunity_graph()
    initial_state: OpportunityState = {
        "company_description": company_description,
        "current_metrics": current_metrics,
        "data_source": data_source,
        "csv_content": csv_content,
        "analytics_summary": None,
        "vector_store": None,
        "funnel_analysis": "",
        "segment_analysis": "",
        "rag_context": [],
        "opportunity_candidates": "",
        "scored_opportunities": "",
        "report": None,
        "fetch_failed": False,
        "failure_reason": "",
        "messages": [],
        "_parsed_opportunities": {},
        "_prebuilt_summary": analytics_summary,
    }
    result = await graph.ainvoke(initial_state)
    report = result.get("report")
    if report is None:
        report = _fallback_report(initial_state)
    return report

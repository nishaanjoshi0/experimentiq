"""LangGraph framing agent for ExperimentIQ experiment design."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any, Final, TypedDict

from anthropic import AsyncAnthropic
from dotenv import load_dotenv
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field, ValidationError


LOGGER_NAME: Final[str] = "experimentiq.framing_agent"
SYSTEM_PROMPT: Final[str] = (
    "You are an expert experimentation designer at a growth-stage tech company. "
    "You are precise, opinionated, and always think about statistical validity."
)
MODEL_NAME: Final[str] = "claude-sonnet-4-5-20250929"
MAX_TOKENS: Final[int] = 4000
ANTHROPIC_API_KEY_ENV_VAR: Final[str] = "ANTHROPIC_API_KEY"
DEFAULT_INTENT: Final[str] = ""
DEFAULT_PROPOSED_METRICS: Final[str] = ""
DEFAULT_RUNTIME_ESTIMATE: Final[str] = ""
DEFAULT_TRADEOFFS: Final[str] = ""
JSON_RESPONSE_INSTRUCTION: Final[str] = (
    "Return JSON only. Do not include markdown fences or any explanatory text."
)
JSON_PARSE_FAILURE_MESSAGE: Final[str] = (
    "The framing agent could not parse a valid experiment design JSON response."
)

load_dotenv()

_anthropic_client: AsyncAnthropic | None = None


class ExperimentDesign(BaseModel):
    """Structured experiment design returned by the framing agent."""

    hypothesis: str
    primary_metric: str
    metric_rationale: str
    guardrail_metrics: list[str]
    unit_of_randomization: str
    estimated_runtime_days: int
    minimum_detectable_effect: float
    tradeoffs: list[str]
    clarifying_questions: list[str]
    confidence: float = Field(ge=0.0, le=1.0)


class FramingState(TypedDict):
    """State passed through the framing graph."""

    raw_hypothesis: str
    intent: str
    proposed_metrics: str
    runtime_estimate: str
    tradeoffs: str
    design: ExperimentDesign | None
    messages: list[str]


def get_anthropic_client() -> AsyncAnthropic:
    """Return a singleton Anthropic client configured from environment variables."""
    global _anthropic_client
    if _anthropic_client is None:
        api_key = os.getenv(ANTHROPIC_API_KEY_ENV_VAR)
        if not api_key:
            raise ValueError(f"{ANTHROPIC_API_KEY_ENV_VAR} must be set.")
        _anthropic_client = AsyncAnthropic(api_key=api_key)
    return _anthropic_client


async def call_claude(prompt: str) -> str:
    """Send a single stateless request to Claude and return the text response."""
    client = get_anthropic_client()
    response = await client.messages.create(
        model=MODEL_NAME,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    text_blocks = [block.text for block in response.content if getattr(block, "type", "") == "text"]
    return "\n".join(text_blocks).strip()


def build_context(state: FramingState) -> str:
    """Build the shared node context from prior graph state."""
    return (
        f"Raw hypothesis:\n{state['raw_hypothesis']}\n\n"
        f"Intent analysis:\n{state['intent'] or 'Not yet analyzed.'}\n\n"
        f"Metric proposal:\n{state['proposed_metrics'] or 'Not yet proposed.'}\n\n"
        f"Runtime estimate:\n{state['runtime_estimate'] or 'Not yet estimated.'}\n\n"
        f"Tradeoff analysis:\n{state['tradeoffs'] or 'Not yet analyzed.'}\n"
    )


def append_message(state: FramingState, label: str, content: str) -> list[str]:
    """Append a labeled step output to the graph message history."""
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


async def extract_intent(state: FramingState) -> dict[str, Any]:
    """Parse the raw hypothesis into a clear product intent and decision goal."""
    prompt = (
        f"{build_context(state)}\n"
        "Task: Extract the product area, user behavior change, business goal, and any ambiguity. "
        "Be concise but specific."
    )
    intent = await call_claude(prompt)
    return {
        "intent": intent,
        "messages": append_message(state, "extract_intent", intent),
    }


async def propose_metrics(state: FramingState) -> dict[str, Any]:
    """Propose a primary metric and guardrails based on the parsed intent."""
    prompt = (
        f"{build_context(state)}\n"
        "Task: Propose exactly one primary metric, several sensible guardrail metrics, and explain why. "
        "Consider statistical validity and business relevance."
    )
    proposed_metrics = await call_claude(prompt)
    return {
        "proposed_metrics": proposed_metrics,
        "messages": append_message(state, "propose_metrics", proposed_metrics),
    }


async def estimate_runtime(state: FramingState) -> dict[str, Any]:
    """Estimate experiment runtime and minimum detectable effect assumptions."""
    prompt = (
        f"{build_context(state)}\n"
        "Task: Estimate recommended runtime in days and a plausible minimum detectable effect. "
        "State the assumptions briefly, including likely baseline conversion behavior and traffic needs."
    )
    runtime_estimate = await call_claude(prompt)
    return {
        "runtime_estimate": runtime_estimate,
        "messages": append_message(state, "estimate_runtime", runtime_estimate),
    }


async def flag_tradeoffs(state: FramingState) -> dict[str, Any]:
    """Identify likely tradeoffs, risks, and statistical pitfalls."""
    prompt = (
        f"{build_context(state)}\n"
        "Task: Identify the most important tradeoffs, failure modes, guardrail risks, and measurement caveats "
        "for this experiment."
    )
    tradeoffs = await call_claude(prompt)
    return {
        "tradeoffs": tradeoffs,
        "messages": append_message(state, "flag_tradeoffs", tradeoffs),
    }


def build_design_prompt(state: FramingState) -> str:
    """Build the final JSON-only synthesis prompt for the design output."""
    schema = {
        "hypothesis": "string",
        "primary_metric": "string",
        "metric_rationale": "string",
        "guardrail_metrics": ["string"],
        "unit_of_randomization": "string",
        "estimated_runtime_days": "int",
        "minimum_detectable_effect": "float",
        "tradeoffs": ["string"],
        "clarifying_questions": ["string"],
        "confidence": "float between 0 and 1",
    }
    return (
        f"{build_context(state)}\n"
        "Task: Synthesize the prior reasoning into a structured experiment design. "
        "If the hypothesis is too vague, set low confidence and populate clarifying_questions. "
        "If it is clear enough, clarifying_questions should be an empty list. "
        f"{JSON_RESPONSE_INSTRUCTION}\n"
        f"Required schema:\n{json.dumps(schema, indent=2)}"
    )


def fallback_design(raw_hypothesis: str, error_message: str) -> ExperimentDesign:
    """Build a low-confidence fallback design when JSON parsing fails."""
    return ExperimentDesign(
        hypothesis=raw_hypothesis,
        primary_metric="unknown",
        metric_rationale="The framing agent failed to produce valid structured output.",
        guardrail_metrics=[],
        unit_of_randomization="user",
        estimated_runtime_days=0,
        minimum_detectable_effect=0.0,
        tradeoffs=["Unable to assess tradeoffs due to response parsing failure."],
        clarifying_questions=[f"{JSON_PARSE_FAILURE_MESSAGE} {error_message}"],
        confidence=0.0,
    )


async def generate_design(state: FramingState) -> dict[str, Any]:
    """Generate and parse the final ExperimentDesign from prior graph outputs."""
    prompt = build_design_prompt(state)
    last_error_message = JSON_PARSE_FAILURE_MESSAGE

    for _ in range(2):
        response_text = await call_claude(prompt)
        try:
            parsed = json.loads(strip_markdown_fences(response_text))
            design = ExperimentDesign.model_validate(parsed)
            return {
                "design": design,
                "messages": append_message(state, "generate_design", response_text),
            }
        except (json.JSONDecodeError, ValidationError) as error:
            last_error_message = str(error)

    design = fallback_design(state["raw_hypothesis"], last_error_message)
    return {
        "design": design,
        "messages": append_message(state, "generate_design", design.model_dump_json()),
    }


def compile_framing_graph() -> Any:
    """Build and compile the framing StateGraph."""
    graph = StateGraph(FramingState)
    graph.add_node("extract_intent", extract_intent)
    graph.add_node("propose_metrics", propose_metrics)
    graph.add_node("estimate_runtime", estimate_runtime)
    graph.add_node("flag_tradeoffs", flag_tradeoffs)
    graph.add_node("generate_design", generate_design)

    graph.set_entry_point("extract_intent")
    graph.add_edge("extract_intent", "propose_metrics")
    graph.add_edge("propose_metrics", "estimate_runtime")
    graph.add_edge("estimate_runtime", "flag_tradeoffs")
    graph.add_edge("flag_tradeoffs", "generate_design")
    graph.add_edge("generate_design", END)
    return graph.compile()


async def run_framing_agent(hypothesis: str) -> ExperimentDesign:
    """Run the full framing graph and return the structured experiment design."""
    graph = compile_framing_graph()
    initial_state: FramingState = {
        "raw_hypothesis": hypothesis,
        "intent": DEFAULT_INTENT,
        "proposed_metrics": DEFAULT_PROPOSED_METRICS,
        "runtime_estimate": DEFAULT_RUNTIME_ESTIMATE,
        "tradeoffs": DEFAULT_TRADEOFFS,
        "design": None,
        "messages": [],
    }
    result = await graph.ainvoke(initial_state)
    design = result["design"]
    if design is None:
        design = fallback_design(hypothesis, "Graph completed without a design output.")

    hypothesis_hash = hashlib.sha256(hypothesis.encode("utf-8")).hexdigest()
    logging.getLogger(LOGGER_NAME).info(
        "Framing agent completed",
        extra={"hypothesis_hash": hypothesis_hash, "confidence": design.confidence},
    )
    return design

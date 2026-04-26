"""Post-experiment interpretation service for ExperimentIQ."""

from __future__ import annotations

import json
import logging
import os
from typing import Final

import anthropic
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from services.experiment_stats import ExperimentResults

load_dotenv()

LOGGER_NAME: Final[str] = "experimentiq.experiment_interpreter"
MODEL_NAME: Final[str] = "claude-sonnet-4-6"
MAX_TOKENS: Final[int] = 2048
ANTHROPIC_API_KEY_ENV_VAR: Final[str] = "ANTHROPIC_API_KEY"

SYSTEM_PROMPT: Final[str] = (
    "You are a senior growth analyst. You interpret A/B test results with rigor and honesty. "
    "You surface unexpected patterns, flag uncertainty, and make clear recommendations grounded in the data."
)

VALID_VERDICTS: Final[frozenset[str]] = frozenset({"ship", "don't ship", "run longer"})

_anthropic_client: anthropic.AsyncAnthropic | None = None


class InterpretationResult(BaseModel):
    """Structured interpretation result returned by the experiment interpreter."""

    verdict: str = Field(description="One of: ship, don't ship, run longer")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score between 0.0 and 1.0")
    headline: str = Field(description="One sentence summary of what happened")
    narrative: str = Field(description="3-4 paragraph story covering what moved, what did not, surprising patterns, and business meaning")
    key_evidence: list[str] = Field(description="Bullet points of key supporting evidence")
    risks: list[str] = Field(description="Identified risks with this decision")
    follow_up: list[str] = Field(description="What to investigate next")


def _get_anthropic_client() -> anthropic.AsyncAnthropic:
    """Return a singleton async Anthropic client configured from the environment."""
    global _anthropic_client
    if _anthropic_client is None:
        api_key = os.getenv(ANTHROPIC_API_KEY_ENV_VAR)
        if not api_key:
            raise ValueError(f"{ANTHROPIC_API_KEY_ENV_VAR} must be set.")
        _anthropic_client = anthropic.AsyncAnthropic(api_key=api_key)
    return _anthropic_client


def _strip_markdown_fences(text: str) -> str:
    """Strip markdown code fences from a JSON response."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:] if lines[0].startswith("```") else lines
        lines = lines[:-1] if lines and lines[-1].strip() == "```" else lines
        text = "\n".join(lines)
    return text.strip()


def _build_prompt(
    results: ExperimentResults,
    hypothesis: str,
    target_event: str,
) -> str:
    """Build the Claude prompt from pre-computed experiment results."""
    lines: list[str] = []

    lines.append("## Experiment Interpretation Request")
    lines.append("")
    lines.append(f"**Hypothesis:** {hypothesis}")
    lines.append(f"**Primary Metric (Target Event):** {target_event}")
    lines.append("")

    # Variant metrics — results.variants is dict[str, VariantMetrics] (dataclass)
    lines.append("## Variant Metrics")
    for variant_name, vm in results.variants.items():
        lines.append(f"### {variant_name}")
        lines.append(f"  - Users: {vm.users}")
        lines.append(f"  - Conversions: {vm.conversions}")
        lines.append(f"  - Conversion Rate: {vm.conversion_rate:.4f} ({vm.conversion_rate * 100:.2f}%)")
        lines.append(f"  - Revenue per User: ${vm.revenue_per_user:.4f}")
        if vm.guardrail_rates:
            lines.append("  - Guardrail Rates:")
            for guardrail_name, rate in vm.guardrail_rates.items():
                lines.append(f"    - {guardrail_name}: {rate:.4f} ({rate * 100:.2f}%)")

    lines.append("")

    # Statistical test results — results.stat_tests is list[StatTestResult] (dataclass)
    lines.append("## Statistical Test Results")
    for test in results.stat_tests:
        lines.append(f"### {test.metric}")
        lines.append(f"  - Control value: {test.control_value:.4f}")
        lines.append(f"  - Treatment value: {test.treatment_value:.4f}")
        lines.append(f"  - Relative lift: {test.relative_lift_pct:.2f}%")
        lines.append(f"  - p-value: {test.p_value:.4f}")
        lines.append(f"  - 95% CI: [{test.ci_low_pct:.2f}%, {test.ci_high_pct:.2f}%]")
        sig_label = "SIGNIFICANT" if test.is_significant else "not significant"
        lines.append(f"  - Result: {sig_label}")

    lines.append("")

    # SRM result — results.srm is an SRMResult dataclass
    lines.append("## Sample Ratio Mismatch (SRM) Check")
    srm = results.srm
    if srm:
        srm_status = "PASSED (no SRM detected)" if srm.passed else "FAILED (SRM detected)"
        lines.append(f"  - Status: {srm_status}")
        lines.append(f"  - Chi-square p-value: {srm.p_value:.4f}")
        if srm.message:
            lines.append(f"  - Details: {srm.message}")
    lines.append("")

    # Novelty warning
    if results.novelty_warning:
        lines.append("## ⚠️ Novelty Warning")
        lines.append(
            "  - A novelty effect has been detected. Early lift appears meaningfully stronger "
            "than overall lift. Results may not represent steady-state behavior."
        )
        lines.append("")

    # Instruction
    lines.append("## Instructions")
    lines.append(
        "You are a senior growth analyst interpreting the above A/B test results. "
        "Be data-driven, specific about numbers, and honest about uncertainty. "
        "Surface unexpected patterns and flag any concerns."
    )
    lines.append("")
    lines.append(
        "Return ONLY a JSON object (no markdown fences, no explanation) with exactly this schema:"
    )
    lines.append(
        json.dumps(
            {
                "verdict": "ship | don't ship | run longer",
                "confidence": "0.0-1.0",
                "headline": "one sentence summary of what happened",
                "narrative": "3-4 paragraph story: what moved, what didn't, surprising patterns, business meaning",
                "key_evidence": ["bullet 1", "bullet 2", "bullet 3"],
                "risks": ["risk 1", "risk 2"],
                "follow_up": ["what to investigate next", "..."],
            },
            indent=2,
        )
    )

    return "\n".join(lines)


async def interpret_experiment(
    results: ExperimentResults,
    hypothesis: str,
    target_event: str,
) -> InterpretationResult:
    """Call Claude to interpret pre-computed experiment results and produce a verdict.

    Args:
        results: Pre-computed ExperimentResults including variants, SRM, stat tests, and novelty.
        hypothesis: The original experiment hypothesis string.
        target_event: The primary metric event name.

    Returns:
        InterpretationResult with verdict, confidence, headline, narrative, evidence, risks, and follow-up.

    Raises:
        ValueError: If Claude returns unparseable JSON after retries.
    """
    logger = logging.getLogger(LOGGER_NAME)
    client = _get_anthropic_client()
    prompt = _build_prompt(results, hypothesis, target_event)

    last_error: str = "Unknown error"
    for attempt in range(2):
        response = await client.messages.create(
            model=MODEL_NAME,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )

        text_blocks = [
            block.text
            for block in response.content
            if getattr(block, "type", "") == "text"
        ]
        raw_text = "\n".join(text_blocks).strip()
        cleaned = _strip_markdown_fences(raw_text)

        try:
            payload = json.loads(cleaned)
            verdict = payload.get("verdict", "run longer")
            if verdict not in VALID_VERDICTS:
                verdict = "run longer"

            confidence_raw = payload.get("confidence", 0.5)
            try:
                confidence = float(confidence_raw)
            except (TypeError, ValueError):
                confidence = 0.5
            confidence = max(0.0, min(1.0, confidence))

            return InterpretationResult(
                verdict=verdict,
                confidence=confidence,
                headline=str(payload.get("headline", "")),
                narrative=str(payload.get("narrative", "")),
                key_evidence=[str(e) for e in payload.get("key_evidence", [])],
                risks=[str(r) for r in payload.get("risks", [])],
                follow_up=[str(f) for f in payload.get("follow_up", [])],
            )
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            last_error = str(exc)
            logger.warning(
                "Failed to parse interpretation response on attempt %d: %s",
                attempt + 1,
                last_error,
            )

    raise ValueError(
        f"Claude did not return valid JSON after 2 attempts. Last error: {last_error}"
    )

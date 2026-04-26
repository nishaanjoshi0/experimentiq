"""Post-experiment interpretation API router for ExperimentIQ."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from typing import Final

from fastapi import APIRouter, Form, HTTPException, Request, UploadFile, status
from pydantic import BaseModel

from middleware.rate_limit import llm_limit
from services.experiment_interpreter import InterpretationResult, interpret_experiment
from services.experiment_stats import ExperimentInput, ExperimentResults, analyze_experiment


LOGGER_NAME: Final[str] = "experimentiq.api.experiment_interpret"
ROUTER_PREFIX: Final[str] = "/experiments/interpret"
INTERNAL_SERVER_ERROR_MESSAGE: Final[str] = "An unexpected error occurred."

router = APIRouter(prefix=ROUTER_PREFIX, tags=["experiment-interpret"])


class InterpretResult(BaseModel):
    """Combined response with statistical results and AI interpretation."""

    # --- Statistical results ---
    variants: dict
    srm: dict
    stat_tests: list[dict]
    novelty_warning: bool
    novelty_message: str
    data_source: str

    # --- AI interpretation ---
    verdict: str
    confidence: float
    headline: str
    narrative: str
    key_evidence: list[str]
    risks: list[str]
    follow_up: list[str]


def _results_to_variants_dict(results: ExperimentResults) -> dict:
    """Convert VariantMetrics dataclasses to a plain dict for the response."""
    output: dict = {}
    for name, vm in results.variants.items():
        output[name] = {
            "users": vm.users,
            "conversions": vm.conversions,
            "conversion_rate": vm.conversion_rate,
            "revenue_total": vm.revenue_total,
            "revenue_per_user": vm.revenue_per_user,
            "guardrail_rates": vm.guardrail_rates,
        }
    return output


def _srm_to_dict(results: ExperimentResults) -> dict:
    """Convert SRMResult dataclass to a plain dict for the response."""
    srm = results.srm
    return {
        "passed": srm.passed,
        "chi_square": srm.chi_square,
        "p_value": srm.p_value,
        "observed": srm.observed,
        "expected": srm.expected,
        "message": srm.message,
    }


def _stat_tests_to_list(results: ExperimentResults) -> list[dict]:
    """Convert StatTestResult dataclasses to a list of plain dicts for the response."""
    output: list[dict] = []
    for test in results.stat_tests:
        output.append(
            {
                "metric": test.metric,
                "control_value": test.control_value,
                "treatment_value": test.treatment_value,
                "relative_lift_pct": test.relative_lift_pct,
                "p_value": test.p_value,
                "ci_low_pct": test.ci_low_pct,
                "ci_high_pct": test.ci_high_pct,
                "is_significant": test.is_significant,
            }
        )
    return output


@router.post("/", response_model=InterpretResult)
@llm_limit()
async def interpret_experiment_endpoint(
    request: Request,
    assignment_file: UploadFile,
    events_file: UploadFile,
    hypothesis: str = Form(...),
    target_event: str = Form(...),
    guardrail_events: str = Form(""),
    start_date: str = Form(""),
    end_date: str = Form(""),
    pre_aggregated_json: str = Form(""),
    platform_output_json: str = Form(""),
) -> InterpretResult:
    """Run statistical analysis and AI interpretation on an A/B experiment.

    Accepts raw assignment and events CSV files plus experiment metadata.
    Returns per-variant metrics, SRM check, statistical tests, and a
    structured AI verdict.
    """
    logger = logging.getLogger(LOGGER_NAME)
    user_id = getattr(request.state, "user_id", "anonymous")
    logger.debug(
        "Experiment interpret request received",
        extra={"user_id": user_id},
    )

    try:
        # --- Read file contents and write to temp files ---
        # ExperimentInput.assignment_csv and events_csv are file paths consumed
        # by pd.read_csv(), so we materialise the uploaded bytes as named temp files.
        assignment_bytes = await assignment_file.read()
        events_bytes = await events_file.read()

        assignment_tmp_path: str = ""
        events_tmp_path: str = ""

        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", suffix=".csv", delete=False
            ) as assignment_tmp:
                assignment_tmp.write(assignment_bytes)
                assignment_tmp_path = assignment_tmp.name

            with tempfile.NamedTemporaryFile(
                mode="wb", suffix=".csv", delete=False
            ) as events_tmp:
                events_tmp.write(events_bytes)
                events_tmp_path = events_tmp.name

            # --- Parse guardrail events ---
            parsed_guardrails: list[str] = []
            if guardrail_events.strip():
                parsed_guardrails = [e.strip() for e in guardrail_events.split(",") if e.strip()]

            # --- Parse optional JSON blobs ---
            pre_aggregated: dict | None = None
            if pre_aggregated_json.strip():
                try:
                    pre_aggregated = json.loads(pre_aggregated_json)
                except json.JSONDecodeError as exc:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=f"Invalid JSON in pre_aggregated_json: {exc}",
                    ) from exc

            platform_output: dict | None = None
            if platform_output_json.strip():
                try:
                    platform_output = json.loads(platform_output_json)
                except json.JSONDecodeError as exc:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=f"Invalid JSON in platform_output_json: {exc}",
                    ) from exc

            # --- Build ExperimentInput ---
            inp = ExperimentInput(
                assignment_csv=assignment_tmp_path,
                events_csv=events_tmp_path,
                hypothesis=hypothesis,
                target_event=target_event,
                guardrail_events=parsed_guardrails,
                start_date=start_date if start_date.strip() else None,
                end_date=end_date if end_date.strip() else None,
                pre_aggregated=pre_aggregated,
                platform_output=platform_output,
            )

            # --- Run statistical analysis ---
            results: ExperimentResults = await analyze_experiment(inp)

        finally:
            # Always clean up temp files
            for path in (assignment_tmp_path, events_tmp_path):
                if path and os.path.exists(path):
                    try:
                        os.unlink(path)
                    except OSError:
                        pass

        # --- Run AI interpretation ---
        interpretation: InterpretationResult = await interpret_experiment(
            results=results,
            hypothesis=hypothesis,
            target_event=target_event,
        )

        # --- Assemble response ---
        return InterpretResult(
            variants=_results_to_variants_dict(results),
            srm=_srm_to_dict(results),
            stat_tests=_stat_tests_to_list(results),
            novelty_warning=results.novelty_warning,
            novelty_message=results.novelty_message,
            data_source=results.data_source,
            verdict=interpretation.verdict,
            confidence=interpretation.confidence,
            headline=interpretation.headline,
            narrative=interpretation.narrative,
            key_evidence=interpretation.key_evidence,
            risks=interpretation.risks,
            follow_up=interpretation.follow_up,
        )

    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception(
            "Unexpected error in experiment interpret endpoint",
            extra={"error": str(exc)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=INTERNAL_SERVER_ERROR_MESSAGE,
        ) from exc

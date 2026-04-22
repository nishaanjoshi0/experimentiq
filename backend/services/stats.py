"""Statistical computation utilities for ExperimentIQ."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from statistics import NormalDist
from typing import Final

import numpy as np
from scipy import stats


LOGGER_NAME: Final[str] = "experimentiq.stats"
SRM_P_VALUE_THRESHOLD: Final[float] = 0.01
BASIC_STATS_ALPHA: Final[float] = 0.05
MINIMUM_CUPED_USERS: Final[int] = 10
MINIMUM_VARIATION_SAMPLE_SIZE: Final[int] = 100
MINIMUM_RUNTIME: Final[timedelta] = timedelta(days=1)
DATA_FRESHNESS_WINDOW: Final[timedelta] = timedelta(hours=24)
DEFAULT_TARGET_EFFECT_SIZE: Final[float] = 0.2
STOP_SHIP_RECOMMENDATION: Final[str] = "stop_ship"
STOP_ABANDON_RECOMMENDATION: Final[str] = "stop_abandon"
CONTINUE_RECOMMENDATION: Final[str] = "continue"

_stats_service: StatsService | None = None


@dataclass(frozen=True)
class SRMResult:
    """Result of a sample ratio mismatch check."""

    has_srm: bool
    chi_square_statistic: float
    p_value: float
    observed_counts: dict[str, int]
    expected_counts: dict[str, float]


@dataclass(frozen=True)
class SequentialTestResult:
    """Result of a sequential hypothesis test."""

    can_stop: bool
    current_p_value: float
    spending_boundary: float
    information_fraction: float
    recommendation: str


@dataclass(frozen=True)
class BasicStatsResult:
    """Basic two-sample experiment statistics."""

    control_mean: float
    treatment_mean: float
    relative_lift: float
    absolute_lift: float
    p_value: float
    confidence_interval_lower: float
    confidence_interval_upper: float
    is_significant: bool


@dataclass(frozen=True)
class DataQualityResult:
    """Result of experiment data quality checks."""

    passed: bool
    checks: dict[str, bool]
    failure_reasons: list[str]


@dataclass(frozen=True)
class NoveltyResult:
    """Result of a novelty effect check."""

    has_novelty: bool
    early_window_lift: float
    overall_lift: float
    novelty_ratio: float
    early_window_days: int
    message: str


class StatsServiceError(Exception):
    """Raised when stats computations cannot be completed safely."""

    def __init__(self, message: str) -> None:
        """Initialize the stats service error."""
        super().__init__(message)
        self.message = message


class StatsService:
    """Pure-computation statistical service for experiment analysis."""

    def __init__(self) -> None:
        """Initialize the stats service logger."""
        self._logger = logging.getLogger(LOGGER_NAME)

    def check_srm(
        self,
        observed_counts: dict[str, int],
        expected_splits: dict[str, float],
    ) -> SRMResult:
        """Run a chi-square sample ratio mismatch test."""
        observed_keys = set(observed_counts.keys())
        expected_keys = set(expected_splits.keys())
        if observed_keys != expected_keys:
            raise StatsServiceError("Observed and expected variations must match for SRM check.")

        total_observed = sum(observed_counts.values())
        if total_observed <= 0:
            raise StatsServiceError("Observed counts must sum to a positive value.")

        split_sum = sum(expected_splits.values())
        if split_sum <= 0:
            raise StatsServiceError("Expected splits must sum to a positive value.")

        ordered_variations = sorted(observed_counts.keys())
        observed = np.array([observed_counts[key] for key in ordered_variations], dtype=float)
        normalized_splits = np.array(
            [expected_splits[key] / split_sum for key in ordered_variations],
            dtype=float,
        )
        expected = normalized_splits * total_observed
        chi_square_statistic, p_value = stats.chisquare(f_obs=observed, f_exp=expected)

        return SRMResult(
            has_srm=bool(p_value < SRM_P_VALUE_THRESHOLD),
            chi_square_statistic=float(chi_square_statistic),
            p_value=float(p_value),
            observed_counts={key: observed_counts[key] for key in ordered_variations},
            expected_counts={key: float(expected[index]) for index, key in enumerate(ordered_variations)},
        )

    def apply_cuped(
        self,
        observations: list[dict],
        pre_observations: list[dict],
    ) -> list[dict]:
        """Apply CUPED variance reduction using pre-experiment covariates."""
        pre_by_user = {
            str(item["user_id"]): float(item["pre_value"])
            for item in pre_observations
            if item.get("user_id") is not None and item.get("pre_value") is not None
        }

        matched_rows = [
            row for row in observations if row.get("user_id") is not None and str(row["user_id"]) in pre_by_user
        ]
        if len(matched_rows) < MINIMUM_CUPED_USERS:
            self._logger.warning(
                "Skipping CUPED adjustment due to insufficient pre-experiment data.",
                extra={"matched_user_count": len(matched_rows)},
            )
            return observations

        x = np.array([pre_by_user[str(row["user_id"])] for row in matched_rows], dtype=float)
        y = np.array([float(row["value"]) for row in matched_rows], dtype=float)
        x_mean = float(np.mean(x))
        covariance = float(np.cov(x, y, ddof=1)[0, 1])
        variance = float(np.var(x, ddof=1))

        if math.isclose(variance, 0.0):
            self._logger.warning("Skipping CUPED adjustment because pre-experiment variance is zero.")
            return observations

        theta = covariance / variance
        adjusted_rows: list[dict] = []
        for row in observations:
            user_id = row.get("user_id")
            adjusted_row = dict(row)
            if user_id is not None and str(user_id) in pre_by_user:
                adjusted_row["value"] = float(row["value"]) - theta * (pre_by_user[str(user_id)] - x_mean)
            adjusted_rows.append(adjusted_row)

        return adjusted_rows

    def run_sequential_test(
        self,
        control_values: list[float],
        treatment_values: list[float],
        alpha: float = BASIC_STATS_ALPHA,
        target_power: float = 0.8,
    ) -> SequentialTestResult:
        """Run a sequential test using an O'Brien-Fleming-style stopping rule."""
        control = self._as_float_array(control_values, "control_values")
        treatment = self._as_float_array(treatment_values, "treatment_values")

        current_p_value = float(stats.ttest_ind(control, treatment, equal_var=False).pvalue)
        expected_final_sample_size = self._estimate_expected_final_sample_size(
            control,
            treatment,
            alpha,
            target_power,
        )
        current_sample_size = control.size + treatment.size
        information_fraction = min(current_sample_size / expected_final_sample_size, 1.0)
        spending_boundary = self._obrien_fleming_boundary(alpha, information_fraction)

        effect_direction = float(np.mean(treatment) - np.mean(control))
        if current_p_value <= spending_boundary:
            recommendation = STOP_SHIP_RECOMMENDATION if effect_direction > 0 else STOP_ABANDON_RECOMMENDATION
            can_stop = True
        else:
            recommendation = CONTINUE_RECOMMENDATION
            can_stop = False

        return SequentialTestResult(
            can_stop=can_stop,
            current_p_value=current_p_value,
            spending_boundary=spending_boundary,
            information_fraction=information_fraction,
            recommendation=recommendation,
        )

    def compute_basic_stats(
        self,
        control_values: list[float],
        treatment_values: list[float],
    ) -> BasicStatsResult:
        """Compute Welch's t-test and a 95 percent confidence interval on the difference."""
        control = self._as_float_array(control_values, "control_values")
        treatment = self._as_float_array(treatment_values, "treatment_values")

        control_mean = float(np.mean(control))
        treatment_mean = float(np.mean(treatment))
        absolute_lift = treatment_mean - control_mean
        relative_lift = absolute_lift / control_mean if not math.isclose(control_mean, 0.0) else math.inf

        test_result = stats.ttest_ind(control, treatment, equal_var=False)
        p_value = float(test_result.pvalue)

        control_variance = float(np.var(control, ddof=1))
        treatment_variance = float(np.var(treatment, ddof=1))
        standard_error = math.sqrt((control_variance / control.size) + (treatment_variance / treatment.size))
        degrees_of_freedom = self._welch_satterthwaite_df(
            control_variance,
            treatment_variance,
            control.size,
            treatment.size,
        )
        critical_value = float(stats.t.ppf(1 - (BASIC_STATS_ALPHA / 2), degrees_of_freedom))
        margin_of_error = critical_value * standard_error

        return BasicStatsResult(
            control_mean=control_mean,
            treatment_mean=treatment_mean,
            relative_lift=float(relative_lift),
            absolute_lift=float(absolute_lift),
            p_value=p_value,
            confidence_interval_lower=float(absolute_lift - margin_of_error),
            confidence_interval_upper=float(absolute_lift + margin_of_error),
            is_significant=bool(p_value < BASIC_STATS_ALPHA),
        )

    def run_data_quality_gate(
        self,
        experiment_id: str,
        control_count: int,
        treatment_count: int,
        last_event_timestamp: datetime,
        experiment_start_timestamp: datetime | None = None,
        experiment_status: str | None = None,
    ) -> DataQualityResult:
        """Run core data-quality checks, using experiment start time for runtime when available."""
        _ = experiment_id
        now = datetime.now(timezone.utc)
        normalized_last_event = self._ensure_utc(last_event_timestamp)
        runtime_reference = experiment_start_timestamp or last_event_timestamp
        normalized_runtime_reference = self._ensure_utc(runtime_reference)
        normalized_status = experiment_status.lower() if experiment_status is not None else None
        is_completed_experiment = normalized_status in {"stopped", "completed"}

        checks = {
            "minimum_sample_size": control_count >= MINIMUM_VARIATION_SAMPLE_SIZE
            and treatment_count >= MINIMUM_VARIATION_SAMPLE_SIZE,
            "data_freshness": True
            if is_completed_experiment
            else now - normalized_last_event <= DATA_FRESHNESS_WINDOW,
            "minimum_runtime": True
            if is_completed_experiment
            else now - normalized_runtime_reference >= MINIMUM_RUNTIME,
        }

        failure_reasons: list[str] = []
        if not checks["minimum_sample_size"]:
            failure_reasons.append("Minimum sample size not met for all variations.")
        if not checks["data_freshness"]:
            failure_reasons.append("Data is stale; latest event is older than 24 hours.")
        if not checks["minimum_runtime"]:
            failure_reasons.append("Experiment has not been running for at least 1 day.")

        return DataQualityResult(
            passed=all(checks.values()),
            checks=checks,
            failure_reasons=failure_reasons,
        )

    def check_novelty(
        self,
        daily_treatment_rates: list[float],
        daily_control_rates: list[float],
        early_window_days: int = 3,
        novelty_ratio_threshold: float = 1.5,
    ) -> NoveltyResult:
        """Check whether early experiment lift appears meaningfully larger than overall lift."""
        total_days = min(len(daily_treatment_rates), len(daily_control_rates))
        if total_days < early_window_days + 2:
            return NoveltyResult(
                has_novelty=False,
                early_window_lift=0.0,
                overall_lift=0.0,
                novelty_ratio=0.0,
                early_window_days=early_window_days,
                message="Not enough daily data to evaluate novelty effects yet.",
            )

        treatment = np.asarray(daily_treatment_rates[:total_days], dtype=float)
        control = np.asarray(daily_control_rates[:total_days], dtype=float)
        early_window_lift = float(np.mean(treatment[:early_window_days]) - np.mean(control[:early_window_days]))
        overall_lift = float(np.mean(treatment) - np.mean(control))
        novelty_ratio = (
            float(early_window_lift / overall_lift)
            if overall_lift > 0
            else 0.0
        )
        has_novelty = bool(
            novelty_ratio > novelty_ratio_threshold
            and early_window_lift > 0
            and overall_lift > 0
            and total_days >= early_window_days + 2
        )
        if has_novelty:
            message = (
                "Early lift is meaningfully stronger than the overall lift, suggesting a possible novelty effect."
            )
        else:
            message = "No novelty effect detected from the available daily rate trends."

        return NoveltyResult(
            has_novelty=has_novelty,
            early_window_lift=early_window_lift,
            overall_lift=overall_lift,
            novelty_ratio=novelty_ratio,
            early_window_days=early_window_days,
            message=message,
        )

    def _as_float_array(self, values: list[float], field_name: str) -> np.ndarray:
        """Convert a non-empty list of numeric values into a numpy float array."""
        if len(values) < 2:
            raise StatsServiceError(f"{field_name} must contain at least 2 values.")
        return np.asarray(values, dtype=float)

    def _estimate_expected_final_sample_size(
        self,
        control: np.ndarray,
        treatment: np.ndarray,
        alpha: float,
        target_power: float,
    ) -> float:
        """Estimate expected final sample size for a two-sample comparison."""
        pooled_std = float(
            np.sqrt(((np.var(control, ddof=1) * (control.size - 1)) + (np.var(treatment, ddof=1) * (treatment.size - 1)))
                    / (control.size + treatment.size - 2))
        )
        observed_effect = abs(float(np.mean(treatment) - np.mean(control)))
        effect_size = observed_effect / pooled_std if not math.isclose(pooled_std, 0.0) else DEFAULT_TARGET_EFFECT_SIZE
        effect_size = max(effect_size, DEFAULT_TARGET_EFFECT_SIZE)

        z_alpha = NormalDist().inv_cdf(1 - (alpha / 2))
        z_beta = NormalDist().inv_cdf(target_power)
        per_group = 2 * ((z_alpha + z_beta) ** 2) / (effect_size**2)
        return max(float(math.ceil(per_group * 2)), float(control.size + treatment.size))

    def _obrien_fleming_boundary(self, alpha: float, information_fraction: float) -> float:
        """Compute the O'Brien-Fleming significance boundary at the current information fraction."""
        bounded_information_fraction = max(information_fraction, 1e-6)
        z_alpha = NormalDist().inv_cdf(1 - (alpha / 2))
        critical_value = z_alpha / math.sqrt(bounded_information_fraction)
        return float(2 * (1 - NormalDist().cdf(critical_value)))

    def _welch_satterthwaite_df(
        self,
        control_variance: float,
        treatment_variance: float,
        control_size: int,
        treatment_size: int,
    ) -> float:
        """Compute the Welch-Satterthwaite approximation for degrees of freedom."""
        numerator = (control_variance / control_size + treatment_variance / treatment_size) ** 2
        control_term = ((control_variance / control_size) ** 2) / (control_size - 1)
        treatment_term = ((treatment_variance / treatment_size) ** 2) / (treatment_size - 1)
        denominator = control_term + treatment_term
        if math.isclose(denominator, 0.0, abs_tol=1e-10):
            return float(min(control_size, treatment_size) - 1)
        return numerator / denominator

    def _ensure_utc(self, value: datetime) -> datetime:
        """Normalize a datetime value to timezone-aware UTC."""
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


def get_stats_service() -> StatsService:
    """Return a singleton stats service instance."""
    global _stats_service
    if _stats_service is None:
        _stats_service = StatsService()
    return _stats_service

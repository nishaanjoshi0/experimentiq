"""Post-experiment statistical analysis engine for ExperimentIQ.

Takes raw assignment + event log CSVs (or pre-aggregated data), computes per-variant
metrics, validates sample integrity, and runs hypothesis tests.  No AI — pure
pandas / scipy / numpy.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Final

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SIGNIFICANCE_ALPHA: Final[float] = 0.05
SRM_ALPHA: Final[float] = 0.01
NOVELTY_RATIO_THRESHOLD: Final[float] = 1.3  # early_rate > late_rate * 1.3

# ---------------------------------------------------------------------------
# Input / Output dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ExperimentInput:
    """All inputs needed to drive a full post-experiment analysis."""

    assignment_csv: str        # path — columns: user_id, variant, timestamp
    events_csv: str            # path — columns: user_id, event, value, timestamp
    hypothesis: str
    target_event: str          # e.g. "purchase"
    guardrail_events: list[str]  # e.g. ["refund", "support_ticket"]
    start_date: str | None = None   # ISO date string (inclusive)
    end_date: str | None = None     # ISO date string (inclusive)
    pre_aggregated: dict | None = None  # {variant: {users, conversions, revenue}}
    platform_output: dict | None = None  # {lift_pct, p_value, ci_low, ci_high}


@dataclass
class VariantMetrics:
    """Per-variant computed metrics."""

    name: str
    users: int
    conversions: int
    conversion_rate: float
    revenue_total: float
    revenue_per_user: float
    guardrail_rates: dict[str, float]  # event_name -> rate


@dataclass
class SRMResult:
    """Sample ratio mismatch check result."""

    passed: bool
    chi_square: float
    p_value: float
    observed: dict[str, int]   # variant -> count
    expected: dict[str, int]
    message: str


@dataclass
class StatTestResult:
    """Result of a single statistical hypothesis test."""

    metric: str
    control_value: float
    treatment_value: float
    relative_lift_pct: float
    p_value: float
    ci_low_pct: float    # relative lift 95 % CI lower bound (%)
    ci_high_pct: float   # relative lift 95 % CI upper bound (%)
    is_significant: bool  # p < 0.05


@dataclass
class ExperimentResults:
    """Aggregated results returned by analyze_experiment."""

    variants: dict[str, VariantMetrics]   # variant_name -> metrics
    srm: SRMResult
    stat_tests: list[StatTestResult]
    novelty_warning: bool
    novelty_message: str
    data_source: str       # "raw_logs" | "pre_aggregated" | "platform_output"
    experiment_window: str  # e.g. "2024-01-01 to 2024-01-14"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _r4(value: float) -> float:
    """Round a float to 4 decimal places, returning 0.0 for NaN/inf."""
    if not math.isfinite(value):
        return 0.0
    return round(value, 4)


def _two_prop_ztest(
    conversions_ctrl: int,
    users_ctrl: int,
    conversions_trt: int,
    users_trt: int,
) -> tuple[float, float]:
    """Two-proportion z-test; returns (z_stat, p_value)."""
    p1 = conversions_ctrl / users_ctrl if users_ctrl else 0.0
    p2 = conversions_trt / users_trt if users_trt else 0.0
    p_pool = (conversions_ctrl + conversions_trt) / (users_ctrl + users_trt)
    se = np.sqrt(p_pool * (1 - p_pool) * (1 / users_ctrl + 1 / users_trt))
    if se == 0:
        return 0.0, 1.0
    z_stat = (p2 - p1) / se
    p_value = float(2 * (1 - scipy_stats.norm.cdf(abs(z_stat))))
    return float(z_stat), p_value


def _relative_lift_ci(
    rate_ctrl: float,
    users_ctrl: int,
    rate_trt: float,
    users_trt: int,
    alpha: float = SIGNIFICANCE_ALPHA,
) -> tuple[float, float, float]:
    """
    Compute relative lift (%) and its 95 % CI using normal approximation on the
    absolute difference, then convert to relative terms.

    Returns (relative_lift_pct, ci_low_pct, ci_high_pct).
    """
    if rate_ctrl <= 0 or users_ctrl <= 0 or users_trt <= 0:
        return 0.0, 0.0, 0.0

    abs_diff = rate_trt - rate_ctrl
    se = math.sqrt(
        rate_ctrl * (1 - rate_ctrl) / users_ctrl
        + rate_trt * (1 - rate_trt) / users_trt
    )
    z_crit = float(scipy_stats.norm.ppf(1 - alpha / 2))
    margin = z_crit * se

    rel_lift = abs_diff / rate_ctrl * 100
    ci_low = (abs_diff - margin) / rate_ctrl * 100
    ci_high = (abs_diff + margin) / rate_ctrl * 100
    return _r4(rel_lift), _r4(ci_low), _r4(ci_high)


def _revenue_lift_ci(
    mean_ctrl: float,
    mean_trt: float,
    se: float,
    alpha: float = SIGNIFICANCE_ALPHA,
) -> tuple[float, float, float]:
    """
    Convert absolute revenue-per-user difference + SE into relative lift CI (%).
    Returns (relative_lift_pct, ci_low_pct, ci_high_pct).
    """
    if mean_ctrl <= 0:
        return 0.0, 0.0, 0.0

    z_crit = float(scipy_stats.norm.ppf(1 - alpha / 2))
    margin = z_crit * se
    abs_diff = mean_trt - mean_ctrl
    rel_lift = abs_diff / mean_ctrl * 100
    ci_low = (abs_diff - margin) / mean_ctrl * 100
    ci_high = (abs_diff + margin) / mean_ctrl * 100
    return _r4(rel_lift), _r4(ci_low), _r4(ci_high)


def _choose_control(variant_names: list[str]) -> str:
    """Return the control variant name: prefer 'control'/'Control', else first alpha."""
    for name in variant_names:
        if name.lower() == "control":
            return name
    return sorted(variant_names)[0]


def _require_columns(df: pd.DataFrame, required: list[str], context: str) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            f"{context}: missing required column(s): {missing}. "
            f"Found: {list(df.columns)}"
        )


# ---------------------------------------------------------------------------
# SRM helper
# ---------------------------------------------------------------------------


def _compute_srm(user_counts: dict[str, int]) -> SRMResult:
    """Chi-square SRM test assuming equal expected split across all variants."""
    variants = sorted(user_counts.keys())
    n_variants = len(variants)
    total = sum(user_counts.values())

    if total == 0:
        return SRMResult(
            passed=False,
            chi_square=0.0,
            p_value=0.0,
            observed={v: user_counts[v] for v in variants},
            expected={v: 0 for v in variants},
            message="No users observed — cannot perform SRM check.",
        )

    expected_count = total / n_variants
    observed_arr = np.array([user_counts[v] for v in variants], dtype=float)
    expected_arr = np.full(n_variants, expected_count, dtype=float)

    chi2, p_value = scipy_stats.chisquare(f_obs=observed_arr, f_exp=expected_arr)
    chi2, p_value = float(chi2), float(p_value)
    passed = p_value > SRM_ALPHA

    expected_rounded = {v: int(round(expected_count)) for v in variants}
    if passed:
        msg = (
            f"SRM check passed (chi2={_r4(chi2)}, p={_r4(p_value)}). "
            "User distribution looks as expected."
        )
    else:
        msg = (
            f"SRM check FAILED (chi2={_r4(chi2)}, p={_r4(p_value)}). "
            "Observed user counts deviate significantly from expected equal split — "
            "results may be unreliable."
        )

    return SRMResult(
        passed=passed,
        chi_square=_r4(chi2),
        p_value=_r4(p_value),
        observed={v: user_counts[v] for v in variants},
        expected=expected_rounded,
        message=msg,
    )


# ---------------------------------------------------------------------------
# Path 1: platform_output passthrough
# ---------------------------------------------------------------------------


def _results_from_platform_output(inp: ExperimentInput) -> ExperimentResults:
    po = inp.platform_output or {}
    dummy_srm = SRMResult(
        passed=True,
        chi_square=0.0,
        p_value=1.0,
        observed={},
        expected={},
        message="SRM not computed — using platform output.",
    )
    stat = StatTestResult(
        metric=inp.target_event,
        control_value=0.0,
        treatment_value=0.0,
        relative_lift_pct=_r4(float(po.get("lift_pct", 0.0))),
        p_value=_r4(float(po.get("p_value", 1.0))),
        ci_low_pct=_r4(float(po.get("ci_low", 0.0))),
        ci_high_pct=_r4(float(po.get("ci_high", 0.0))),
        is_significant=float(po.get("p_value", 1.0)) < SIGNIFICANCE_ALPHA,
    )
    return ExperimentResults(
        variants={},
        srm=dummy_srm,
        stat_tests=[stat],
        novelty_warning=False,
        novelty_message="Novelty check not available with platform output.",
        data_source="platform_output",
        experiment_window="N/A",
    )


# ---------------------------------------------------------------------------
# Path 2: pre_aggregated
# ---------------------------------------------------------------------------


def _results_from_pre_aggregated(inp: ExperimentInput) -> ExperimentResults:
    pa: dict = inp.pre_aggregated or {}
    if not pa:
        raise ValueError("pre_aggregated is empty.")

    variant_names = list(pa.keys())
    control_name = _choose_control(variant_names)
    treatment_names = [v for v in variant_names if v != control_name]

    # Build VariantMetrics
    variant_metrics: dict[str, VariantMetrics] = {}
    for vname, vdata in pa.items():
        users = int(vdata.get("users", 0))
        conversions = int(vdata.get("conversions", 0))
        revenue = float(vdata.get("revenue", 0.0))
        cr = conversions / users if users > 0 else 0.0
        rpu = revenue / users if users > 0 else 0.0
        variant_metrics[vname] = VariantMetrics(
            name=vname,
            users=users,
            conversions=conversions,
            conversion_rate=_r4(cr),
            revenue_total=_r4(revenue),
            revenue_per_user=_r4(rpu),
            guardrail_rates={},
        )

    # SRM
    user_counts = {v: variant_metrics[v].users for v in variant_names}
    srm = _compute_srm(user_counts)

    # Stat tests — two-proportion z-test for conversion only
    ctrl = variant_metrics[control_name]
    stat_tests: list[StatTestResult] = []

    for trt_name in treatment_names:
        trt = variant_metrics[trt_name]
        label = f"{inp.target_event} (conversion_rate) [{trt_name} vs {control_name}]"
        if ctrl.users > 0 and trt.users > 0:
            _, p_val = _two_prop_ztest(
                ctrl.conversions, ctrl.users, trt.conversions, trt.users
            )
            rel_lift, ci_low, ci_high = _relative_lift_ci(
                ctrl.conversion_rate, ctrl.users,
                trt.conversion_rate, trt.users,
            )
        else:
            p_val, rel_lift, ci_low, ci_high = 1.0, 0.0, 0.0, 0.0

        stat_tests.append(
            StatTestResult(
                metric=label,
                control_value=ctrl.conversion_rate,
                treatment_value=trt.conversion_rate,
                relative_lift_pct=rel_lift,
                p_value=_r4(p_val),
                ci_low_pct=ci_low,
                ci_high_pct=ci_high,
                is_significant=p_val < SIGNIFICANCE_ALPHA,
            )
        )

    return ExperimentResults(
        variants=variant_metrics,
        srm=srm,
        stat_tests=stat_tests,
        novelty_warning=False,
        novelty_message="Novelty check requires raw CSV logs.",
        data_source="pre_aggregated",
        experiment_window="N/A",
    )


# ---------------------------------------------------------------------------
# Path 3: raw CSVs (main path)
# ---------------------------------------------------------------------------


def _parse_assignments(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    df.columns = [c.strip().lower() for c in df.columns]
    _require_columns(df, ["user_id", "variant", "timestamp"], "assignment_csv")
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df["user_id"] = df["user_id"].astype(str)
    df["variant"] = df["variant"].astype(str)
    return df


def _parse_events(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    df.columns = [c.strip().lower() for c in df.columns]
    _require_columns(df, ["user_id", "event", "timestamp"], "events_csv")
    if "value" not in df.columns:
        df["value"] = 0.0
    df["value"] = pd.to_numeric(df["value"], errors="coerce").fillna(0.0)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df["user_id"] = df["user_id"].astype(str)
    df["event"] = df["event"].astype(str)
    return df


def _apply_window(
    assignments: pd.DataFrame,
    events: pd.DataFrame,
    start_date: str | None,
    end_date: str | None,
) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """Filter both dataframes to the experiment window; return window label."""
    start_ts = pd.Timestamp(start_date, tz="UTC") if start_date else None
    end_ts = (
        pd.Timestamp(end_date, tz="UTC") + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        if end_date
        else None
    )

    if end_ts is not None:
        assignments = assignments[assignments["timestamp"] <= end_ts].copy()
    if start_ts is not None:
        events = events[events["timestamp"] >= start_ts].copy()
    if end_ts is not None:
        events = events[events["timestamp"] <= end_ts].copy()

    # Derive window label from data if not specified
    all_ts = pd.concat(
        [assignments["timestamp"].dropna(), events["timestamp"].dropna()]
    )
    if len(all_ts) > 0:
        actual_start = all_ts.min().strftime("%Y-%m-%d")
        actual_end = all_ts.max().strftime("%Y-%m-%d")
        window_str = f"{actual_start} to {actual_end}"
    else:
        window_str = f"{start_date or 'unknown'} to {end_date or 'unknown'}"

    return assignments, events, window_str


def _build_variant_metrics(
    assignments: pd.DataFrame,
    events: pd.DataFrame,
    target_event: str,
    guardrail_events: list[str],
) -> dict[str, VariantMetrics]:
    """Build per-variant metrics from the joined assignment + events data."""
    # Left-join events onto assignments so every assigned user is preserved
    merged = assignments.merge(events, on="user_id", how="left", suffixes=("_assign", "_event"))

    variant_metrics: dict[str, VariantMetrics] = {}
    for variant_name, grp in assignments.groupby("variant"):
        variant_users = grp["user_id"].unique()
        n_users = len(variant_users)

        variant_events = merged[merged["variant"] == variant_name]

        # Conversions: users with at least one target_event
        target_rows = variant_events[variant_events["event"] == target_event]
        converted_users = target_rows["user_id"].nunique()
        cr = converted_users / n_users if n_users > 0 else 0.0

        # Revenue
        revenue_total = float(target_rows["value"].sum())
        rpu = revenue_total / n_users if n_users > 0 else 0.0

        # Guardrail rates
        guardrail_rates: dict[str, float] = {}
        for ge in guardrail_events:
            ge_rows = variant_events[variant_events["event"] == ge]
            users_with_ge = ge_rows["user_id"].nunique()
            guardrail_rates[ge] = _r4(users_with_ge / n_users if n_users > 0 else 0.0)

        variant_metrics[str(variant_name)] = VariantMetrics(
            name=str(variant_name),
            users=n_users,
            conversions=int(converted_users),
            conversion_rate=_r4(cr),
            revenue_total=_r4(revenue_total),
            revenue_per_user=_r4(rpu),
            guardrail_rates=guardrail_rates,
        )

    return variant_metrics


def _build_per_user_revenue(
    assignments: pd.DataFrame,
    events: pd.DataFrame,
    target_event: str,
    variant: str,
) -> np.ndarray:
    """Return a per-user revenue array for `variant` (0 for non-converting users)."""
    variant_users = assignments.loc[assignments["variant"] == variant, "user_id"].unique()
    target_rows = events[events["event"] == target_event].copy()
    revenue_by_user = target_rows.groupby("user_id")["value"].sum()
    user_revenues = np.array(
        [float(revenue_by_user.get(uid, 0.0)) for uid in variant_users],
        dtype=float,
    )
    return user_revenues


def _compute_stat_tests(
    assignments: pd.DataFrame,
    events: pd.DataFrame,
    variant_metrics: dict[str, VariantMetrics],
    control_name: str,
    target_event: str,
    guardrail_events: list[str],
) -> list[StatTestResult]:
    """Run statistical tests for target and guardrail metrics."""
    treatment_names = [v for v in variant_metrics if v != control_name]
    ctrl = variant_metrics[control_name]
    stat_tests: list[StatTestResult] = []

    for trt_name in treatment_names:
        trt = variant_metrics[trt_name]

        # --- Conversion rate: two-proportion z-test ---
        if ctrl.users > 0 and trt.users > 0:
            _, p_conv = _two_prop_ztest(
                ctrl.conversions, ctrl.users,
                trt.conversions, trt.users,
            )
            rel_lift, ci_low, ci_high = _relative_lift_ci(
                ctrl.conversion_rate, ctrl.users,
                trt.conversion_rate, trt.users,
            )
        else:
            p_conv, rel_lift, ci_low, ci_high = 1.0, 0.0, 0.0, 0.0

        stat_tests.append(
            StatTestResult(
                metric=f"{target_event} (conversion_rate) [{trt_name} vs {control_name}]",
                control_value=ctrl.conversion_rate,
                treatment_value=trt.conversion_rate,
                relative_lift_pct=rel_lift,
                p_value=_r4(p_conv),
                ci_low_pct=ci_low,
                ci_high_pct=ci_high,
                is_significant=p_conv < SIGNIFICANCE_ALPHA,
            )
        )

        # --- Revenue per user: Welch's t-test ---
        ctrl_rev = _build_per_user_revenue(assignments, events, target_event, control_name)
        trt_rev = _build_per_user_revenue(assignments, events, target_event, trt_name)

        if len(ctrl_rev) >= 2 and len(trt_rev) >= 2:
            t_res = scipy_stats.ttest_ind(ctrl_rev, trt_rev, equal_var=False)
            p_rev = float(t_res.pvalue)
            mean_ctrl = float(np.mean(ctrl_rev))
            mean_trt = float(np.mean(trt_rev))
            # SE of the difference for CI
            se_rev = math.sqrt(
                float(np.var(ctrl_rev, ddof=1)) / len(ctrl_rev)
                + float(np.var(trt_rev, ddof=1)) / len(trt_rev)
            )
            rel_lift_rev, ci_low_rev, ci_high_rev = _revenue_lift_ci(
                mean_ctrl, mean_trt, se_rev
            )
        else:
            p_rev = 1.0
            mean_ctrl = ctrl.revenue_per_user
            mean_trt = trt.revenue_per_user
            rel_lift_rev, ci_low_rev, ci_high_rev = 0.0, 0.0, 0.0

        stat_tests.append(
            StatTestResult(
                metric=f"{target_event} (revenue_per_user) [{trt_name} vs {control_name}]",
                control_value=_r4(mean_ctrl),
                treatment_value=_r4(mean_trt),
                relative_lift_pct=rel_lift_rev,
                p_value=_r4(p_rev),
                ci_low_pct=ci_low_rev,
                ci_high_pct=ci_high_rev,
                is_significant=p_rev < SIGNIFICANCE_ALPHA,
            )
        )

        # --- Guardrail events: two-proportion z-test ---
        for ge in guardrail_events:
            ctrl_ge_rate = ctrl.guardrail_rates.get(ge, 0.0)
            trt_ge_rate = trt.guardrail_rates.get(ge, 0.0)
            ctrl_ge_conv = round(ctrl_ge_rate * ctrl.users)
            trt_ge_conv = round(trt_ge_rate * trt.users)

            if ctrl.users > 0 and trt.users > 0:
                _, p_ge = _two_prop_ztest(
                    ctrl_ge_conv, ctrl.users,
                    trt_ge_conv, trt.users,
                )
                rel_ge, ci_low_ge, ci_high_ge = _relative_lift_ci(
                    ctrl_ge_rate, ctrl.users,
                    trt_ge_rate, trt.users,
                )
            else:
                p_ge, rel_ge, ci_low_ge, ci_high_ge = 1.0, 0.0, 0.0, 0.0

            stat_tests.append(
                StatTestResult(
                    metric=f"{ge} (guardrail_rate) [{trt_name} vs {control_name}]",
                    control_value=ctrl_ge_rate,
                    treatment_value=trt_ge_rate,
                    relative_lift_pct=rel_ge,
                    p_value=_r4(p_ge),
                    ci_low_pct=ci_low_ge,
                    ci_high_pct=ci_high_ge,
                    is_significant=p_ge < SIGNIFICANCE_ALPHA,
                )
            )

    return stat_tests


def _check_novelty(
    assignments: pd.DataFrame,
    events: pd.DataFrame,
    target_event: str,
    treatment_name: str,
) -> tuple[bool, str]:
    """
    Split the experiment window in half (by event timestamp) and compare
    the treatment conversion rate in the first half vs the second half.
    Warning triggered if early_rate > late_rate * NOVELTY_RATIO_THRESHOLD.
    """
    trt_users = assignments.loc[assignments["variant"] == treatment_name, "user_id"].unique()
    trt_target = events[
        (events["user_id"].isin(trt_users)) & (events["event"] == target_event)
    ].copy()

    if trt_target.empty or trt_target["timestamp"].isna().all():
        return False, "Insufficient event data to evaluate novelty effect."

    ts_min = trt_target["timestamp"].min()
    ts_max = trt_target["timestamp"].max()
    midpoint = ts_min + (ts_max - ts_min) / 2

    early_target = trt_target[trt_target["timestamp"] <= midpoint]
    late_target = trt_target[trt_target["timestamp"] > midpoint]

    # Count users in each half based on assignment timestamps (all treatment users eligible)
    n_total = len(trt_users)
    if n_total == 0:
        return False, "No treatment users — novelty check skipped."

    early_users_converting = early_target["user_id"].nunique()
    late_users_converting = late_target["user_id"].nunique()

    early_rate = early_users_converting / n_total
    late_rate = late_users_converting / n_total

    if late_rate > 0 and early_rate > late_rate * NOVELTY_RATIO_THRESHOLD:
        msg = (
            f"Novelty effect detected: early conversion rate ({_r4(early_rate)}) "
            f"is more than {int(NOVELTY_RATIO_THRESHOLD * 100)}% higher than "
            f"late conversion rate ({_r4(late_rate)}). "
            "Results may be inflated by novelty bias."
        )
        return True, msg

    return False, (
        f"No novelty effect detected (early_rate={_r4(early_rate)}, "
        f"late_rate={_r4(late_rate)})."
    )


def _results_from_raw_csvs(inp: ExperimentInput) -> ExperimentResults:
    """Main analysis path: parse CSVs, join, compute metrics and tests."""
    assignments = _parse_assignments(inp.assignment_csv)
    events = _parse_events(inp.events_csv)

    if assignments.empty:
        raise ValueError("assignment_csv is empty — no users to analyse.")

    # Filter to experiment window
    assignments, events, window_str = _apply_window(
        assignments, events, inp.start_date, inp.end_date
    )

    if assignments.empty:
        raise ValueError(
            "No assignments remain after applying the date window filter."
        )

    # Build variant metrics
    variant_metrics = _build_variant_metrics(
        assignments, events, inp.target_event, inp.guardrail_events
    )

    if not variant_metrics:
        raise ValueError("No variants found in the assignment data.")

    variant_names = list(variant_metrics.keys())
    control_name = _choose_control(variant_names)
    treatment_names = [v for v in variant_names if v != control_name]

    # SRM
    user_counts = {v: variant_metrics[v].users for v in variant_names}
    srm = _compute_srm(user_counts)

    # Stat tests
    stat_tests = _compute_stat_tests(
        assignments, events, variant_metrics,
        control_name, inp.target_event, inp.guardrail_events,
    )

    # Novelty check — use first treatment variant
    if treatment_names:
        novelty_warning, novelty_message = _check_novelty(
            assignments, events, inp.target_event, treatment_names[0]
        )
    else:
        novelty_warning = False
        novelty_message = "No treatment variant found — novelty check skipped."

    return ExperimentResults(
        variants=variant_metrics,
        srm=srm,
        stat_tests=stat_tests,
        novelty_warning=novelty_warning,
        novelty_message=novelty_message,
        data_source="raw_logs",
        experiment_window=window_str,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def analyze_experiment(inp: ExperimentInput) -> ExperimentResults:
    """
    Post-experiment statistical analysis engine.

    Dispatch order:
      1. platform_output provided  -> passthrough (no computation)
      2. pre_aggregated provided   -> two-proportion z-test on aggregates + SRM
      3. raw CSVs                  -> full pipeline (parse, filter, join, metrics, tests)

    All float fields in the returned dataclasses are rounded to 4 decimal places.
    """
    if inp.platform_output is not None:
        return _results_from_platform_output(inp)

    if inp.pre_aggregated is not None:
        return _results_from_pre_aggregated(inp)

    return _results_from_raw_csvs(inp)

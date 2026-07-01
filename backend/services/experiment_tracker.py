"""Daily experiment tracking job.

For each user with connected platforms:
1. Fetch all active experiments from GrowthBook / LaunchDarkly / Statsig
2. Run monitoring reports (SRM, novelty, sequential testing, recommendation)
3. Store snapshots + reports in SQLite
4. Email the daily summary via SendGrid
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from services.db import get_db
from services.oauth_store import (
    _exp_platform_store,
    _platform_store,
    _store as _ga4_store,
    get_exp_platform_connection,
    get_ga4_connection,
)

_logger = logging.getLogger("experimentiq.tracker")

NOTIFY_EMAIL = os.getenv("NOTIFY_TO_EMAIL", "")


# ── Experiment fetching ───────────────────────────────────────────────────────

async def _fetch_platform_experiments(user_id: str) -> dict[str, list[dict]]:
    """Return {platform: [experiments]} for all connected platforms."""
    results: dict[str, list[dict]] = {}

    # GrowthBook (always attempt)
    try:
        from services.growthbook import get_growthbook_client
        exps = await get_growthbook_client().list_experiments()
        results["growthbook"] = [e for e in exps if e.get("status") == "running"]
    except Exception as exc:
        _logger.warning("GrowthBook fetch failed for %s: %s", user_id, exc)

    # LaunchDarkly
    ld_conn = get_exp_platform_connection(user_id, "launchdarkly")
    if ld_conn:
        try:
            from services.launchdarkly import LaunchDarklyClient
            client = LaunchDarklyClient(
                access_token=ld_conn.api_key,
                project_key=ld_conn.extra.get("project_key") or "default",
                environment_key=ld_conn.extra.get("environment_key") or "test",
            )
            exps = await client.list_experiments()
            results["launchdarkly"] = [e for e in exps if e.get("status") == "running"]
            await client.close()
        except Exception as exc:
            _logger.warning("LaunchDarkly fetch failed for %s: %s", user_id, exc)

    # Statsig
    statsig_conn = get_exp_platform_connection(user_id, "statsig")
    if statsig_conn:
        try:
            from services.statsig import StatsigClient
            client = StatsigClient(secret=statsig_conn.api_key)
            exps = await client.list_experiments()
            results["statsig"] = [e for e in exps if e.get("status") == "running"]
        except Exception as exc:
            _logger.warning("Statsig fetch failed for %s: %s", user_id, exc)

    return results


# ── Monitoring per experiment ─────────────────────────────────────────────────

async def _monitor_experiment(experiment_id: str) -> dict[str, Any] | None:
    """Run the monitoring pipeline for a single GrowthBook experiment."""
    try:
        from agents.monitoring_agent import run_monitoring_agent
        result = await run_monitoring_agent(experiment_id)
        if result:
            return {
                "health_status": result.health_status,
                "summary": result.summary,
                "suggested_actions": result.suggested_actions,
                "has_srm": result.srm_check.has_srm if result.srm_check else False,
                "can_stop": result.sequential_test.can_stop if result.sequential_test else False,
                "stop_recommendation": result.sequential_test.recommendation if result.sequential_test else "",
                "confidence": result.confidence,
            }
    except Exception as exc:
        _logger.debug("Monitoring skipped for %s: %s", experiment_id, exc)
    return None


# ── Main daily job ────────────────────────────────────────────────────────────

async def run_daily_job() -> None:
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    _logger.info("Daily tracker job started for %s", today)

    all_user_ids = set()
    all_user_ids.update(_exp_platform_store.keys())
    all_user_ids.update(_platform_store.keys())
    all_user_ids.update(_ga4_store.keys())

    if not all_user_ids:
        _logger.info("No connected users — skipping daily job")
        return

    db = await get_db()
    try:
        for user_id in all_user_ids:
            _logger.info("Processing user %s", user_id)
            platform_experiments = await _fetch_platform_experiments(user_id)

            email_sections: list[dict] = []

            for platform, experiments in platform_experiments.items():
                section_exps: list[dict] = []

                for exp in experiments:
                    exp_id = exp.get("id", "")
                    exp_name = exp.get("name", "Untitled")

                    # Run monitoring (only works for GrowthBook which has metric data)
                    monitoring = None
                    if platform == "growthbook" and exp_id:
                        monitoring = await _monitor_experiment(exp_id)

                    # Build section entry
                    entry: dict[str, Any] = {
                        "name": exp_name,
                        "health_status": monitoring["health_status"] if monitoring else "unknown",
                        "summary": monitoring["summary"] if monitoring else f"Experiment is {exp.get('status','running')} in {platform}.",
                        "suggested_actions": monitoring["suggested_actions"] if monitoring else [],
                        "has_srm": monitoring["has_srm"] if monitoring else False,
                        "can_stop": monitoring["can_stop"] if monitoring else False,
                        "stop_recommendation": monitoring["stop_recommendation"] if monitoring else "",
                    }
                    section_exps.append(entry)

                    # Snapshot to DB
                    await db.execute(
                        """INSERT INTO experiment_snapshots
                           (user_id, platform, experiment_id, experiment_name, status, snapshot_date, raw_json)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (user_id, platform, exp_id, exp_name,
                         exp.get("status", "running"), today,
                         json.dumps({**exp, "monitoring": monitoring})),
                    )

                email_sections.append({"platform": platform, "experiments": section_exps})

            total_experiments = sum(len(s["experiments"]) for s in email_sections)

            # Store daily report
            await db.execute(
                """INSERT INTO daily_reports
                   (user_id, report_date, experiment_count, opportunities_json)
                   VALUES (?, ?, ?, ?)""",
                (user_id, today, total_experiments, json.dumps(email_sections)),
            )

            # Send email
            to_email = NOTIFY_EMAIL or _resolve_user_email(user_id)
            sent = False
            if to_email and email_sections:
                from services.notifier import send_daily_report
                sent = await send_daily_report(
                    to_email=to_email,
                    report_date=today,
                    sections=email_sections,
                )

            await db.execute(
                "UPDATE daily_reports SET notification_sent=? WHERE user_id=? AND report_date=?",
                (1 if sent else 0, user_id, today),
            )
            await db.commit()

            _logger.info(
                "User %s: %d experiments across %d platforms, email_sent=%s",
                user_id, total_experiments, len(email_sections), sent,
            )

    finally:
        await db.close()

    _logger.info("Daily tracker job complete for %s", today)


def _resolve_user_email(user_id: str) -> str:
    """Try to get the user's email from Clerk (best-effort)."""
    # For now return empty — email stored in NOTIFY_TO_EMAIL env var.
    # When Clerk management API is wired, look up by user_id here.
    return ""

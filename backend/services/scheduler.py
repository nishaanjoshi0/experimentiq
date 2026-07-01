"""APScheduler setup for ExperimentIQ background jobs."""

from __future__ import annotations

import asyncio
import logging
import os

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

_logger = logging.getLogger("experimentiq.scheduler")

_scheduler: AsyncIOScheduler | None = None

DAILY_JOB_HOUR = int(os.getenv("DAILY_JOB_HOUR_UTC", "11"))   # 6 AM EST = 11 AM UTC
DAILY_JOB_MINUTE = int(os.getenv("DAILY_JOB_MINUTE_UTC", "0"))


async def _run_daily_tracker() -> None:
    from services.experiment_tracker import run_daily_job
    try:
        await run_daily_job()
    except Exception as exc:
        _logger.error("Daily tracker job raised: %s", exc, exc_info=True)


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return

    _scheduler = AsyncIOScheduler(timezone="UTC")
    _scheduler.add_job(
        _run_daily_tracker,
        trigger=CronTrigger(hour=DAILY_JOB_HOUR, minute=DAILY_JOB_MINUTE, timezone="UTC"),
        id="daily_experiment_tracker",
        name="Daily experiment snapshot + AI analysis",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    _scheduler.start()
    _logger.info(
        "Scheduler started — daily job runs at %02d:%02d UTC",
        DAILY_JOB_HOUR, DAILY_JOB_MINUTE,
    )


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def get_scheduler() -> AsyncIOScheduler | None:
    return _scheduler

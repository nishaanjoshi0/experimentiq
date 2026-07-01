"""Reports API — daily snapshots and analysis history."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from services.db import get_db
from services.scheduler import get_scheduler

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/history")
async def get_report_history(request: Request, limit: int = 30):
    """Return the last N daily reports for the authenticated user."""
    user_id = getattr(request.state, "user_id", "anonymous")
    db = await get_db()
    try:
        cursor = await db.execute(
            """
            SELECT report_date, analytics_platform, experiment_count,
                   opportunities_json, notification_sent, created_at
            FROM daily_reports
            WHERE user_id = ?
            ORDER BY report_date DESC
            LIMIT ?
            """,
            (user_id, limit),
        )
        rows = await cursor.fetchall()
        return [
            {
                "report_date": row["report_date"],
                "analytics_platform": row["analytics_platform"],
                "experiment_count": row["experiment_count"],
                "opportunities": json.loads(row["opportunities_json"])
                if row["opportunities_json"]
                else None,
                "notification_sent": bool(row["notification_sent"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]
    finally:
        await db.close()


@router.get("/snapshots")
async def get_experiment_snapshots(request: Request, days: int = 7):
    """Return experiment snapshots for the last N days."""
    user_id = getattr(request.state, "user_id", "anonymous")
    db = await get_db()
    try:
        cursor = await db.execute(
            """
            SELECT platform, experiment_id, experiment_name, status,
                   snapshot_date, raw_json
            FROM experiment_snapshots
            WHERE user_id = ?
            ORDER BY snapshot_date DESC, platform, experiment_name
            LIMIT 500
            """,
            (user_id,),
        )
        rows = await cursor.fetchall()

        # Group by date
        by_date: dict[str, list] = {}
        for row in rows:
            date = row["snapshot_date"]
            by_date.setdefault(date, []).append({
                "platform": row["platform"],
                "experiment_id": row["experiment_id"],
                "name": row["experiment_name"],
                "status": row["status"],
            })
        return {"snapshots_by_date": by_date}
    finally:
        await db.close()


@router.post("/run-now")
async def trigger_daily_job(request: Request):
    """Manually trigger the daily job. Accepts Clerk JWT or ADMIN_SECRET header."""
    admin_secret = os.getenv("ADMIN_SECRET", "")
    provided = request.headers.get("X-Admin-Secret", "")
    user_id = getattr(request.state, "user_id", None)

    if not user_id and (not admin_secret or provided != admin_secret):
        raise HTTPException(status_code=401, detail="Unauthorized")

    from services.experiment_tracker import run_daily_job
    try:
        await run_daily_job()
        return {"status": "ok", "message": "Daily job completed."}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/scheduler-status")
async def scheduler_status(request: Request):
    """Return next scheduled run time."""
    scheduler = get_scheduler()
    if not scheduler:
        return {"running": False}
    jobs = scheduler.get_jobs()
    next_run = None
    for job in jobs:
        if job.id == "daily_experiment_tracker":
            next_run = job.next_run_time.isoformat() if job.next_run_time else None
    return {"running": True, "next_run_utc": next_run}

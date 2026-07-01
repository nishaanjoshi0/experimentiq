"""SQLite database for persistent experiment snapshots and daily reports."""

from __future__ import annotations

import os
from pathlib import Path

import aiosqlite

_DB_PATH = Path(os.getenv("CREDENTIAL_STORE_PATH", "/app/data/creds.json")).parent / "snapshots.db"


async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(_DB_PATH)
    db.row_factory = aiosqlite.Row
    return db


async def init_db() -> None:
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS experiment_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                platform TEXT NOT NULL,
                experiment_id TEXT NOT NULL,
                experiment_name TEXT NOT NULL,
                status TEXT NOT NULL,
                snapshot_date TEXT NOT NULL,
                raw_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_snapshots_user_date
                ON experiment_snapshots(user_id, snapshot_date);

            CREATE TABLE IF NOT EXISTS daily_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                report_date TEXT NOT NULL,
                analytics_platform TEXT,
                opportunities_json TEXT,
                experiment_count INTEGER DEFAULT 0,
                notification_sent INTEGER DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_reports_user_date
                ON daily_reports(user_id, report_date);
        """)
        await db.commit()

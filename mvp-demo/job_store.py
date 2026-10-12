"""Local task index; uploaded files and reports remain in their scan directories."""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any


def _connect(root: Path) -> sqlite3.Connection:
    root.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(root / "jobs.sqlite3", timeout=20)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS jobs ("
        "job_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, scan_id TEXT, metadata TEXT NOT NULL)"
    )
    connection.execute('CREATE TABLE IF NOT EXISTS submissions (key TEXT PRIMARY KEY, signature TEXT, job_id TEXT)')
    return connection


def save(root: Path, job: dict[str, Any], submission=None) -> None:
    metadata = {key: value for key, value in job.items()
                if key not in {"payload", "uploads", "runtime_dir", "result"}}
    with closing(_connect(root)) as connection, connection:
        if submission:
            connection.execute('INSERT INTO submissions VALUES(?,?,?)',(*submission,job['job_id']))
        connection.execute(
            "INSERT INTO jobs(job_id, created_at, scan_id, metadata) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(job_id) DO UPDATE SET scan_id=excluded.scan_id, metadata=excluded.metadata",
            (job["job_id"], job["created_at"], job.get("scan_id"),
             json.dumps(metadata, ensure_ascii=False)),
        )


def submission(root, key):
    with closing(_connect(root)) as connection:
        row=connection.execute('SELECT signature,job_id FROM submissions WHERE key=?',(key,)).fetchone()
    return row


def family(root, paper_id):
    with closing(_connect(root)) as connection:
        rows=connection.execute('SELECT metadata FROM jobs').fetchall()
    return [job for row in rows if (job:=json.loads(row[0])).get('paper_id',job['job_id'])==paper_id]


def get(root: Path, job_id: str) -> dict[str, Any] | None:
    with closing(_connect(root)) as connection:
        row = connection.execute("SELECT metadata FROM jobs WHERE job_id=?", (job_id,)).fetchone()
    return json.loads(row[0]) if row else None


def list_jobs(root: Path, limit: int = 50) -> list[dict[str, Any]]:
    with closing(_connect(root)) as connection:
        rows = connection.execute(
            "SELECT metadata FROM jobs ORDER BY created_at DESC, job_id DESC LIMIT ?",
            (max(1, min(limit, 200)),),
        ).fetchall()
    return [json.loads(row[0]) for row in rows]


def recover_interrupted(root: Path, finished_at: str) -> None:
    with closing(_connect(root)) as connection, connection:
        rows = connection.execute("SELECT job_id, metadata FROM jobs").fetchall()
        for job_id, encoded in rows:
            job = json.loads(encoded)
            if job.get("status") in {"queued", "running", "cancelling"}:
                job.update(status="failed", finished_at=finished_at,
                           error="上次检查因服务关闭而中断，请重新提交材料。")
                connection.execute("UPDATE jobs SET metadata=? WHERE job_id=?",
                                   (json.dumps(job, ensure_ascii=False), job_id))


def known_scan_ids(root: Path) -> set[str]:
    with closing(_connect(root)) as connection:
        return {row[0] for row in connection.execute("SELECT scan_id FROM jobs WHERE scan_id IS NOT NULL")}

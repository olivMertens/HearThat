"""Async SQLite-backed jobs store for the FastAPI UI."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import aiosqlite

from .config import get_settings
from .models import AudioJob, JobStatus, VoiceSpec

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    source_path TEXT NOT NULL,
    status TEXT NOT NULL,
    progress REAL NOT NULL DEFAULT 0,
    voice_json TEXT NOT NULL,
    summary_model TEXT NOT NULL,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    result_dir TEXT
);
"""


def _db_path() -> Path:
    return get_settings().hearthat_db_path


async def init_db() -> None:
    db_path = _db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(_SCHEMA)
        await db.commit()


async def insert_job(job: AudioJob) -> None:
    async with aiosqlite.connect(_db_path()) as db:
        await db.execute(
            "INSERT INTO jobs (id, source_path, status, progress, voice_json, "
            "summary_model, error, created_at, updated_at, result_dir) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                job.id,
                str(job.source_path),
                job.status.value,
                job.progress,
                job.voice.model_dump_json(),
                job.summary_model,
                job.error,
                job.created_at.isoformat(),
                job.updated_at.isoformat(),
                str(job.result_dir) if job.result_dir else None,
            ),
        )
        await db.commit()


async def update_job(
    job_id: str,
    *,
    status: JobStatus | None = None,
    progress: float | None = None,
    error: str | None = None,
    result_dir: Path | None = None,
) -> None:
    fields: list[str] = []
    values: list[object] = []
    if status is not None:
        fields.append("status=?")
        values.append(status.value)
    if progress is not None:
        fields.append("progress=?")
        values.append(progress)
    if error is not None:
        fields.append("error=?")
        values.append(error)
    if result_dir is not None:
        fields.append("result_dir=?")
        values.append(str(result_dir))
    fields.append("updated_at=?")
    values.append(datetime.utcnow().isoformat())
    values.append(job_id)
    async with aiosqlite.connect(_db_path()) as db:
        await db.execute(f"UPDATE jobs SET {', '.join(fields)} WHERE id=?", values)
        await db.commit()


def _row_to_job(row: aiosqlite.Row) -> AudioJob:
    return AudioJob(
        id=row["id"],
        source_path=Path(row["source_path"]),
        status=JobStatus(row["status"]),
        progress=row["progress"],
        voice=VoiceSpec.model_validate(json.loads(row["voice_json"])),
        summary_model=row["summary_model"],
        error=row["error"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        result_dir=Path(row["result_dir"]) if row["result_dir"] else None,
    )


async def get_job(job_id: str) -> AudioJob | None:
    async with aiosqlite.connect(_db_path()) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)) as cur:
            row = await cur.fetchone()
    return _row_to_job(row) if row else None


async def list_jobs(limit: int = 50) -> list[AudioJob]:
    async with aiosqlite.connect(_db_path()) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        ) as cur:
            rows = await cur.fetchall()
    return [_row_to_job(r) for r in rows]

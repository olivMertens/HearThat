"""FastAPI + HTMX UI for HearThat."""

from __future__ import annotations

import asyncio
import shutil
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..config import get_settings
from ..models import AudioJob, JobStatus, VoiceSpec
from ..pipeline import run_book
from ..store import get_job, init_db, insert_job, list_jobs, update_job

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    await init_db()
    settings = get_settings()
    (settings.hearthat_data_dir / "uploads").mkdir(parents=True, exist_ok=True)
    (settings.hearthat_data_dir / "out").mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="HearThat", lifespan=_lifespan)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


# ---------------------------------------------------------------------------
# Background job runner
# ---------------------------------------------------------------------------


_PHASE_MAP = {
    "ingest": JobStatus.INGESTING,
    "summarise": JobStatus.SUMMARIZING,
    "synthesise": JobStatus.SYNTHESIZING,
    "done": JobStatus.COMPLETED,
}


async def _run_pipeline(job: AudioJob) -> None:
    settings = get_settings()
    output_dir = settings.hearthat_data_dir / "out" / job.id

    async def _progress(phase: str, value: float) -> None:
        await update_job(job.id, status=_PHASE_MAP.get(phase, job.status), progress=value)

    try:
        await update_job(job.id, status=JobStatus.INGESTING, progress=0.0)
        await run_book(
            job.source_path,
            output_dir=output_dir,
            voice=job.voice,
            summary_model=job.summary_model,
            on_progress=_progress,
        )
        await update_job(
            job.id, status=JobStatus.COMPLETED, progress=1.0, result_dir=output_dir
        )
    except Exception as exc:  # pragma: no cover - background task
        await update_job(job.id, status=JobStatus.FAILED, error=str(exc))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    jobs = await list_jobs()
    settings = get_settings()
    return TEMPLATES.TemplateResponse(
        request,
        "index.html",
        {
            "jobs": jobs,
            "default_voice": settings.hearthat_default_voice,
            "fallback_voice": settings.hearthat_fallback_voice,
        },
    )


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/jobs", response_class=HTMLResponse)
async def create_job(
    request: Request,
    pdf: UploadFile = File(...),
    backend: str = Form("azure_speech_mai"),
    voice_name: str = Form(""),
    style: str = Form(""),
    summary_model: str = Form("gpt-5.4-mini"),
) -> HTMLResponse:
    settings = get_settings()
    upload_dir = settings.hearthat_data_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    job_id = uuid.uuid4().hex[:12]
    target = upload_dir / f"{job_id}_{pdf.filename}"
    with target.open("wb") as fh:
        shutil.copyfileobj(pdf.file, fh)

    job = AudioJob(
        id=job_id,
        source_path=target,
        voice=VoiceSpec(
            backend=backend,  # type: ignore[arg-type]
            voice_name=voice_name or settings.hearthat_default_voice,
            style=style or None,
        ),
        summary_model=summary_model,
    )
    await insert_job(job)
    asyncio.create_task(_run_pipeline(job))
    return TEMPLATES.TemplateResponse(
        request, "partials/job_row.html", {"job": job}
    )


@app.get("/jobs/{job_id}/progress", response_class=HTMLResponse)
async def job_progress(request: Request, job_id: str) -> HTMLResponse:
    job = await get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404)
    return TEMPLATES.TemplateResponse(
        request, "partials/job_row.html", {"job": job}
    )


@app.get("/jobs/{job_id}/audio/{chapter}")
async def chapter_audio(job_id: str, chapter: str) -> FileResponse:
    job = await get_job(job_id)
    if job is None or job.result_dir is None:
        raise HTTPException(status_code=404)
    candidate = job.result_dir / chapter
    if not candidate.exists():
        raise HTTPException(status_code=404)
    return FileResponse(candidate)


def main() -> None:
    import uvicorn

    uvicorn.run("hearthat.ui.app:app", host="127.0.0.1", port=8000)

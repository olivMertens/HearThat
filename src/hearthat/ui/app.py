"""FastAPI + HTMX UI for HearThat."""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..config import Settings, get_settings
from ..limits import (
    ALLOWED_EXTENSIONS,
    MAX_OPENAI_TTS_CHARS,
    MAX_PDF_PAGES,
    MAX_TEXT_CHARS,
    MAX_UPLOAD_BYTES,
    human_size,
)
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
    audio_by_job = {j.id: _collect_audio(j) for j in jobs}
    return TEMPLATES.TemplateResponse(
        request,
        "index.html",
        {
            "jobs": jobs,
            "audio_by_job": audio_by_job,
            "default_voice": settings.hearthat_default_voice,
            "fallback_voice": settings.hearthat_fallback_voice,
            "active_page": "home",
            "limits": {
                "max_size_human": human_size(MAX_UPLOAD_BYTES),
                "max_bytes": MAX_UPLOAD_BYTES,
                "max_pdf_pages": MAX_PDF_PAGES,
                "max_text_chars": MAX_TEXT_CHARS,
                "max_openai_chars": MAX_OPENAI_TTS_CHARS,
                "allowed_extensions": ", ".join(ALLOWED_EXTENSIONS),
            },
        },
    )


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Settings page — DNS only, no secrets, runtime-editable
# ---------------------------------------------------------------------------


_SETTINGS_GROUPS: list[dict[str, object]] = [
    {
        "title": "Language understanding",
        "fields": [
            (
                "AZURE_OPENAI_ENDPOINT",
                "Service address",
                "https://<your-foundry>.openai.azure.com/",
                "Where HearThat sends text for analysis and narration planning.",
                False,
            ),
            (
                "AZURE_OPENAI_API_VERSION",
                "Service version",
                "2024-12-01-preview",
                "Leave the default unless your administrator says otherwise.",
                False,
            ),
            (
                "AZURE_OPENAI_DEPLOYMENT_SUMMARY",
                "Summary model",
                "gpt-5.4-mini",
                "Used for chapter summaries and scene analysis.",
                False,
            ),
            (
                "AZURE_OPENAI_DEPLOYMENT_TTS",
                "Voice model (OpenAI backend)",
                "gpt-4o-mini-tts",
                "Only used when you pick the OpenAI voice backend.",
                False,
            ),
            (
                "AZURE_OPENAI_DEPLOYMENT_TRANSCRIBE",
                "Transcription model",
                "gpt-4o-mini-transcribe",
                "Used when re-listening to audio for quality checks.",
                False,
            ),
            (
                "AZURE_OPENAI_API_KEY",
                "Access key (development only)",
                "",
                "Optional. Used locally when your account can't sign in to this service.",
                True,
            ),
        ],
    },
    {
        "title": "Voice synthesis",
        "fields": [
            (
                "AZURE_SPEECH_ENDPOINT",
                "Service address",
                "https://eastus.api.cognitive.microsoft.com/",
                "Where HearThat sends text to turn into audio.",
                False,
            ),
            (
                "AZURE_SPEECH_REGION",
                "Region",
                "eastus",
                "The premium narration voice is currently only available in East US.",
                False,
            ),
            (
                "HEARTHAT_DEFAULT_VOICE",
                "Preferred voice",
                "en-us-Iris:MAI-Voice-1",
                "Used when you don't pick one in the form.",
                False,
            ),
            (
                "HEARTHAT_FALLBACK_VOICE",
                "Backup voice",
                "en-US-Ava:DragonHDOmniLatestNeural",
                "Used if the preferred voice is unavailable.",
                False,
            ),
            (
                "AZURE_SPEECH_API_KEY",
                "Access key (development only)",
                "",
                "Optional. Used locally when your account can't sign in to this service.",
                True,
            ),
        ],
    },
    {
        "title": "Documents and translation",
        "fields": [
            (
                "AZURE_DOCINTEL_ENDPOINT",
                "Document reader address",
                "https://<your-docintel>.cognitiveservices.azure.com/",
                "Reads PDFs and extracts the text. Optional — a built-in reader is used otherwise.",
                False,
            ),
            (
                "AZURE_DOCINTEL_API_KEY",
                "Document reader key (development only)",
                "",
                "Optional. Used locally when your account can't sign in.",
                True,
            ),
            (
                "AZURE_TRANSLATOR_ENDPOINT",
                "Translator address",
                "https://<your-translator>.cognitiveservices.azure.com/",
                "Optional. Only needed if you want translated audiobooks.",
                False,
            ),
            (
                "AZURE_TRANSLATOR_API_KEY",
                "Translator key (development only)",
                "",
                "Optional. Used locally when your account can't sign in.",
                True,
            ),
            (
                "AZURE_STORAGE_ACCOUNT_NAME",
                "Storage account name",
                "mystorageacct",
                "Optional. Used by the translation workflow.",
                False,
            ),
        ],
    },
]


def _editable_keys(*, include_secret: bool) -> list[str]:
    keys: list[str] = []
    for g in _SETTINGS_GROUPS:
        for entry in g["fields"]:  # type: ignore[index]
            name = entry[0]
            secret = entry[4] if len(entry) > 4 else False
            if secret and not include_secret:
                continue
            keys.append(name)
    return keys


def _build_groups(settings: Settings) -> list[dict[str, object]]:
    dump = {k.upper(): v for k, v in settings.model_dump().items()}
    out: list[dict[str, object]] = []
    for group in _SETTINGS_GROUPS:
        fields = []
        for entry in group["fields"]:  # type: ignore[index]
            name, label, placeholder, hint = entry[0], entry[1], entry[2], entry[3]
            secret = entry[4] if len(entry) > 4 else False
            if secret and not settings.is_dev:
                # Hide all key fields in production.
                continue
            value = dump.get(name, "")
            fields.append(
                {
                    "name": name,
                    "label": label,
                    "placeholder": placeholder,
                    "hint": hint,
                    "value": str(value) if value is not None else "",
                    "secret": bool(secret),
                }
            )
        out.append({"title": group["title"], "fields": fields})
    return out


def _identity_info(settings: Settings) -> dict[str, str]:
    has_sp = bool(os.environ.get("AZURE_CLIENT_ID") and os.environ.get("AZURE_CLIENT_SECRET"))
    has_keys = any(
        [
            settings.use_openai_key,
            settings.use_speech_key,
            settings.use_docintel_key,
            settings.use_translator_key,
        ]
    )
    has_cli = bool(os.environ.get("AZURE_TENANT_ID")) or not has_sp
    if has_keys:
        sign_in = "Using access keys (development)"
    elif has_sp:
        sign_in = "Signed in with an application identity"
    elif has_cli:
        sign_in = "Signed in with your user account"
    else:
        sign_in = "Not signed in yet"
    tenant = os.environ.get("AZURE_TENANT_ID") or "(default for your account)"
    return {
        "Sign-in": sign_in,
        "Mode": "Development" if settings.is_dev else "Production",
        "Organisation": tenant,
    }


def _persist_env_file(updates: dict[str, str], env_path: Path) -> None:
    """Write/update keys in the .env file (creates it if missing)."""
    existing: list[str] = []
    if env_path.exists():
        existing = env_path.read_text(encoding="utf-8").splitlines()
    seen: set[str] = set()
    new_lines: list[str] = []
    for line in existing:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            new_lines.append(line)
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in updates:
            new_lines.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            new_lines.append(line)
    for key, val in updates.items():
        if key not in seen:
            new_lines.append(f"{key}={val}")
    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, saved: int = 0) -> HTMLResponse:
    settings = get_settings()
    env_path = Path(".env")
    return TEMPLATES.TemplateResponse(
        request,
        "settings.html",
        {
            "active_page": "settings",
            "groups": _build_groups(settings),
            "identity": _identity_info(settings),
            "env_file_exists": env_path.exists(),
            "is_dev": settings.is_dev,
            "message": "Settings applied." if saved else None,
        },
    )


@app.post("/settings")
async def update_settings_route(request: Request) -> RedirectResponse:
    form = await request.form()
    persist = bool(form.get("persist"))
    settings = get_settings()
    updates: dict[str, str] = {}
    for key in _editable_keys(include_secret=settings.is_dev):
        if key in form:
            value = str(form[key]).strip()
            updates[key] = value
            if value:
                os.environ[key] = value
            else:
                os.environ.pop(key, None)
    # Bust cached settings so next call reflects the new env.
    get_settings.cache_clear()
    if persist:
        _persist_env_file(updates, Path(".env"))
    return RedirectResponse(url="/settings?saved=1", status_code=303)


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
    filename = pdf.filename or "upload"
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{suffix}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}.",
        )

    upload_dir = settings.hearthat_data_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    job_id = uuid.uuid4().hex[:12]
    target = upload_dir / f"{job_id}_{filename}"
    written = 0
    with target.open("wb") as fh:
        while chunk := await pdf.read(1024 * 1024):
            written += len(chunk)
            if written > MAX_UPLOAD_BYTES:
                fh.close()
                target.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"File exceeds {human_size(MAX_UPLOAD_BYTES)} demo cap.",
                )
            fh.write(chunk)

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
        request, "partials/job_row.html", {"job": job, "audio_files": []}
    )


@app.get("/jobs/{job_id}/progress", response_class=HTMLResponse)
async def job_progress(request: Request, job_id: str) -> HTMLResponse:
    job = await get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404)
    return TEMPLATES.TemplateResponse(
        request,
        "partials/job_row.html",
        {"job": job, "audio_files": _collect_audio(job)},
    )


_PLAYABLE_EXTS = {".mp3", ".wav", ".ogg", ".m4a"}
_DOWNLOAD_EXTS = _PLAYABLE_EXTS | {".zip"}


def _collect_audio(job: AudioJob) -> list[dict[str, str]]:
    """List playable audio + download archives produced for a completed job."""
    if job.result_dir is None or not job.result_dir.exists():
        return []
    items: list[dict[str, str]] = []
    for path in sorted(job.result_dir.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix not in _DOWNLOAD_EXTS:
            continue
        rel = path.relative_to(job.result_dir).as_posix()
        items.append(
            {
                "name": path.name,
                "rel": rel,
                "kind": "audio" if suffix in _PLAYABLE_EXTS else "archive",
                "size_human": human_size(path.stat().st_size),
            }
        )
    return items


@app.get("/jobs/{job_id}/file/{rel_path:path}")
async def job_file(job_id: str, rel_path: str) -> FileResponse:
    job = await get_job(job_id)
    if job is None or job.result_dir is None:
        raise HTTPException(status_code=404)
    base = job.result_dir.resolve()
    candidate = (base / rel_path).resolve()
    # Path traversal guard.
    try:
        candidate.relative_to(base)
    except ValueError as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=400, detail="Invalid path") from exc
    if not candidate.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(candidate, filename=candidate.name)


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

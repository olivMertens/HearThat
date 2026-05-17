"""High-level orchestration: PDF -> chapters -> summaries -> audio."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

from .config import get_settings
from .costs import build_cost
from .ingest import ingest_pdf
from .models import Book, Cost, VoiceSpec
from .summarize import summarise_book
from .tts import synthesize

logger = logging.getLogger(__name__)

ProgressCb = Callable[[str, float], Awaitable[None]]


async def run_book(
    pdf_path: Path,
    *,
    output_dir: Path | None = None,
    voice: VoiceSpec | None = None,
    summary_model: str | None = None,
    on_progress: ProgressCb | None = None,
) -> tuple[Book, Cost]:
    """End-to-end pipeline: ingest, summarise, narrate."""
    settings = get_settings()
    pdf_path = Path(pdf_path)
    output_dir = output_dir or (settings.hearthat_data_dir / "out" / pdf_path.stem)
    output_dir.mkdir(parents=True, exist_ok=True)
    voice = voice or VoiceSpec(voice_name=settings.hearthat_default_voice)
    cost = Cost()

    async def _emit(phase: str, value: float) -> None:
        if on_progress is not None:
            await on_progress(phase, value)

    # 1. Ingest
    await _emit("ingest", 0.05)
    book = await ingest_pdf(pdf_path)
    await _emit("ingest", 0.20)

    # 2. Summaries
    async def _sum_progress(done: int, total: int) -> None:
        await _emit("summarise", 0.20 + 0.30 * (done / max(total, 1)))

    sum_cost = await summarise_book(book, model=summary_model, on_progress=_sum_progress)
    cost.summary_tokens_in += sum_cost.summary_tokens_in
    cost.summary_tokens_out += sum_cost.summary_tokens_out
    cost.summary_usd += sum_cost.summary_usd

    # 3. TTS per chapter
    total = len(book.chapters)
    for i, ch in enumerate(book.chapters, start=1):
        narration = ch.summary or ch.text
        chapter_dir = output_dir / f"chapter_{ch.index:02d}"
        try:
            audio = await synthesize(narration, voice=voice, output_dir=chapter_dir)
            ch.audio_path = audio
        except Exception as exc:  # pragma: no cover - integration path
            logger.exception("TTS failed for chapter %s: %s", ch.index, exc)
        chars = len(narration)
        cost.tts_neural_chars += chars
        cost.tts_usd += build_cost(
            model="-", tts_chars=chars, tts_backend=voice.backend
        ).tts_usd
        await _emit("synthesise", 0.50 + 0.50 * (i / total))

    # 4. Persist chapter markdown + summaries.
    for ch in book.chapters:
        md = output_dir / f"chapter_{ch.index:02d}.md"
        md.write_text(
            f"# {ch.title}\n\n## Summary\n\n{ch.summary or ''}\n\n## Text\n\n{ch.text}",
            encoding="utf-8",
        )

    await _emit("done", 1.0)
    return book, cost

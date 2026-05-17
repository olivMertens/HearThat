"""HearThat CLI (Typer + Rich)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .config import get_settings
from .ingest import ingest_pdf
from .models import VoiceSpec
from .pipeline import run_book
from .summarize import summarise_text
from .tts import synthesize_openai_tts

app = typer.Typer(
    help="HearThat — turn PDF books into multi-voice audiobooks with Azure AI.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def version() -> None:
    """Print the HearThat version."""
    console.print(f"hearthat v{__version__}")


@app.command()
def ingest(
    pdf: Path = typer.Argument(..., exists=True, readable=True, help="Path to a PDF file."),
    no_doc_intelligence: bool = typer.Option(False, help="Skip Document Intelligence."),
) -> None:
    """Extract a PDF into chapters and print a summary."""

    async def _run() -> None:
        book = await ingest_pdf(pdf, use_doc_intelligence=not no_doc_intelligence)
        table = Table(title=book.title)
        table.add_column("#")
        table.add_column("Title")
        table.add_column("Chars", justify="right")
        for ch in book.chapters:
            table.add_row(str(ch.index), ch.title[:60], str(len(ch.text)))
        console.print(table)

    asyncio.run(_run())


@app.command()
def summarise(
    text_file: Path = typer.Argument(..., exists=True),
    model: str | None = typer.Option(None, help="Override summary deployment."),
) -> None:
    """Summarise a text file."""

    async def _run() -> None:
        text = text_file.read_text(encoding="utf-8")
        out, cost = await summarise_text(text, model=model)
        console.print(out)
        console.print(f"[dim]cost: ${cost.summary_usd:.4f}[/dim]")

    asyncio.run(_run())


@app.command(name="tts-openai")
def tts_openai(
    text: str = typer.Argument(..., help="Text to synthesise."),
    out: Path = typer.Option(Path("out.mp3"), "--out", "-o"),
    instructions: str | None = typer.Option(None, help="Natural-language style brief."),
    voice: str = typer.Option("alloy", help="OpenAI TTS voice (alloy, sage, nova, ...)."),
) -> None:
    """Synthesise short text with prompt-steerable gpt-4o-mini-tts."""
    asyncio.run(
        synthesize_openai_tts(text, output_path=out, instructions=instructions, voice=voice)
    )
    console.print(f"[green]Wrote[/green] {out}")


@app.command()
def run(
    pdf: Path = typer.Argument(..., exists=True, readable=True),
    voice_name: str = typer.Option(
        "", "--voice", help="Voice name (defaults to settings)."
    ),
    backend: str = typer.Option(
        "azure_speech_mai",
        help="azure_speech_mai | azure_speech_hd | openai_tts",
    ),
    style: str | None = typer.Option(None, help="mstts:express-as / OpenAI instructions."),
    model: str | None = typer.Option(None, help="Summary model override."),
) -> None:
    """End-to-end: PDF -> chapters -> summaries -> audio."""
    settings = get_settings()
    voice = VoiceSpec(
        backend=backend,  # type: ignore[arg-type]
        voice_name=voice_name or settings.hearthat_default_voice,
        style=style,
    )

    async def _run() -> None:
        async def _on(phase: str, value: float) -> None:
            console.print(f"[cyan]{phase:>10}[/cyan] {value * 100:5.1f}%")

        book, cost = await run_book(
            pdf, voice=voice, summary_model=model, on_progress=_on
        )
        console.print(f"\n[bold green]Done.[/bold green] {len(book.chapters)} chapters")
        console.print(f"  summary: ${cost.summary_usd:.4f}")
        console.print(f"  tts    : ${cost.tts_usd:.4f}")
        console.print(f"  total  : ${cost.total_usd:.4f}")

    asyncio.run(_run())


@app.command()
def ui(
    host: str = typer.Option("127.0.0.1"),
    port: int = typer.Option(8000),
) -> None:
    """Launch the HearThat web UI (FastAPI + HTMX)."""
    import uvicorn

    uvicorn.run("hearthat.ui.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    app()

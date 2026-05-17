"""Source ingestion: PDF via Document Intelligence (pypdf fallback), plus
plain-text and Markdown sources."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from azure.ai.documentintelligence.aio import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest, AnalyzeResult

from .auth import docintel_credential
from .config import get_settings
from .limits import (
    ALLOWED_EXTENSIONS,
    MAX_PDF_PAGES,
    MAX_TEXT_CHARS,
    MAX_UPLOAD_BYTES,
    human_size,
)
from .models import Book, Chapter

logger = logging.getLogger(__name__)

_CHAPTER_HEADING = re.compile(
    r"^(?:chapter|chapitre|part|partie)\s+[\dIVXLC]+\b.*$",
    re.IGNORECASE | re.MULTILINE,
)
# Markdown ATX headings (#, ##, ###) — used for .md chapter splitting.
_MD_HEADING = re.compile(r"^(#{1,3})\s+(.+?)\s*#*\s*$", re.MULTILINE)


class IngestError(ValueError):
    """Raised when an input file violates the demo limits or format rules."""


def _validate_size(path: Path) -> None:
    size = path.stat().st_size
    if size > MAX_UPLOAD_BYTES:
        raise IngestError(
            f"File too large: {human_size(size)} > {human_size(MAX_UPLOAD_BYTES)} max."
        )


async def extract_with_doc_intelligence(pdf_path: Path) -> str:
    """Run Document Intelligence ``prebuilt-layout`` and return Markdown."""
    settings = get_settings()
    if not settings.is_docintel_configured:
        raise RuntimeError("AZURE_DOCINTEL_ENDPOINT not configured")

    credential = docintel_credential(settings)
    client = DocumentIntelligenceClient(
        endpoint=settings.azure_docintel_endpoint,
        credential=credential,
    )
    async with client:
        with pdf_path.open("rb") as fh:
            poller = await client.begin_analyze_document(
                "prebuilt-layout",
                AnalyzeDocumentRequest(bytes_source=fh.read()),
                output_content_format="markdown",
            )
        result: AnalyzeResult = await poller.result()
    return result.content or ""


def extract_local(pdf_path: Path) -> str:
    """Cheap fallback using ``pypdf`` — text only, no layout. Enforces page cap."""
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    if len(reader.pages) > MAX_PDF_PAGES:
        raise IngestError(
            f"PDF has {len(reader.pages)} pages > {MAX_PDF_PAGES} max for the demo."
        )
    return "\n\n".join(page.extract_text() or "" for page in reader.pages)


def split_chapters(text: str, *, default_title: str = "Chapter") -> list[Chapter]:
    """Split a Markdown blob into chapters based on heading regex."""
    if not text.strip():
        return []

    matches = list(_CHAPTER_HEADING.finditer(text))
    if not matches:
        return [Chapter(index=1, title=default_title, text=text.strip())]

    chapters: list[Chapter] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end].strip()
        title = m.group(0).strip()
        body = block[len(m.group(0)) :].strip()
        chapters.append(Chapter(index=i + 1, title=title, text=body))
    return chapters


def split_markdown_chapters(text: str, *, default_title: str = "Chapter") -> list[Chapter]:
    """Split Markdown by ``#`` / ``##`` headings."""
    if not text.strip():
        return []
    matches = list(_MD_HEADING.finditer(text))
    if not matches:
        # Fall back to the prose-style chapter splitter (Chapter N, etc.).
        return split_chapters(text, default_title=default_title)

    chapters: list[Chapter] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        title = m.group(2).strip()
        body = text[m.end() : end].strip()
        chapters.append(Chapter(index=i + 1, title=title, text=body))
    return chapters


async def ingest_pdf(pdf_path: Path, *, use_doc_intelligence: bool = True) -> Book:
    """Read a PDF and return a :class:`Book` with chapters."""
    pdf_path = Path(pdf_path)
    _validate_size(pdf_path)
    if use_doc_intelligence:
        try:
            text = await extract_with_doc_intelligence(pdf_path)
        except IngestError:
            raise
        except Exception as exc:  # pragma: no cover - integration path
            logger.warning("Document Intelligence failed (%s); falling back to pypdf", exc)
            text = extract_local(pdf_path)
    else:
        text = extract_local(pdf_path)

    if len(text) > MAX_TEXT_CHARS:
        raise IngestError(
            f"Extracted text is {len(text):,} chars > {MAX_TEXT_CHARS:,} max for the demo."
        )
    chapters = split_chapters(text, default_title=pdf_path.stem)
    return Book(title=pdf_path.stem, source_path=pdf_path, chapters=chapters)


def ingest_text(path: Path) -> Book:
    """Read a plain ``.txt`` file and split into chapters."""
    path = Path(path)
    _validate_size(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) > MAX_TEXT_CHARS:
        raise IngestError(
            f"Text is {len(text):,} chars > {MAX_TEXT_CHARS:,} max for the demo."
        )
    chapters = split_chapters(text, default_title=path.stem)
    return Book(title=path.stem, source_path=path, chapters=chapters)


def ingest_markdown(path: Path) -> Book:
    """Read a ``.md`` file and split on Markdown headings."""
    path = Path(path)
    _validate_size(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) > MAX_TEXT_CHARS:
        raise IngestError(
            f"Markdown is {len(text):,} chars > {MAX_TEXT_CHARS:,} max for the demo."
        )
    chapters = split_markdown_chapters(text, default_title=path.stem)
    return Book(title=path.stem, source_path=path, chapters=chapters)


async def ingest_source(path: Path, *, use_doc_intelligence: bool = True) -> Book:
    """Dispatch to the right ingester based on the file extension."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise IngestError(
            f"Unsupported file type '{suffix}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}."
        )
    if suffix == ".pdf":
        return await ingest_pdf(path, use_doc_intelligence=use_doc_intelligence)
    if suffix in {".md", ".markdown"}:
        return ingest_markdown(path)
    return ingest_text(path)

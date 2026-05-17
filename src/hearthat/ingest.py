"""PDF ingestion: Document Intelligence first, pypdf fallback."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from azure.ai.documentintelligence.aio import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest, AnalyzeResult

from .auth import get_async_credential
from .config import get_settings
from .models import Book, Chapter

logger = logging.getLogger(__name__)

_CHAPTER_HEADING = re.compile(
    r"^(?:chapter|chapitre|part|partie)\s+[\dIVXLC]+\b.*$",
    re.IGNORECASE | re.MULTILINE,
)


async def extract_with_doc_intelligence(pdf_path: Path) -> str:
    """Run Document Intelligence ``prebuilt-layout`` and return Markdown."""
    settings = get_settings()
    if not settings.is_docintel_configured:
        raise RuntimeError("AZURE_DOCINTEL_ENDPOINT not configured")

    credential = get_async_credential()
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
    """Cheap fallback using ``pypdf`` — text only, no layout."""
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    return "\n\n".join(page.extract_text() or "" for page in reader.pages)


def split_chapters(text: str, *, default_title: str = "Chapter") -> list[Chapter]:
    """Split a Markdown blob into chapters based on heading regex."""
    if not text.strip():
        return []

    # Try to split on chapter-like headings; fall back to a single chapter.
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


async def ingest_pdf(pdf_path: Path, *, use_doc_intelligence: bool = True) -> Book:
    """Read a PDF and return a :class:`Book` with chapters."""
    pdf_path = Path(pdf_path)
    if use_doc_intelligence:
        try:
            text = await extract_with_doc_intelligence(pdf_path)
        except Exception as exc:  # pragma: no cover - integration path
            logger.warning("Document Intelligence failed (%s); falling back to pypdf", exc)
            text = extract_local(pdf_path)
    else:
        text = extract_local(pdf_path)

    chapters = split_chapters(text, default_title=pdf_path.stem)
    return Book(title=pdf_path.stem, source_path=pdf_path, chapters=chapters)

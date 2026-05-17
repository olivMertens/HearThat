"""Local text translation via Azure AI Translator Text (async, passwordless).

Works on in-memory strings and on-disk files — no Blob Storage required.
Requests are chunked to stay under the 50 000-character per-call limit.
"""

from __future__ import annotations

from pathlib import Path

from azure.ai.translation.text.aio import TextTranslationClient
from azure.ai.translation.text.models import InputTextItem

from .auth import get_async_credential
from .config import get_settings

_MAX_CHARS = 45_000  # service caps each request at 50 000 incl. overhead


def _chunk(text: str, limit: int = _MAX_CHARS) -> list[str]:
    """Split *text* on paragraph boundaries while staying under *limit* chars."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for para in text.split("\n\n"):
        block = para + "\n\n"
        if size + len(block) > limit and current:
            chunks.append("".join(current).rstrip())
            current, size = [], 0
        current.append(block)
        size += len(block)
    if current:
        chunks.append("".join(current).rstrip())
    return chunks


async def translate_text(
    text: str,
    *,
    target_language: str,
    source_language: str | None = None,
    text_type: str = "plain",
) -> str:
    """Translate an in-memory string. Returns the translated text."""
    settings = get_settings()
    if not settings.is_translator_configured:
        raise RuntimeError("AZURE_TRANSLATOR_ENDPOINT not configured")

    credential = get_async_credential()
    client = TextTranslationClient(
        endpoint=settings.azure_translator_endpoint,
        credential=credential,
    )
    out: list[str] = []
    async with client:
        for chunk in _chunk(text):
            response = await client.translate(
                body=[InputTextItem(text=chunk)],
                to_language=[target_language],
                from_language=source_language,
                text_type=text_type,
            )
            out.append(response[0].translations[0].text)
    return "\n\n".join(out)


async def translate_markdown_file(
    src: Path,
    dst: Path,
    *,
    target_language: str,
    source_language: str | None = None,
) -> Path:
    """Translate a local markdown file and write the result to *dst*."""
    text = src.read_text(encoding="utf-8")
    translated = await translate_text(
        text,
        target_language=target_language,
        source_language=source_language,
        text_type="plain",
    )
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(translated, encoding="utf-8")
    return dst

"""LLM Speech (preview) — transcription + translation in one pass.

23-language auto-detect, custom prompting, retry policy from the official doc
(5 attempts, exponential backoff 2/4/8/16/32 s).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .auth import COGNITIVE_SCOPE, get_async_credential
from .config import get_settings

_RETRY_KW: dict[str, Any] = {
    "stop": stop_after_attempt(5),
    "wait": wait_exponential(multiplier=2, min=2, max=32),
    "retry": retry_if_exception_type(
        (httpx.HTTPStatusError, httpx.TransportError, httpx.TimeoutException)
    ),
    "reraise": True,
}


async def transcribe_audio(
    audio_path: Path,
    *,
    translate_to: str | None = None,
    prompt: str | None = None,
) -> dict[str, Any]:
    """Transcribe (and optionally translate) an audio file through LLM Speech.

    Parameters
    ----------
    audio_path:
        Audio file (wav/mp3/m4a/...).
    translate_to:
        If set, request translation to this BCP-47 locale (``en``, ``fr``, ...).
    prompt:
        Custom prompt to guide the LLM (style, formatting).
    """
    settings = get_settings()
    base = settings.azure_speech_endpoint.rstrip("/") or (
        f"https://{settings.azure_speech_region}.api.cognitive.microsoft.com"
    )
    url = f"{base}/speechtotext/transcriptions:transcribe?api-version=2024-11-15"

    credential = get_async_credential()
    token = (await credential.get_token(COGNITIVE_SCOPE)).token
    headers = {"Authorization": f"Bearer {token}"}

    definition: dict[str, Any] = {"model": "llm-speech"}
    if translate_to:
        definition["task"] = "translate"
        definition["targetLocale"] = translate_to
    else:
        definition["task"] = "transcribe"
    if prompt:
        definition["prompt"] = prompt

    async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client:
        async for attempt in AsyncRetrying(**_RETRY_KW):
            with attempt:
                # Reset stream on each retry (doc requirement).
                with audio_path.open("rb") as fh:
                    audio_bytes = fh.read()
                files: list[tuple[str, tuple[str | None, bytes | str, str | None]]] = [
                    (
                        "audio",
                        (audio_path.name, audio_bytes, "application/octet-stream"),
                    ),
                    ("definition", (None, str(definition).replace("'", '"'), None)),
                ]
                resp = await client.post(url, headers=headers, files=files)
                resp.raise_for_status()
    data: dict[str, Any] = resp.json()
    return data

"""Text-to-speech backends: MAI-Voice-1, DragonHD (Batch Synthesis), and gpt-4o-mini-tts.

Retry policy follows the official LLM Speech guidance (5 attempts, exponential
backoff 2/4/8/16/32 s).
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

import httpx
from openai import AsyncAzureOpenAI
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .auth import aoai_client_kwargs, speech_auth_headers
from .config import get_settings
from .models import ProsodyProfile, TtsBackend, VoiceSpec
from .narration import analyse_scene, build_narration_ssml_from_plan
from .ssml import build_narration_ssml

logger = logging.getLogger(__name__)

BATCH_API_VERSION = "2024-04-01"

_RETRY_KW: dict[str, Any] = {
    "stop": stop_after_attempt(5),
    "wait": wait_exponential(multiplier=2, min=2, max=32),
    "retry": retry_if_exception_type(
        (httpx.HTTPStatusError, httpx.TransportError, httpx.TimeoutException)
    ),
    "reraise": True,
}


async def _speech_token() -> str:  # pragma: no cover - legacy, kept for back-compat
    from .auth import COGNITIVE_SCOPE, get_async_credential

    credential = get_async_credential()
    token = await credential.get_token(COGNITIVE_SCOPE)
    return token.token


# ---------------------------------------------------------------------------
# Batch Synthesis (DragonHD/Omni + MAI-Voice-1 share the same endpoint)
# ---------------------------------------------------------------------------


def build_batch_payload(ssml: str, *, name: str = "hearthat-job") -> dict[str, Any]:
    """Build a Batch Synthesis request payload."""
    return {
        "description": name,
        "inputKind": "SSML",
        "inputs": [{"content": ssml}],
        "properties": {
            "outputFormat": "audio-24khz-160kbitrate-mono-mp3",
            "wordBoundaryEnabled": True,
            "sentenceBoundaryEnabled": True,
            "concatenateResult": True,
        },
    }


async def _submit_batch(ssml: str, *, output_dir: Path) -> Path:
    settings = get_settings()
    base = settings.azure_speech_endpoint.rstrip("/") or (
        f"https://{settings.azure_speech_region}.api.cognitive.microsoft.com"
    )
    job_id = str(uuid.uuid4())
    url = f"{base}/texttospeech/batchsyntheses/{job_id}?api-version={BATCH_API_VERSION}"
    headers = await speech_auth_headers(settings)
    headers["Content-Type"] = "application/json"

    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
        async for attempt in AsyncRetrying(**_RETRY_KW):
            with attempt:
                resp = await client.put(url, headers=headers, json=build_batch_payload(ssml))
                resp.raise_for_status()

        # Poll until succeeded
        while True:
            async for attempt in AsyncRetrying(**_RETRY_KW):
                with attempt:
                    poll = await client.get(url, headers=headers)
                    poll.raise_for_status()
            data = poll.json()
            status = data.get("status")
            if status in {"Succeeded", "Failed"}:
                break

        if status == "Failed":
            raise RuntimeError(f"Batch synthesis failed: {data}")

        outputs = data.get("outputs", {})
        zip_url = outputs.get("result")
        if not zip_url:
            raise RuntimeError("Batch synthesis succeeded but no result URL returned")

        async for attempt in AsyncRetrying(**_RETRY_KW):
            with attempt:
                zip_resp = await client.get(zip_url)
                zip_resp.raise_for_status()

    output_dir.mkdir(parents=True, exist_ok=True)
    zip_path = output_dir / f"{job_id}.zip"
    zip_path.write_bytes(zip_resp.content)
    return zip_path


async def synthesize_batch(
    text: str,
    *,
    voice: VoiceSpec,
    output_dir: Path,
    prosody: ProsodyProfile | None = None,
    scene_analysis: bool = True,
) -> Path:
    """Submit one SSML payload through Batch Synthesis and return the result zip.

    When ``scene_analysis`` is ``True`` (default) and Azure OpenAI is
    configured, an LLM pre-pass labels each paragraph (kind / mood / style /
    pause / emphasis) and the SSML is built from that plan. Any failure
    silently falls back to the regex-only builder so synthesis still succeeds.
    """
    ssml: str | None = None
    if scene_analysis and get_settings().is_openai_configured:
        try:
            plan = await analyse_scene(text)
            if plan.paragraphs:
                ssml = build_narration_ssml_from_plan(text, plan, voice, prosody=prosody)
                logger.info("Scene plan applied (%d paragraphs)", len(plan.paragraphs))
        except Exception as exc:  # pragma: no cover - best-effort
            logger.warning("Scene analysis failed (%s); falling back to regex SSML", exc)
    if ssml is None:
        ssml = build_narration_ssml(text, voice, prosody=prosody)
    return await _submit_batch(ssml, output_dir=output_dir)


# ---------------------------------------------------------------------------
# OpenAI TTS (gpt-4o-mini-tts) — prompt-steerable
# ---------------------------------------------------------------------------


async def synthesize_openai_tts(
    text: str,
    *,
    output_path: Path,
    instructions: str | None = None,
    voice: str = "alloy",
    model: str | None = None,
) -> Path:
    """Synthesise short text with ``gpt-4o-mini-tts``."""
    settings = get_settings()
    model = model or settings.azure_openai_deployment_tts

    client = AsyncAzureOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_version=settings.azure_openai_api_version,
        **aoai_client_kwargs(settings),
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    async with client:
        kwargs: dict[str, Any] = {"model": model, "voice": voice, "input": text}
        if instructions:
            kwargs["instructions"] = instructions
        resp = await client.audio.speech.create(**kwargs)
        output_path.write_bytes(resp.read())
    return output_path


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


async def synthesize(
    text: str,
    *,
    voice: VoiceSpec,
    output_dir: Path,
    prosody: ProsodyProfile | None = None,
) -> Path:
    """Dispatch to the right backend based on ``voice.backend``."""
    backend: TtsBackend = voice.backend
    if backend == "openai_tts":
        out = output_dir / "openai_tts.mp3"
        return await synthesize_openai_tts(
            text,
            output_path=out,
            instructions=voice.style,
        )
    # MAI-Voice-1 and HD voices both go through Batch Synthesis.
    return await synthesize_batch(text, voice=voice, output_dir=output_dir, prosody=prosody)

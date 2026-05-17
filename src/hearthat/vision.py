"""PDF figure description via multimodal Azure OpenAI (``gpt-5.4-mini`` default).

Document Intelligence already detects ``figure`` bounding boxes; this module
encodes those crops as base64 data URIs and asks the model to describe them
so the narration can mention them naturally.
"""

from __future__ import annotations

import base64
from pathlib import Path

from openai import AsyncAzureOpenAI

from .auth import COGNITIVE_SCOPE, get_async_credential
from .config import get_settings

_REASONING_PREFIXES = ("o1", "o3", "o4", "gpt-5")


async def describe_figure(
    image_path: Path,
    *,
    caption: str | None = None,
    model: str | None = None,
) -> str:
    """Return a 1-3 sentence narration-ready description of ``image_path``."""
    settings = get_settings()
    model = model or settings.azure_openai_deployment_vision

    credential = get_async_credential()

    async def token_provider() -> str:
        token = await credential.get_token(COGNITIVE_SCOPE)
        return token.token

    client = AsyncAzureOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_version=settings.azure_openai_api_version,
        azure_ad_token_provider=token_provider,
    )

    data = base64.b64encode(image_path.read_bytes()).decode("ascii")
    suffix = image_path.suffix.lstrip(".").lower() or "png"
    data_url = f"data:image/{suffix};base64,{data}"

    user_text = (
        "Describe this figure for a listener of an audiobook in 1-3 short sentences. "
        "Be concrete and avoid generic phrasing."
    )
    if caption:
        user_text += f"\nCaption: {caption}"

    kwargs: dict[str, object] = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        "max_completion_tokens": 300,
    }
    if model.lower().startswith(_REASONING_PREFIXES):
        kwargs["reasoning_effort"] = "low"
    else:
        kwargs["temperature"] = 0.2

    async with client:
        resp = await client.chat.completions.create(**kwargs)  # type: ignore[call-overload]
    return (resp.choices[0].message.content or "").strip()

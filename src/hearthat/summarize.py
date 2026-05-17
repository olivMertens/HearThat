"""Chapter summarisation via Azure OpenAI.

Default model is a reasoning model (``gpt-5.4-mini``) called with
``reasoning_effort='minimal'``. Set ``model`` to a non-reasoning model
(``gpt-4.1-mini``) to enable ``temperature``.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from openai import AsyncAzureOpenAI

from .auth import aoai_client_kwargs
from .config import get_settings
from .costs import build_cost
from .models import Book, Cost

logger = logging.getLogger(__name__)

_REASONING_PREFIXES = ("o1", "o3", "o4", "gpt-5")

SYSTEM_PROMPT = (
    "You are a precise, neutral book summariser. Produce a faithful, easy-to-listen "
    "summary in clear English. Keep proper nouns intact. Output Markdown."
)


def _is_reasoning(model: str) -> bool:
    return model.lower().startswith(_REASONING_PREFIXES)


async def _aoai_client() -> AsyncAzureOpenAI:
    settings = get_settings()
    if not settings.is_openai_configured:
        raise RuntimeError("AZURE_OPENAI_ENDPOINT not configured")

    return AsyncAzureOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_version=settings.azure_openai_api_version,
        **aoai_client_kwargs(settings),
    )


async def summarise_text(
    text: str,
    *,
    model: str | None = None,
    max_output_tokens: int = 1500,
    user_prompt: str | None = None,
) -> tuple[str, Cost]:
    """Summarise ``text`` and return ``(markdown, cost)``."""
    settings = get_settings()
    model = model or settings.azure_openai_deployment_summary

    client = await _aoai_client()
    user = user_prompt or (
        "Summarise the following chapter. Use short paragraphs and section headings."
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"{user}\n\n---\n\n{text}"},
    ]

    kwargs: dict[str, object] = {
        "model": model,
        "messages": messages,
        "max_completion_tokens": max_output_tokens,
    }
    if _is_reasoning(model):
        kwargs["reasoning_effort"] = "minimal"
    else:
        kwargs["temperature"] = 0.3

    async with client:
        resp = await client.chat.completions.create(**kwargs)  # type: ignore[call-overload]

    content = (resp.choices[0].message.content or "").strip()
    usage = resp.usage
    cost = build_cost(
        model=model,
        tokens_in=getattr(usage, "prompt_tokens", 0) or 0,
        tokens_out=getattr(usage, "completion_tokens", 0) or 0,
    )
    return content, cost


async def summarise_book(
    book: Book,
    *,
    model: str | None = None,
    on_progress: Callable[[int, int], Awaitable[None]] | None = None,
) -> Cost:
    """Summarise every chapter in-place; return aggregated cost."""
    total = Cost()
    for i, chapter in enumerate(book.chapters, start=1):
        summary, cost = await summarise_text(chapter.text, model=model)
        chapter.summary = summary
        total.summary_tokens_in += cost.summary_tokens_in
        total.summary_tokens_out += cost.summary_tokens_out
        total.summary_usd += cost.summary_usd
        if on_progress is not None:
            await on_progress(i, len(book.chapters))
    return total

"""LLM-driven scene analysis for narration SSML.

Sends the chapter text to Azure OpenAI and asks for a per-paragraph plan:
the kind of paragraph (heading / dialog / narration / action), an atmosphere
mood, an ``mstts:express-as`` style hint, a pre-paragraph pause and an
emphasis level. The plan is then turned into a single SSML document.

This stage is best-effort: any error falls back to the regex-only
:func:`hearthat.ssml.build_narration_ssml` builder.
"""

from __future__ import annotations

import html
import json
import logging
import re
from dataclasses import dataclass

from openai import AsyncAzureOpenAI

from .auth import COGNITIVE_SCOPE, get_async_credential
from .config import get_settings
from .models import ProsodyProfile, VoiceSpec
from .ssml import SSML_NS, _params_attr, _render_dialog

logger = logging.getLogger(__name__)

_REASONING_PREFIXES = ("o1", "o3", "o4", "gpt-5")

_ALLOWED_KINDS = {"heading", "dialog", "narration", "action"}
_ALLOWED_EMPHASIS = {"none", "reduced", "moderate", "strong"}

SYSTEM_PROMPT = (
    "You are a narration director for an audiobook. You read the user's text "
    "and label each paragraph so a TTS engine can read it expressively. "
    "Return ONLY valid JSON, no prose, no Markdown fences."
)

USER_TEMPLATE = (
    "For each numbered paragraph below, output one JSON object with:\n"
    '  "index": the paragraph number (1-based),\n'
    '  "kind": one of "heading", "dialog", "narration", "action",\n'
    '  "mood": one or two adjectives (e.g. "tense", "warm and reflective"),\n'
    '  "style": a SHORT mstts:express-as style ("narration-relaxed", '
    '"narration-professional", "calm", "cheerful", "sad", "whispering", '
    '"empathetic", "excited", "hopeful", "serious"),\n'
    '  "pause_before_ms": integer pause to insert before the paragraph '
    "(0-1500, used for scene breaks),\n"
    '  "emphasis": one of "none", "reduced", "moderate", "strong".\n'
    'Return a JSON object: {"plan": [ ... ]}. Output ONLY the JSON.\n\n'
    "Paragraphs:\n{paragraphs}"
)


@dataclass(slots=True)
class SceneParagraph:
    index: int
    kind: str
    mood: str
    style: str
    pause_before_ms: int
    emphasis: str


@dataclass(slots=True)
class ScenePlan:
    paragraphs: list[SceneParagraph]

    def for_index(self, idx: int) -> SceneParagraph | None:
        for p in self.paragraphs:
            if p.index == idx:
                return p
        return None


def _is_reasoning(model: str) -> bool:
    return model.lower().startswith(_REASONING_PREFIXES)


def _split_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]


def _format_for_prompt(paragraphs: list[str]) -> str:
    # Truncate each paragraph to keep the prompt small.
    out: list[str] = []
    for i, p in enumerate(paragraphs, start=1):
        snippet = p if len(p) <= 600 else p[:600] + " …"
        out.append(f"[{i}] {snippet}")
    return "\n\n".join(out)


def _coerce_plan(data: object, *, n_paragraphs: int) -> ScenePlan:
    """Validate the LLM JSON; drop any malformed entries."""
    if isinstance(data, dict):
        raw = data.get("plan") or data.get("paragraphs") or []
    else:
        raw = data
    if not isinstance(raw, list):
        raise ValueError("Scene plan is not a list")

    items: list[SceneParagraph] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        try:
            idx = int(entry.get("index", 0))
        except (TypeError, ValueError):
            continue
        if idx < 1 or idx > n_paragraphs:
            continue
        kind = str(entry.get("kind", "narration")).lower()
        if kind not in _ALLOWED_KINDS:
            kind = "narration"
        emphasis = str(entry.get("emphasis", "none")).lower()
        if emphasis not in _ALLOWED_EMPHASIS:
            emphasis = "none"
        try:
            pause = max(0, min(1500, int(entry.get("pause_before_ms", 0))))
        except (TypeError, ValueError):
            pause = 0
        style = str(entry.get("style", "narration-relaxed")).strip() or "narration-relaxed"
        mood = str(entry.get("mood", "")).strip()
        items.append(
            SceneParagraph(
                index=idx,
                kind=kind,
                mood=mood,
                style=style,
                pause_before_ms=pause,
                emphasis=emphasis,
            )
        )
    items.sort(key=lambda x: x.index)
    return ScenePlan(paragraphs=items)


async def analyse_scene(text: str, *, model: str | None = None) -> ScenePlan:
    """Ask Azure OpenAI to label each paragraph for narration."""
    settings = get_settings()
    if not settings.is_openai_configured:
        raise RuntimeError("Azure OpenAI not configured")

    paragraphs = _split_paragraphs(text)
    if not paragraphs:
        return ScenePlan(paragraphs=[])

    model = model or settings.azure_openai_deployment_summary
    credential = get_async_credential()

    async def token_provider() -> str:
        token = await credential.get_token(COGNITIVE_SCOPE)
        return token.token

    client = AsyncAzureOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_version=settings.azure_openai_api_version,
        azure_ad_token_provider=token_provider,
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": USER_TEMPLATE.format(paragraphs=_format_for_prompt(paragraphs)),
        },
    ]

    kwargs: dict[str, object] = {
        "model": model,
        "messages": messages,
        "max_completion_tokens": 4000,
        "response_format": {"type": "json_object"},
    }
    if _is_reasoning(model):
        kwargs["reasoning_effort"] = "minimal"
    else:
        kwargs["temperature"] = 0.2

    async with client:
        resp = await client.chat.completions.create(**kwargs)  # type: ignore[call-overload]

    content = (resp.choices[0].message.content or "").strip()
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Scene plan was not valid JSON: {exc}") from exc

    return _coerce_plan(data, n_paragraphs=len(paragraphs))


# ---------------------------------------------------------------------------
# SSML rendering from a plan
# ---------------------------------------------------------------------------


def _render_planned_paragraph(text: str, plan: SceneParagraph | None) -> str:
    """Render one paragraph using its plan (heading / dialog / narration)."""
    text = text.strip()
    if not text:
        return ""
    style = (plan.style if plan else "narration-relaxed") or "narration-relaxed"
    emphasis = (plan.emphasis if plan else "none") or "none"
    pause = plan.pause_before_ms if plan else 0
    kind = (plan.kind if plan else "narration")

    prefix = f'<break time="{pause}ms"/>' if pause > 0 else ""

    if kind == "heading":
        title = re.sub(r"^#+\s*", "", text).strip()
        return (
            f'{prefix}<break time="400ms"/>'
            f'<emphasis level="moderate">{html.escape(title)}</emphasis>'
            '<break time="600ms"/>'
        )

    body = _render_dialog(text, dialog_style=style)
    if emphasis != "none":
        body = f'<emphasis level="{emphasis}">{body}</emphasis>'
    body = f'<mstts:express-as style="{html.escape(style)}">{body}</mstts:express-as>'
    return f"{prefix}{body}<break time='450ms'/>"


def build_narration_ssml_from_plan(
    text: str,
    plan: ScenePlan,
    voice: VoiceSpec,
    *,
    prosody: ProsodyProfile | None = None,
) -> str:
    """Render SSML using the LLM scene plan (one ``<voice>`` for the whole chapter)."""
    paragraphs = _split_paragraphs(text)
    rendered = "".join(
        _render_planned_paragraph(p, plan.for_index(i))
        for i, p in enumerate(paragraphs, start=1)
    )
    params = _params_attr(prosody)
    return (
        f'<speak version="1.0" {SSML_NS} xml:lang="{voice.locale}">'
        f'<voice name="{voice.voice_name}"{params}>{rendered}</voice></speak>'
    )

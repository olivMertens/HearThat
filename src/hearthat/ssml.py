"""SSML construction for HearThat voices.

Supports three voice families:

* **MAI-Voice-1** (preview) — Microsoft in-house, ``<voice name='en-us-Iris:MAI-Voice-1'>``
  + ``mstts:express-as`` style.
* **DragonHDOmni / HD** — ``parameters="temperature=...;top_p=..."`` plus
  ``mstts:express-as`` with natural-language style descriptions.
* **DragonHDLatest MultiTalker** — ``<mstts:turn speaker="...">`` blocks.

``build_narration_ssml`` is the context-aware variant used by the pipeline:
it adds breaks at paragraphs / headings, wraps quoted dialog in a softer
express-as style, and emphasises Markdown headings.
"""

from __future__ import annotations

import html
import re
from collections.abc import Iterable

from .models import ProsodyProfile, VoiceSpec

SSML_NS = (
    'xmlns="http://www.w3.org/2001/10/synthesis" '
    'xmlns:mstts="http://www.w3.org/2001/mstts"'
)

# Match Markdown headings (#, ##, ###) at the start of a line.
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
# Match double-quoted English dialog OR French guillemets « ... ».
_DIALOG_RE = re.compile(r'(?:"([^"\n]{2,400}?)"|«\s*([^»\n]{2,400}?)\s*»)')


def _params_attr(prosody: ProsodyProfile | None) -> str:
    if prosody is None:
        return ""
    parts: list[str] = []
    if prosody.temperature is not None:
        parts.append(f"temperature={prosody.temperature}")
    if prosody.top_p is not None:
        parts.append(f"top_p={prosody.top_p}")
    if prosody.top_k is not None:
        parts.append(f"top_k={prosody.top_k}")
    if prosody.cfg_scale is not None:
        parts.append(f"cfg_scale={prosody.cfg_scale}")
    if prosody.enhance_pronunciation:
        parts.append("enhancePronunciation=true")
    if not parts:
        return ""
    return f' parameters="{";".join(parts)}"'


def build_ssml(
    text: str,
    voice: VoiceSpec,
    *,
    prosody: ProsodyProfile | None = None,
) -> str:
    """Build a single-voice SSML document for ``text`` (no context analysis)."""
    escaped = html.escape(text)
    body = escaped
    if voice.style:
        body = (
            f'<mstts:express-as style="{html.escape(voice.style)}">{escaped}'
            "</mstts:express-as>"
        )
    params = _params_attr(prosody)
    return (
        f'<speak version="1.0" {SSML_NS} xml:lang="{voice.locale}">'
        f'<voice name="{voice.voice_name}"{params}>{body}</voice></speak>'
    )


# ---------------------------------------------------------------------------
# Context-aware narration SSML
# ---------------------------------------------------------------------------


def _render_dialog(text: str, dialog_style: str) -> str:
    """Wrap quoted segments in a softer express-as style; escape the rest."""
    parts: list[str] = []
    last = 0
    for m in _DIALOG_RE.finditer(text):
        before = text[last : m.start()]
        if before:
            parts.append(html.escape(before))
        spoken = m.group(1) or m.group(2) or ""
        if spoken:
            parts.append(
                f'<mstts:express-as style="{html.escape(dialog_style)}">'
                f"&#8220;{html.escape(spoken)}&#8221;</mstts:express-as>"
            )
        last = m.end()
    tail = text[last:]
    if tail:
        parts.append(html.escape(tail))
    return "".join(parts) if parts else html.escape(text)


def _render_paragraph(text: str, *, dialog_style: str) -> str:
    """Render a single paragraph: heading / dialog detection + breaks."""
    text = text.strip()
    if not text:
        return ""
    heading = _HEADING_RE.match(text)
    if heading:
        title = heading.group(2).strip()
        # Heading: short pause, mild emphasis, longer pause after.
        return (
            '<break time="500ms"/>'
            f'<emphasis level="moderate">{html.escape(title)}</emphasis>'
            '<break time="700ms"/>'
        )
    body = _render_dialog(text, dialog_style=dialog_style)
    # End every paragraph with a longer pause for breathing.
    return f"{body}<break time='450ms'/>"


def build_narration_ssml(
    text: str,
    voice: VoiceSpec,
    *,
    prosody: ProsodyProfile | None = None,
    dialog_style: str = "narration-relaxed",
) -> str:
    """Build a context-aware narration SSML document.

    The text is split on blank lines; each paragraph is annotated with:

    * ``<emphasis>`` + breaks around Markdown headings (``# Title``).
    * a softer ``mstts:express-as`` around quoted dialog.
    * a 450 ms ``<break>`` between paragraphs.

    The outer voice carries the user-selected ``voice.style`` (if any) so the
    overall tone is preserved while individual segments get local treatment.
    """
    paragraphs = re.split(r"\n\s*\n", text.strip())
    rendered = "".join(
        _render_paragraph(p, dialog_style=dialog_style) for p in paragraphs if p.strip()
    )
    if voice.style:
        rendered = (
            f'<mstts:express-as style="{html.escape(voice.style)}">'
            f"{rendered}</mstts:express-as>"
        )
    params = _params_attr(prosody)
    return (
        f'<speak version="1.0" {SSML_NS} xml:lang="{voice.locale}">'
        f'<voice name="{voice.voice_name}"{params}>{rendered}</voice></speak>'
    )


def build_multitalker_ssml(
    turns: Iterable[tuple[str, str]],
    *,
    voice_name: str = "en-US-MultiTalker-Ava-Andrew:DragonHDLatestNeural",
    locale: str = "en-US",
) -> str:
    """Build SSML with ``<mstts:turn>`` blocks: ``[(speaker, text), ...]``."""
    turn_xml = "".join(
        f'<mstts:turn speaker="{html.escape(s)}">{html.escape(t)}</mstts:turn>'
        for s, t in turns
    )
    return (
        f'<speak version="1.0" {SSML_NS} xml:lang="{locale}">'
        f'<voice name="{voice_name}">{turn_xml}</voice></speak>'
    )

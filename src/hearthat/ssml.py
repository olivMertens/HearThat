"""SSML construction for HearThat voices.

Supports three voice families:

* **MAI-Voice-1** (preview) — Microsoft in-house, ``<voice name='en-us-Iris:MAI-Voice-1'>``
  + ``mstts:express-as`` style.
* **DragonHDOmni / HD** — ``parameters="temperature=...;top_p=..."`` plus
  ``mstts:express-as`` with natural-language style descriptions.
* **DragonHDLatest MultiTalker** — ``<mstts:turn speaker="...">`` blocks.
"""

from __future__ import annotations

import html
from collections.abc import Iterable

from .models import ProsodyProfile, VoiceSpec

SSML_NS = (
    'xmlns="http://www.w3.org/2001/10/synthesis" '
    'xmlns:mstts="http://www.w3.org/2001/mstts"'
)


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
    """Build a single-voice SSML document for ``text``."""
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

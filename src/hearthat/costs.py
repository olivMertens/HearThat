"""Centralised pricing constants and cost helpers (USD, May 2026 snapshot)."""

from __future__ import annotations

from .models import Cost

# Azure OpenAI per 1M tokens (May 2026 reference rates).
# Update before invoicing — these are best-effort defaults.
OPENAI_PRICES_PER_1M = {
    "gpt-5.4-mini": {"in": 0.25, "out": 2.00},
    "gpt-5.4-nano": {"in": 0.10, "out": 0.80},
    "gpt-5.5": {"in": 2.50, "out": 10.00},
    "gpt-4.1-mini": {"in": 0.40, "out": 1.60},
    "gpt-4.1-nano": {"in": 0.10, "out": 0.40},
    "gpt-4.1": {"in": 2.00, "out": 8.00},
    "gpt-4o-mini-tts": {"in": 0.60, "out": 12.00},  # text in, audio out
}

# Per 1M neural characters.
SPEECH_HD_USD_PER_1M_CHARS = 30.0
SPEECH_MAI_USD_PER_1M_CHARS = 30.0  # preview, assume parity

# Per 1M source characters.
TRANSLATOR_USD_PER_1M_CHARS = 10.0


def summary_usd(model: str, tokens_in: int, tokens_out: int) -> float:
    """Compute USD cost for a Chat Completion call."""
    rates = OPENAI_PRICES_PER_1M.get(model, {"in": 0.5, "out": 2.0})
    return (tokens_in * rates["in"] + tokens_out * rates["out"]) / 1_000_000


def tts_usd(chars: int, backend: str = "azure_speech_hd") -> float:
    rate = SPEECH_MAI_USD_PER_1M_CHARS if "mai" in backend else SPEECH_HD_USD_PER_1M_CHARS
    return chars * rate / 1_000_000


def translation_usd(chars: int) -> float:
    return chars * TRANSLATOR_USD_PER_1M_CHARS / 1_000_000


def build_cost(
    *,
    model: str,
    tokens_in: int = 0,
    tokens_out: int = 0,
    tts_chars: int = 0,
    tts_backend: str = "azure_speech_hd",
    translation_chars: int = 0,
) -> Cost:
    """Build a :class:`Cost` from raw usage counters."""
    return Cost(
        summary_tokens_in=tokens_in,
        summary_tokens_out=tokens_out,
        summary_usd=summary_usd(model, tokens_in, tokens_out),
        tts_neural_chars=tts_chars,
        tts_usd=tts_usd(tts_chars, tts_backend),
        translation_chars=translation_chars,
        translation_usd=translation_usd(translation_chars),
    )

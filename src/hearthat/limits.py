"""Demo-friendly hard limits for ingestion + synthesis.

Sources (verified May 2026):
- Document Intelligence prebuilt-layout: max **500 MB** file, **2000 pages**
  (S0 tier). https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/service-limits
- Azure Speech **Batch Synthesis**: SSML input <= **50 000 characters per file**,
  request body <= **2 MB**, up to **1000 inputs** per request.
  https://learn.microsoft.com/en-us/azure/ai-services/speech-service/batch-synthesis
- OpenAI ``gpt-4o-mini-tts``: **4096 input tokens** per request
  (~ 12 000 characters). https://platform.openai.com/docs/guides/text-to-speech

The values below are intentionally tighter than the service ceilings so a
demo upload finishes in a reasonable time and stays within free-tier quotas.
"""

from __future__ import annotations

from typing import Final

# ---------- Upload limits ----------
MAX_UPLOAD_BYTES: Final[int] = 25 * 1024 * 1024  # 25 MB
MAX_PDF_PAGES: Final[int] = 200
MAX_TEXT_CHARS: Final[int] = 500_000  # ~120 pages worth of plain text

# ---------- Per-chapter chunking for TTS ----------
# Speech Batch Synthesis caps SSML at 50 000 chars/input; we leave headroom.
MAX_SSML_CHARS: Final[int] = 40_000
# OpenAI TTS caps around 4096 input tokens (~12k chars); we cap conservatively.
MAX_OPENAI_TTS_CHARS: Final[int] = 4_000

# ---------- Accepted MIME types / extensions ----------
ALLOWED_EXTENSIONS: Final[tuple[str, ...]] = (".pdf", ".txt", ".md", ".markdown")
ALLOWED_MIME_TYPES: Final[tuple[str, ...]] = (
    "application/pdf",
    "text/plain",
    "text/markdown",
    "text/x-markdown",
)


def human_size(num_bytes: int) -> str:
    """Format ``num_bytes`` as a short human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if num_bytes < 1024 or unit == "GB":
            return f"{num_bytes:.0f} {unit}" if unit == "B" else f"{num_bytes / 1024:.1f} {unit}"
        num_bytes //= 1024
    return f"{num_bytes} B"

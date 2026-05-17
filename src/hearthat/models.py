"""Domain models shared by ingestion, summarisation, TTS, and translation."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Book / chapter / figure
# ---------------------------------------------------------------------------


class Figure(BaseModel):
    """A figure or image extracted from the source PDF."""

    page: int
    caption: str | None = None
    image_path: Path | None = None
    description: str | None = None  # Filled by hearthat.vision


class Chapter(BaseModel):
    """One chapter of a book."""

    index: int
    title: str
    text: str
    summary: str | None = None
    figures: list[Figure] = Field(default_factory=list)
    audio_path: Path | None = None


class Book(BaseModel):
    """A parsed book with chapters and metadata."""

    title: str
    source_path: Path
    chapters: list[Chapter] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# TTS / voices
# ---------------------------------------------------------------------------


TtsBackend = Literal["azure_speech_mai", "azure_speech_hd", "openai_tts"]


class VoiceSpec(BaseModel):
    """Voice selection for a TTS job."""

    backend: TtsBackend = "azure_speech_mai"
    voice_name: str = "en-us-Iris:MAI-Voice-1"
    style: str | None = None  # mstts:express-as style (Speech) or instructions (OpenAI)
    locale: str = "en-US"


class ProsodyProfile(BaseModel):
    """Optional prosody tuning for DragonHDOmni / HD voices."""

    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    cfg_scale: float | None = None
    enhance_pronunciation: bool = False


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------


class JobStatus(StrEnum):
    PENDING = "pending"
    INGESTING = "ingesting"
    SUMMARIZING = "summarizing"
    SYNTHESIZING = "synthesizing"
    TRANSLATING = "translating"
    COMPLETED = "completed"
    FAILED = "failed"


class AudioJob(BaseModel):
    """Persisted job tracked by the UI in SQLite."""

    id: str
    source_path: Path
    status: JobStatus = JobStatus.PENDING
    progress: float = 0.0  # 0.0 -> 1.0
    voice: VoiceSpec = Field(default_factory=VoiceSpec)
    summary_model: str = "gpt-5.4-mini"
    error: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    result_dir: Path | None = None


# ---------------------------------------------------------------------------
# Cost reporting
# ---------------------------------------------------------------------------


class Cost(BaseModel):
    """Cost breakdown for a single job."""

    summary_tokens_in: int = 0
    summary_tokens_out: int = 0
    summary_usd: float = 0.0
    tts_neural_chars: int = 0
    tts_usd: float = 0.0
    translation_chars: int = 0
    translation_usd: float = 0.0

    @property
    def total_usd(self) -> float:
        return self.summary_usd + self.tts_usd + self.translation_usd

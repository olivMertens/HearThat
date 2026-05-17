"""Smoke tests — verify the package imports cleanly and core helpers work."""

from __future__ import annotations

from pathlib import Path

import pytest

import hearthat
from hearthat import ssml
from hearthat.config import Settings
from hearthat.translate import _chunk


def test_version() -> None:
    assert hearthat.__version__


def test_settings_defaults_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_SPEECH_ENDPOINT",
        "AZURE_SPEECH_REGION",
        "AZURE_TRANSLATOR_ENDPOINT",
    ):
        monkeypatch.delenv(key, raising=False)
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.azure_openai_endpoint == ""
    assert s.is_translator_configured is False


def test_chunk_short_text_returns_single() -> None:
    text = "hello world"
    assert _chunk(text) == [text]


def test_chunk_splits_on_paragraph_boundary() -> None:
    para = "x" * 20_000 + "\n\n" + "y" * 20_000 + "\n\n" + "z" * 20_000
    chunks = _chunk(para, limit=25_000)
    assert len(chunks) >= 2
    assert all(len(c) <= 25_000 for c in chunks)


def test_ssml_module_exists() -> None:
    assert hasattr(ssml, "__file__")
    assert Path(ssml.__file__).exists()

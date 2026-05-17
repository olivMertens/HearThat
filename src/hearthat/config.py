"""Runtime configuration loaded from environment variables / .env.

Only endpoints and deployment names live here — credentials come from
Entra ID via DefaultAzureCredential (see ``hearthat.auth``).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings.

    All values come from the environment or a local ``.env`` file. No API
    keys are accepted — we authenticate with ``DefaultAzureCredential``.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---------- Azure OpenAI ----------
    azure_openai_endpoint: str = Field(default="")
    azure_openai_api_version: str = Field(default="2024-12-01-preview")
    azure_openai_deployment_summary: str = Field(default="gpt-5.4-mini")
    azure_openai_deployment_vision: str = Field(default="gpt-5.4-mini")
    azure_openai_deployment_tts: str = Field(default="gpt-4o-mini-tts")
    azure_openai_deployment_transcribe: str = Field(default="gpt-4o-mini-transcribe")

    # ---------- Azure Speech ----------
    azure_speech_endpoint: str = Field(default="")
    azure_speech_region: str = Field(default="eastus")
    hearthat_default_voice: str = Field(default="en-us-Iris:MAI-Voice-1")
    hearthat_fallback_voice: str = Field(default="en-US-Ava:DragonHDOmniLatestNeural")

    # ---------- Document Intelligence ----------
    azure_docintel_endpoint: str = Field(default="")

    # ---------- Translator ----------
    azure_translator_endpoint: str = Field(default="")

    # ---------- Storage ----------
    azure_storage_account_name: str = Field(default="")
    azure_storage_source_container: str = Field(default="source")
    azure_storage_target_container: str = Field(default="target")

    # ---------- Runtime ----------
    hearthat_data_dir: Path = Field(default=Path("./data"))
    hearthat_db_path: Path = Field(default=Path("./hearthat.db"))
    hearthat_log_level: str = Field(default="INFO")

    @property
    def is_openai_configured(self) -> bool:
        return bool(self.azure_openai_endpoint)

    @property
    def is_speech_configured(self) -> bool:
        return bool(self.azure_speech_endpoint or self.azure_speech_region)

    @property
    def is_docintel_configured(self) -> bool:
        return bool(self.azure_docintel_endpoint)

    @property
    def is_translator_configured(self) -> bool:
        return bool(self.azure_translator_endpoint)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()

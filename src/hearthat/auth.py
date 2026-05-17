"""Shared credential helpers.

In production we use ``DefaultAzureCredential`` (Entra ID) only. For local
development — where Entra-only access often isn't available — the helpers
below transparently fall back to API keys when ``HEARTHAT_ENV != 'prod'``
and the matching ``*_API_KEY`` is set. Keys are *never* required.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from azure.core.credentials import AzureKeyCredential, TokenCredential
from azure.identity import DefaultAzureCredential
from azure.identity.aio import DefaultAzureCredential as AsyncDefaultAzureCredential

from .config import Settings, get_settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_credential() -> TokenCredential:
    """Return a process-wide sync Entra ID credential."""
    return DefaultAzureCredential()


@lru_cache(maxsize=1)
def get_async_credential() -> AsyncDefaultAzureCredential:
    """Return a process-wide async Entra ID credential."""
    return AsyncDefaultAzureCredential()


# Azure Cognitive Services token scope (Speech, DocIntel, Translator, OpenAI).
COGNITIVE_SCOPE = "https://cognitiveservices.azure.com/.default"


# ---------------------------------------------------------------------------
# Dev-mode API-key fallback
# ---------------------------------------------------------------------------


def aoai_client_kwargs(settings: Settings | None = None) -> dict[str, Any]:
    """Return the kwargs to pass to ``AsyncAzureOpenAI``.

    In dev with a key configured, returns ``{"api_key": ...}``; otherwise
    returns an ``azure_ad_token_provider`` bound to the async credential.
    The caller adds ``azure_endpoint`` and ``api_version`` themselves.
    """
    settings = settings or get_settings()
    if settings.use_openai_key:
        logger.debug("Using Azure OpenAI API key (dev mode)")
        return {"api_key": settings.azure_openai_api_key}

    credential = get_async_credential()

    async def token_provider() -> str:
        token = await credential.get_token(COGNITIVE_SCOPE)
        return token.token

    return {"azure_ad_token_provider": token_provider}


def docintel_credential(
    settings: Settings | None = None,
) -> AzureKeyCredential | AsyncDefaultAzureCredential:
    """Return the credential to pass to the Document Intelligence client."""
    settings = settings or get_settings()
    if settings.use_docintel_key:
        logger.debug("Using Document Intelligence API key (dev mode)")
        return AzureKeyCredential(settings.azure_docintel_api_key)
    return get_async_credential()


async def speech_auth_headers(settings: Settings | None = None) -> dict[str, str]:
    """Return the headers to use for an Azure Speech REST call."""
    settings = settings or get_settings()
    if settings.use_speech_key:
        logger.debug("Using Azure Speech API key (dev mode)")
        return {"Ocp-Apim-Subscription-Key": settings.azure_speech_api_key}
    credential = get_async_credential()
    token = await credential.get_token(COGNITIVE_SCOPE)
    return {"Authorization": f"Bearer {token.token}"}

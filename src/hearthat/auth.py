"""Shared Entra ID credential — no API keys at runtime.

``DefaultAzureCredential`` walks a chain (env vars, managed identity, Azure CLI,
VS Code, etc.). Run ``az login`` once locally and everything else is automatic.
"""

from __future__ import annotations

from functools import lru_cache

from azure.core.credentials import TokenCredential
from azure.identity import DefaultAzureCredential
from azure.identity.aio import DefaultAzureCredential as AsyncDefaultAzureCredential


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

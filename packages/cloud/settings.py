"""Azure settings from the environment (names in config/.env.example; values written by `azd env` or Key Vault)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or default


def cloud_enabled() -> bool:
    return (_env("WHYLINE_CLOUD", "0") or "0").lower() in ("1", "true", "yes")


@dataclass(frozen=True)
class AzureSettings:
    cosmos_endpoint: str | None
    cosmos_database: str
    cosmos_checkpoint_container: str
    cosmos_blackboard_container: str
    webpubsub_endpoint: str | None
    webpubsub_connection_string: str | None
    webpubsub_hub: str
    appinsights_connection_string: str | None
    foundry_project_endpoint: str | None
    foundry_model_deployment: str | None
    managed_identity_client_id: str | None

    @classmethod
    def from_env(cls) -> AzureSettings:
        return cls(
            cosmos_endpoint=_env("AZURE_COSMOS_ENDPOINT"),
            cosmos_database=_env("AZURE_COSMOS_DATABASE_NAME", "whyline"),
            cosmos_checkpoint_container=_env("AZURE_COSMOS_CONTAINER_NAME", "checkpoints"),
            cosmos_blackboard_container=_env("AZURE_COSMOS_BLACKBOARD_CONTAINER", "blackboard"),
            webpubsub_endpoint=_env("AZURE_WEBPUBSUB_ENDPOINT"),
            webpubsub_connection_string=_env("AZURE_WEBPUBSUB_CONNECTION_STRING"),
            webpubsub_hub=_env("AZURE_WEBPUBSUB_HUB", "cues"),
            appinsights_connection_string=_env("APPLICATIONINSIGHTS_CONNECTION_STRING"),
            foundry_project_endpoint=_env("FOUNDRY_PROJECT_ENDPOINT"),
            foundry_model_deployment=_env("FOUNDRY_MODEL_DEPLOYMENT"),
            managed_identity_client_id=_env("AZURE_CLIENT_ID"),
        )

    @property
    def has_cosmos(self) -> bool:
        return bool(self.cosmos_endpoint)

    @property
    def has_webpubsub(self) -> bool:
        return bool(self.webpubsub_endpoint or self.webpubsub_connection_string)

    @property
    def has_foundry(self) -> bool:
        return bool(self.foundry_project_endpoint and self.foundry_model_deployment)


@lru_cache(maxsize=1)
def settings() -> AzureSettings:
    return AzureSettings.from_env()


@lru_cache(maxsize=1)
def credential():
    """DefaultAzureCredential: managed identity in Container Apps (AZURE_CLIENT_ID for a user-assigned one),
    the developer's `az login` locally."""
    from azure.identity import DefaultAzureCredential

    return DefaultAzureCredential(managed_identity_client_id=settings().managed_identity_client_id)


@lru_cache(maxsize=1)
def async_credential():
    from azure.identity.aio import DefaultAzureCredential

    return DefaultAzureCredential(managed_identity_client_id=settings().managed_identity_client_id)

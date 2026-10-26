"""cloud: the Azure deployment path, switched on by WHYLINE_CLOUD=1.

Locally every service runs on SQLite, FileCheckpointStorage and the in-process cue forwarder. With WHYLINE_CLOUD=1
the same processes read their Azure endpoints from the environment (azd writes them from infra/main.bicep outputs):

    blackboard   AZURE_COSMOS_ENDPOINT, AZURE_COSMOS_DATABASE_NAME, AZURE_COSMOS_BLACKBOARD_CONTAINER
    checkpoints  AZURE_COSMOS_ENDPOINT, AZURE_COSMOS_DATABASE_NAME, AZURE_COSMOS_CONTAINER_NAME
    cue fan-out  AZURE_WEBPUBSUB_ENDPOINT + AZURE_WEBPUBSUB_HUB, or AZURE_WEBPUBSUB_CONNECTION_STRING
    telemetry    APPLICATIONINSIGHTS_CONNECTION_STRING
    models       FOUNDRY_PROJECT_ENDPOINT, FOUNDRY_MODEL_DEPLOYMENT (provider `foundry` in config/models.yaml,
                 or WHYLINE_LLM_PROVIDER=foundry to route every Gemini role through Azure AI Foundry)

Credentials come from DefaultAzureCredential (managed identity in Container Apps, `az login` on a laptop); keys
are never read from files in the repository. Every factory falls back to the local implementation when its
settings are absent, so a half-configured environment degrades instead of failing at start-up.
"""

from cloud.factory import make_blackboard, make_checkpoint_storage, make_cue_publisher
from cloud.settings import AzureSettings, cloud_enabled, settings

__all__ = ["AzureSettings", "cloud_enabled", "make_blackboard", "make_checkpoint_storage", "make_cue_publisher",
           "settings"]

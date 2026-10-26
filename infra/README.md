# Pitchsight infrastructure (Azure)

`azure.yaml` (repo root) declares six services for azd 1.36.0: `api`, `mcp`, `newsroom` on Azure Container Apps
(consumption plan, scale to zero) and `overlay`, `studio`, `fan` on Azure Static Web Apps (free plan).
`main.bicep` creates the resource group; `resources.bicep` creates everything in it (ADR-009):

| Resource | Tier | Used by | Code |
|---|---|---|---|
| Log Analytics + Application Insights | pay per GB | agent spans from every service | `packages/cloud/telemetry.py` |
| User-assigned managed identity | free | all three Container Apps (no keys in app settings) | `packages/cloud/settings.py` |
| Container Registry | Basic | the python image (`docker/python.Dockerfile`) | `azure.yaml` |
| Cosmos DB for NoSQL, database `whyline` | serverless | `blackboard` container (facts, moments, cues, traces), `checkpoints` container (workflow resume) | `packages/cloud/cosmos_blackboard.py`, `packages/cloud/factory.py` |
| Web PubSub, hub `cues` | Free_F1 | cue fan-out to the screens; `GET /cues/negotiate` issues client URLs | `packages/cloud/pubsub.py`, `packages/api/cues.py` |
| Key Vault (RBAC) | standard | the Gemini key when the Vertex route is not used | |
| Azure AI Foundry resource + project `pitchsight`, two model deployments | S0, GlobalStandard | the model roles when `WHYLINE_LLM_PROVIDER=foundry` | `packages/newsroom/llm.py` (`foundry` provider), `packages/newsroom/config.py` |
| Container Apps environment + `api`, `mcp`, `newsroom` | consumption | the services | |
| Static Web Apps `overlay`, `studio`, `fan` | Free | the screens | |

Every service reads its Azure settings from environment variables (`config/.env.example`). Container Apps get
them from the Bicep template; for a laptop run against the cloud stores, `azd env get-values > .env` and
`az login`. With `WHYLINE_CLOUD=0` (the default) nothing in `packages/cloud` touches Azure and the stack runs on
SQLite, FileCheckpointStorage and the api's own WebSocket.

No subscription IDs, tenant IDs or keys belong in this folder; authentication is Entra ID throughout
(`disableLocalAuth` on Cosmos DB, Web PubSub and Foundry).

## Deploy

```bash
az login && azd auth login
azd env new pitchsight --location swedencentral
azd env set AZURE_PRINCIPAL_ID "$(az ad signed-in-user show --query id -o tsv)"
azd up
```

Parameters: `reasoningModelName` and `fastModelName` (Foundry model deployments; pick models available in the
chosen region), `principalId` (data access for the developer). Pick a region that offers Static Web Apps, Web
PubSub Free and the two models.

Check without deploying: `az bicep build --file infra/main.bicep --stdout > /dev/null`.

## Status (26 Oct 2026)

The submission demo and video ran on the local stack with Gemini on Vertex AI. The Azure template and the
`packages/cloud` code path are in the repository; an Azure subscription has not been provisioned for this entry
yet (owner step), so `azd up` has not been run.

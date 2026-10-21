# WHYLINE infrastructure

`azure.yaml` (repo root) declares six services for azd 1.36.0: `api`, `mcp`, `newsroom` on Azure Container Apps
(consumption plan, scale to zero) and `overlay`, `studio`, `fan` on Azure Static Web Apps (free plan). `main.bicep`
targets the subscription and creates one resource group `rg-<environmentName>`; T-052 adds the resource modules.

| Setting | Value |
|---|---|
| Subscription type | **Not set yet** (owner action, T-009 human step). Trial or pay-as-you-go decides only whether Foundry Evaluations can be shown (TECH_PLAN 1.14, question 5); Claude is called directly either way. |
| Region | **Not set yet**; pick one region for every resource when running `azd env new`. |
| Event Hubs | Optional. Direct `POST /ingest/*` to the `api` container is the default; Event Hubs Basic is only for the judging period, paid from trial credit (ADR-009). |

No subscription IDs, tenant IDs or keys belong in this folder. Keys live in Key Vault (T-052) and the local `.env`.

## Owner set-up (not done by a session)

1. Create the Azure free account.
2. Install the CLIs: `brew install azure-cli` and azd 1.36.0 (`brew tap azure/azd && brew install azd`).
3. Log in yourself: `az login` and `azd auth login`.
4. Record the subscription type and region in the table above.

Check: `az bicep build --file infra/main.bicep --stdout > /dev/null && azd version`

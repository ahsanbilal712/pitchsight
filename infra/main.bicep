// Pitchsight infrastructure entry point (T-009, T-052; ADR-009, TECH_PLAN 1.10). `azd up` deploys it.
// Subscription scope: one resource group, then every resource in resources.bicep. The outputs become azd
// environment values, which the services read as the environment variables listed in config/.env.example.
targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('azd environment name; prefixes every resource')
param environmentName string

@minLength(1)
@description('Azure region for all resources')
param location string

@description('Object id of the developer running azd, granted data access for local runs against the cloud stores')
param principalId string = ''

@description('Azure AI Foundry model deployment for the reasoning roles (Tactician, Panel, recap)')
param reasoningModelName string = 'gpt-5.1'

@description('Azure AI Foundry model deployment for the fast roles (Proposer, Narrator)')
param fastModelName string = 'gpt-5.1-mini'

var tags = {
  'azd-env-name': environmentName
  project: 'pitchsight'
}

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

module resources 'resources.bicep' = {
  name: 'pitchsight-resources'
  scope: rg
  params: {
    environmentName: environmentName
    location: location
    tags: tags
    principalId: principalId
    reasoningModelName: reasoningModelName
    fastModelName: fastModelName
  }
}

output AZURE_LOCATION string = location
output AZURE_RESOURCE_GROUP string = rg.name
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = resources.outputs.registryEndpoint
output AZURE_COSMOS_ENDPOINT string = resources.outputs.cosmosEndpoint
output AZURE_COSMOS_DATABASE_NAME string = resources.outputs.cosmosDatabase
output AZURE_COSMOS_CONTAINER_NAME string = 'checkpoints'
output AZURE_COSMOS_BLACKBOARD_CONTAINER string = 'blackboard'
output AZURE_WEBPUBSUB_ENDPOINT string = resources.outputs.webPubSubEndpoint
output AZURE_WEBPUBSUB_HUB string = 'cues'
output AZURE_KEY_VAULT_ENDPOINT string = resources.outputs.keyVaultEndpoint
output APPLICATIONINSIGHTS_CONNECTION_STRING string = resources.outputs.appInsightsConnectionString
output FOUNDRY_PROJECT_ENDPOINT string = resources.outputs.foundryProjectEndpoint
output FOUNDRY_MODEL_DEPLOYMENT_REASONING string = reasoningModelName
output FOUNDRY_MODEL_DEPLOYMENT_FAST string = fastModelName
output AZURE_CLIENT_ID string = resources.outputs.identityClientId
output SERVICE_API_URI string = resources.outputs.apiUri

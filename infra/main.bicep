// WHYLINE infrastructure entry point (T-009). Subscription scope, one resource group, no resources yet.
// T-052 adds the modules listed in TECH_PLAN 1.10: monitoring, cosmos, webpubsub, aca-env, aca-app (x3),
// swa (x3), keyvault and the optional eventhubs.
targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('azd environment name; prefixes every resource')
param environmentName string

@minLength(1)
@description('Azure region for all resources')
param location string

var tags = {
  'azd-env-name': environmentName
  project: 'whyline'
}

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

output AZURE_LOCATION string = location
output AZURE_RESOURCE_GROUP string = rg.name

// Pitchsight resources (ADR-009): free or consumption tiers throughout, scale to zero when idle.
//   monitoring   Log Analytics + Application Insights (agent spans, TECH_PLAN 1.9)
//   identity     one user-assigned managed identity for the three Container Apps (no keys in app settings)
//   registry     Azure Container Registry (Basic) for the python image
//   cosmos       Cosmos DB for NoSQL, serverless: database `whyline`, containers `blackboard` and `checkpoints`
//   webpubsub    Web PubSub (Free_F1), hub `cues`: cue fan-out to the screens
//   keyvault     Key Vault (RBAC) for the Gemini key when the Vertex route is not used
//   foundry      Azure AI Foundry resource + project, two model deployments
//   apps         Container Apps environment + api, mcp, newsroom; Static Web Apps for overlay, studio, fan
targetScope = 'resourceGroup'

param environmentName string
param location string
param tags object
param principalId string
param reasoningModelName string
param fastModelName string

var token = toLower(uniqueString(subscription().id, resourceGroup().id, environmentName))
var dbName = 'whyline'

// ---------------------------------------------------------------- monitoring
resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${token}'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-${token}'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logs.id
  }
}

// ---------------------------------------------------------------- identity
resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${token}'
  location: location
  tags: tags
}

// ---------------------------------------------------------------- registry
resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: 'cr${token}'
  location: location
  tags: tags
  sku: { name: 'Basic' }
  properties: { adminUserEnabled: false }
}

resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, identity.id, 'acrpull')
  scope: registry
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
  }
}

// ---------------------------------------------------------------- cosmos
resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' = {
  name: 'cosmos-${token}'
  location: location
  tags: tags
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    locations: [ { locationName: location, failoverPriority: 0 } ]
    capabilities: [ { name: 'EnableServerless' } ]
    disableLocalAuth: true
    consistencyPolicy: { defaultConsistencyLevel: 'Session' }
  }
}

resource cosmosDb 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-05-15' = {
  parent: cosmos
  name: dbName
  properties: { resource: { id: dbName } }
}

resource blackboardContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: cosmosDb
  name: 'blackboard'
  properties: {
    resource: {
      id: 'blackboard'
      partitionKey: { paths: [ '/match_id' ], kind: 'Hash' }
      indexingPolicy: {
        indexingMode: 'consistent'
        includedPaths: [ { path: '/*' } ]
        excludedPaths: [ { path: '/doc/*' } ]
        compositeIndexes: [
          [ { path: '/collection', order: 'ascending' }, { path: '/seq', order: 'ascending' } ]
        ]
      }
    }
  }
}

resource checkpointContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: cosmosDb
  name: 'checkpoints'
  properties: {
    resource: {
      id: 'checkpoints'
      partitionKey: { paths: [ '/workflow_name' ], kind: 'Hash' }
    }
  }
}

// Cosmos DB Built-in Data Contributor for the apps and the developer
resource cosmosAppRole 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-05-15' = {
  parent: cosmos
  name: guid(cosmos.id, identity.id, 'data-contributor')
  properties: {
    principalId: identity.properties.principalId
    roleDefinitionId: '${cosmos.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002'
    scope: cosmos.id
  }
}

resource cosmosDevRole 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-05-15' = if (!empty(principalId)) {
  parent: cosmos
  name: guid(cosmos.id, principalId, 'data-contributor')
  properties: {
    principalId: principalId
    roleDefinitionId: '${cosmos.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002'
    scope: cosmos.id
  }
}

// ---------------------------------------------------------------- web pubsub
resource webPubSub 'Microsoft.SignalRService/webPubSub@2024-03-01' = {
  name: 'wps-${token}'
  location: location
  tags: tags
  sku: { name: 'Free_F1', capacity: 1 }
  properties: { disableLocalAuth: true }
}

resource webPubSubHub 'Microsoft.SignalRService/webPubSub/hubs@2024-03-01' = {
  parent: webPubSub
  name: 'cues'
  properties: { anonymousConnectPolicy: 'deny' }
}

resource webPubSubOwner 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(webPubSub.id, identity.id, 'wps-owner')
  scope: webPubSub
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '12cf5a90-567b-43ae-8102-96cf46c7d9b4')
  }
}

// ---------------------------------------------------------------- key vault
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: 'kv-${token}'
  location: location
  tags: tags
  properties: {
    tenantId: subscription().tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
  }
}

resource keyVaultReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, identity.id, 'kv-secrets-user')
  scope: keyVault
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
  }
}

// ---------------------------------------------------------------- azure ai foundry
resource foundry 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: 'aif-${token}'
  location: location
  tags: tags
  kind: 'AIServices'
  sku: { name: 'S0' }
  identity: { type: 'SystemAssigned' }
  properties: {
    customSubDomainName: 'aif-${token}'
    allowProjectManagement: true
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
  }
}

resource foundryProject 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  parent: foundry
  name: 'pitchsight'
  location: location
  identity: { type: 'SystemAssigned' }
  properties: {
    displayName: 'Pitchsight'
    description: 'Pitchsight newsroom agents: Proposer, Tactician, Narrator'
  }
}

resource reasoningDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: foundry
  name: reasoningModelName
  sku: { name: 'GlobalStandard', capacity: 50 }
  properties: {
    model: { format: 'OpenAI', name: reasoningModelName }
  }
}

resource fastDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: foundry
  name: fastModelName
  sku: { name: 'GlobalStandard', capacity: 100 }
  properties: {
    model: { format: 'OpenAI', name: fastModelName }
  }
  dependsOn: [ reasoningDeployment ]
}

// Azure AI User on the Foundry resource for the apps and the developer
resource foundryAppRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(foundry.id, identity.id, 'azure-ai-user')
  scope: foundry
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '53ca6127-db72-4b80-b1b0-d745d6d5456d')
  }
}

resource foundryDevRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(foundry.id, principalId, 'azure-ai-user')
  scope: foundry
  properties: {
    principalId: principalId
    principalType: 'User'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '53ca6127-db72-4b80-b1b0-d745d6d5456d')
  }
}

// ---------------------------------------------------------------- container apps
resource acaEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-${token}'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
  }
}

var foundryProjectEndpoint = 'https://${foundry.properties.customSubDomainName}.services.ai.azure.com/api/projects/${foundryProject.name}'

var commonEnv = [
  { name: 'WHYLINE_CLOUD', value: '1' }
  { name: 'WHYLINE_MODE', value: 'live' }
  { name: 'WHYLINE_LLM_PROVIDER', value: 'foundry' }
  { name: 'AZURE_CLIENT_ID', value: identity.properties.clientId }
  { name: 'AZURE_COSMOS_ENDPOINT', value: cosmos.properties.documentEndpoint }
  { name: 'AZURE_COSMOS_DATABASE_NAME', value: dbName }
  { name: 'AZURE_COSMOS_CONTAINER_NAME', value: 'checkpoints' }
  { name: 'AZURE_COSMOS_BLACKBOARD_CONTAINER', value: 'blackboard' }
  { name: 'AZURE_WEBPUBSUB_ENDPOINT', value: 'https://${webPubSub.properties.hostName}' }
  { name: 'AZURE_WEBPUBSUB_HUB', value: 'cues' }
  { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsights.properties.ConnectionString }
  { name: 'FOUNDRY_PROJECT_ENDPOINT', value: foundryProjectEndpoint }
  { name: 'FOUNDRY_MODEL_DEPLOYMENT_REASONING', value: reasoningModelName }
  { name: 'FOUNDRY_MODEL_DEPLOYMENT_FAST', value: fastModelName }
]

var services = [
  { name: 'api', command: [ 'uvicorn', 'api.main:app', '--host', '0.0.0.0', '--port', '8000' ], port: 8000, external: true }
  { name: 'mcp', command: [ 'python', '-m', 'mcp_server' ], port: 8080, external: false }
  { name: 'newsroom', command: [ 'python', '-m', 'newsroom.supervisor', '--mode', 'live' ], port: 0, external: false }
]

resource apps 'Microsoft.App/containerApps@2024-03-01' = [for svc in services: {
  name: 'ca-${svc.name}-${token}'
  location: location
  tags: union(tags, { 'azd-service-name': svc.name })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identity.id}': {} }
  }
  properties: {
    managedEnvironmentId: acaEnv.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: svc.port == 0 ? null : {
        external: svc.external
        targetPort: svc.port
        transport: 'auto'
      }
      registries: [ { server: registry.properties.loginServer, identity: identity.id } ]
    }
    template: {
      containers: [
        {
          name: svc.name
          image: 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'   // azd deploy replaces it
          command: svc.command
          env: union(commonEnv, svc.name == 'mcp' ? [] : [
            { name: 'WHYLINE_MCP_URL', value: 'https://ca-mcp-${token}.internal.${acaEnv.properties.defaultDomain}/mcp' }
          ])
          resources: { cpu: json('1.0'), memory: '2Gi' }
        }
      ]
      scale: { minReplicas: 0, maxReplicas: svc.name == 'newsroom' ? 1 : 2 }
    }
  }
  dependsOn: [ acrPull ]
}]

// ---------------------------------------------------------------- static web apps (screens)
resource screens 'Microsoft.Web/staticSites@2023-12-01' = [for app in [ 'overlay', 'studio', 'fan' ]: {
  name: 'swa-${app}-${token}'
  location: location
  tags: union(tags, { 'azd-service-name': app })
  sku: { name: 'Free', tier: 'Free' }
  properties: {}
}]

output registryEndpoint string = registry.properties.loginServer
output cosmosEndpoint string = cosmos.properties.documentEndpoint
output cosmosDatabase string = dbName
output webPubSubEndpoint string = 'https://${webPubSub.properties.hostName}'
output keyVaultEndpoint string = keyVault.properties.vaultUri
output appInsightsConnectionString string = appInsights.properties.ConnectionString
output foundryProjectEndpoint string = foundryProjectEndpoint
output identityClientId string = identity.properties.clientId
output apiUri string = 'https://${apps[0].properties.configuration.ingress.fqdn}'

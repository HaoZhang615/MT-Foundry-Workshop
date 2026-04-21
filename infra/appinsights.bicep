// Additive App Insights template for pre-provisioned Foundry environments.
// Deploys: Log Analytics + App Insights + Foundry connection + RBAC
// Does NOT modify the existing Foundry account or its deployments.

targetScope = 'resourceGroup'

@description('Azure region for all resources')
param location string

@description('Name of the EXISTING AI Foundry account (AI Services)')
param foundryAccountName string

@description('Principal ID of the deployer for RBAC assignments')
param deployerPrincipalId string

// ============================================================================
// Reference the EXISTING Foundry account (read-only — no modifications)
// ============================================================================

resource foundry 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  name: foundryAccountName
}

// ============================================================================
// Log Analytics Workspace (for Application Insights)
// ============================================================================

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${foundryAccountName}-logs'
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

// ============================================================================
// Application Insights (for tracing)
// ============================================================================

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: '${foundryAccountName}-insights'
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

// ============================================================================
// Application Insights Connection — auto-connects App Insights to Foundry
// ============================================================================

resource appInsightsConnection 'Microsoft.CognitiveServices/accounts/connections@2025-04-01-preview' = {
  name: 'appinsights-connection'
  parent: foundry
  properties: {
    category: 'AppInsights'
    target: appInsights.id
    authType: 'ApiKey'
    isSharedToAll: true
    credentials: {
      key: appInsights.properties.ConnectionString
    }
    metadata: {
      ApiType: 'Azure'
      ResourceId: appInsights.id
    }
  }
}

// ============================================================================
// RBAC: Log Analytics Reader — needed for viewing traces
// ============================================================================

resource logAnalyticsReaderRole 'Microsoft.Authorization/roleDefinitions@2022-04-01' existing = {
  name: '73c42c96-874c-492b-b04d-ab87d138a893'
}

resource assignLogAnalyticsReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: logAnalytics
  name: guid(logAnalytics.id, deployerPrincipalId, logAnalyticsReaderRole.id)
  properties: {
    roleDefinitionId: logAnalyticsReaderRole.id
    principalId: deployerPrincipalId
    principalType: 'User'
    description: 'Allow workshop participant to view traces in Log Analytics'
  }
}

// ============================================================================
// Outputs
// ============================================================================

output appInsightsConnectionString string = appInsights.properties.ConnectionString
output appInsightsName string = appInsights.name
output logAnalyticsWorkspaceId string = logAnalytics.id

// Microsoft Foundry Workshop — Infrastructure Template
// Deploys: AI Services + Project, Model Deployment, App Insights, RBAC

targetScope = 'resourceGroup'

@description('Azure region for all resources')
param location string

@description('Name for the AI Foundry account (AI Services)')
param foundryAccountName string

@description('Name for the Foundry project')
param projectName string

@description('Model to deploy')
param modelName string = 'gpt-4.1'

@description('Model version')
param modelVersion string = '2025-04-14'

@description('Model deployment capacity (thousands of tokens per minute)')
param modelCapacity int = 80

@description('Principal ID of the deployer for RBAC assignments')
param deployerPrincipalId string

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
// AI Services Account (Foundry)
// ============================================================================

resource foundry 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' = {
  name: foundryAccountName
  location: location
  sku: {
    name: 'S0'
  }
  kind: 'AIServices'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    allowProjectManagement: true
    customSubDomainName: foundryAccountName
    networkAcls: {
      defaultAction: 'Allow'
      virtualNetworkRules: []
      ipRules: []
    }
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: false
  }

  // Foundry Project
  resource project 'projects' = {
    name: projectName
    location: location
    identity: {
      type: 'SystemAssigned'
    }
    properties: {
      description: 'Foundry Workshop hands-on lab project'
      displayName: projectName
    }
  }
}

// ============================================================================
// Model Deployment
// ============================================================================

resource modelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview' = {
  parent: foundry
  name: modelName
  sku: {
    name: 'GlobalStandard'
    capacity: modelCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: modelName
      version: modelVersion
    }
  }
}

// ============================================================================
// RBAC: Azure AI User — allows deployer to create agents, query models
// ============================================================================

resource azureAiUserRole 'Microsoft.Authorization/roleDefinitions@2022-04-01' existing = {
  name: '53ca6127-db72-4b80-b1b0-d745d6d5456d'
}

resource assignAiUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: foundry
  name: guid(foundry.id, deployerPrincipalId, azureAiUserRole.id)
  properties: {
    roleDefinitionId: azureAiUserRole.id
    principalId: deployerPrincipalId
    principalType: 'User'
    description: 'Allow workshop participant to use Foundry AI services'
  }
}

// ============================================================================
// RBAC: Storage Blob Data Contributor — needed for file_search uploads
// ============================================================================

resource storageBlobContributorRole 'Microsoft.Authorization/roleDefinitions@2022-04-01' existing = {
  name: 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
}

resource assignStorageBlobContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: foundry
  name: guid(foundry.id, deployerPrincipalId, storageBlobContributorRole.id)
  properties: {
    roleDefinitionId: storageBlobContributorRole.id
    principalId: deployerPrincipalId
    principalType: 'User'
    description: 'Allow workshop participant to upload files for file_search'
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

output accountName string = foundry.name
output projectName string = foundry::project.name
output projectEndpoint string = 'https://${foundry.name}.services.ai.azure.com/api/projects/${foundry::project.name}'
output modelDeploymentName string = modelDeployment.name
output appInsightsConnectionString string = appInsights.properties.ConnectionString
output appInsightsName string = appInsights.name
output foundryResourceId string = foundry.id

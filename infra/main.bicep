// Voyager — Azure baseline infra (Eric / M0)
// Resource group is created by the deploy script, not here.

param location string = 'japaneast'
param projectName string = 'voyager'
param ownerEmail string
@secure()
param pgAdminPassword string

var suffix = uniqueString(resourceGroup().id)
var kvName = 'kv-${projectName}-${take(suffix, 6)}'
var pgName = 'psql-${projectName}-${take(suffix, 6)}'
var stName = 'st${projectName}${take(suffix, 8)}'
var sbName = 'sb-${projectName}-${take(suffix, 6)}'
var logName = 'log-${projectName}-${take(suffix, 6)}'
var caeName = 'cae-${projectName}-${take(suffix, 6)}'

// ---- Key Vault ----
resource kv 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: kvName
  location: location
  properties: {
    tenantId: subscription().tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    enablePurgeProtection: null
  }
}

// ---- Postgres Flexible Server (B1ms) ----
resource pg 'Microsoft.DBforPostgreSQL/flexibleServers@2023-12-01-preview' = {
  name: pgName
  location: location
  sku: { name: 'Standard_B1ms', tier: 'Burstable' }
  properties: {
    version: '16'
    administratorLogin: 'voyageradmin'
    administratorLoginPassword: pgAdminPassword
    storage: { storageSizeGB: 32 }
    backup: { backupRetentionDays: 7, geoRedundantBackup: 'Disabled' }
    highAvailability: { mode: 'Disabled' }
    network: { publicNetworkAccess: 'Enabled' }
  }
}

resource pgDb 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2023-12-01-preview' = {
  parent: pg
  name: 'voyager'
  properties: { charset: 'UTF8', collation: 'en_US.utf8' }
}

resource pgFwAzure 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2023-12-01-preview' = {
  parent: pg
  name: 'AllowAzureServices'
  properties: { startIpAddress: '0.0.0.0', endIpAddress: '0.0.0.0' }
}

// ---- Storage Account + Blob containers ----
resource st 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: stName
  location: location
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    accessTier: 'Hot'
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
  }
}

resource blobSvc 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: st
  name: 'default'
}

resource cVideosRaw 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobSvc
  name: 'videos-raw'
}
resource cAudio 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobSvc
  name: 'audio'
}
resource cTranscripts 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobSvc
  name: 'transcripts'
}
resource cVideosFinal 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobSvc
  name: 'videos-final'
}

// ---- Service Bus (Basic) ----
resource sb 'Microsoft.ServiceBus/namespaces@2022-10-01-preview' = {
  name: sbName
  location: location
  sku: { name: 'Basic', tier: 'Basic' }
}
resource qIngest 'Microsoft.ServiceBus/namespaces/queues@2022-10-01-preview' = {
  parent: sb
  name: 'ingest'
}
resource qTranscribe 'Microsoft.ServiceBus/namespaces/queues@2022-10-01-preview' = {
  parent: sb
  name: 'transcribe'
}

// ---- Log Analytics ----
resource log 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: logName
  location: location
  properties: { sku: { name: 'PerGB2018' }, retentionInDays: 30 }
}

// ---- Container Apps Environment ----
resource cae 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: caeName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: log.properties.customerId
        sharedKey: log.listKeys().primarySharedKey
      }
    }
  }
}

output keyVaultName string = kv.name
output postgresHost string = pg.properties.fullyQualifiedDomainName
output storageAccountName string = st.name
output serviceBusName string = sb.name
output containerAppsEnv string = cae.name

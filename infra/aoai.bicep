// Azure OpenAI in swedencentral (Whisper + gpt-4o + gpt-4o-mini available)
param location string = 'swedencentral'
param projectName string = 'voyager'

var suffix = uniqueString(resourceGroup().id)
var aoaiName = 'aoai-${projectName}-${take(suffix, 6)}'

resource aoai 'Microsoft.CognitiveServices/accounts@2024-04-01-preview' = {
  name: aoaiName
  location: location
  kind: 'OpenAI'
  sku: { name: 'S0' }
  properties: {
    customSubDomainName: aoaiName
    publicNetworkAccess: 'Enabled'
  }
}

resource whisperDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-04-01-preview' = {
  parent: aoai
  name: 'whisper'
  sku: { name: 'Standard', capacity: 3 }
  properties: {
    model: { format: 'OpenAI', name: 'whisper', version: '001' }
  }
}

resource gpt4oMiniDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-04-01-preview' = {
  parent: aoai
  name: 'gpt-4o-mini'
  sku: { name: 'GlobalStandard', capacity: 50 }
  properties: {
    model: { format: 'OpenAI', name: 'gpt-4o-mini', version: '2024-07-18' }
  }
  dependsOn: [ whisperDeployment ]
}

resource gpt4oDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-04-01-preview' = {
  parent: aoai
  name: 'gpt-4o'
  sku: { name: 'GlobalStandard', capacity: 30 }
  properties: {
    model: { format: 'OpenAI', name: 'gpt-4o', version: '2024-08-06' }
  }
  dependsOn: [ gpt4oMiniDeployment ]
}

output aoaiName string = aoai.name
output aoaiEndpoint string = aoai.properties.endpoint

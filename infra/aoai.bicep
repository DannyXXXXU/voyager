// Azure OpenAI in swedencentral — Whisper only.
// LLM (gpt-4o class) handled by GitHub Copilot Claude in-agent; no Azure LLM deployment.
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

output aoaiName string = aoai.name
output aoaiEndpoint string = aoai.properties.endpoint

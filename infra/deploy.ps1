# Voyager — one-shot Azure deploy script (PowerShell on Windows)
# Run from voyager repo root after `az login`.
# Total deploy time: ~10-15 min. Cost from this point: ~$45-60/month.

$ErrorActionPreference = "Stop"

# ============= CONFIG =============
$SUBSCRIPTION_ID = "2654ac92-a639-463c-b5a5-976b9fd563b5"
$RG              = "rg-voyager-prod"
$LOCATION        = "japaneast"
$AOAI_LOCATION   = "swedencentral"   # Whisper + gpt-4o not in japaneast
$OWNER_EMAIL     = "dingyi.xu11@gmail.com"
$BUDGET_AMOUNT   = 150
# ==================================

Write-Host "==> Setting subscription"
az account set --subscription $SUBSCRIPTION_ID

Write-Host "==> Registering required resource providers (idempotent)"
$providers = @(
  "Microsoft.KeyVault","Microsoft.DBforPostgreSQL","Microsoft.Storage",
  "Microsoft.ServiceBus","Microsoft.OperationalInsights","Microsoft.App",
  "Microsoft.CognitiveServices","Microsoft.Consumption","Microsoft.Insights"
)
foreach ($p in $providers) {
  az provider register --namespace $p --wait | Out-Null
  Write-Host "    $p ok"
}

Write-Host "==> Creating resource group $RG in $LOCATION"
az group create -n $RG -l $LOCATION | Out-Null

Write-Host "==> Generating Postgres admin password"
$pgPwd = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 24 | ForEach-Object {[char]$_})
$pgPwd = $pgPwd + "Aa1!"   # ensure complexity rules

Write-Host "==> Deploying core baseline (main.bicep) — ~8 min"
$mainOut = az deployment group create `
  -g $RG `
  -f infra/main.bicep `
  -p location=$LOCATION ownerEmail=$OWNER_EMAIL pgAdminPassword=$pgPwd `
  --query properties.outputs -o json | ConvertFrom-Json

$KV_NAME      = $mainOut.keyVaultName.value
$PG_HOST      = $mainOut.postgresHost.value
$ST_NAME      = $mainOut.storageAccountName.value
$SB_NAME      = $mainOut.serviceBusName.value
$CAE_NAME     = $mainOut.containerAppsEnv.value

Write-Host "==> Deploying Azure OpenAI in $AOAI_LOCATION (whisper + gpt-4o + gpt-4o-mini) — ~4 min"
$aoaiOut = az deployment group create `
  -g $RG `
  -f infra/aoai.bicep `
  -p location=$AOAI_LOCATION `
  --query properties.outputs -o json | ConvertFrom-Json

$AOAI_NAME     = $aoaiOut.aoaiName.value
$AOAI_ENDPOINT = $aoaiOut.aoaiEndpoint.value

Write-Host "==> Granting your account Key Vault Secrets Officer role"
$me = az ad signed-in-user show --query id -o tsv
$kvId = az keyvault show -n $KV_NAME -g $RG --query id -o tsv
az role assignment create --assignee $me --role "Key Vault Secrets Officer" --scope $kvId | Out-Null

Write-Host "==> Storing secrets in Key Vault"
$pgConn = "postgresql://voyageradmin:$pgPwd@$PG_HOST:5432/voyager?sslmode=require"
$blobConn = az storage account show-connection-string -n $ST_NAME -g $RG --query connectionString -o tsv
$sbConn = az servicebus namespace authorization-rule keys list -g $RG --namespace-name $SB_NAME --name RootManageSharedAccessKey --query primaryConnectionString -o tsv
$aoaiKey = az cognitiveservices account keys list -g $RG -n $AOAI_NAME --query key1 -o tsv

az keyvault secret set --vault-name $KV_NAME --name pg-conn          --value $pgConn   | Out-Null
az keyvault secret set --vault-name $KV_NAME --name pg-admin-pwd     --value $pgPwd    | Out-Null
az keyvault secret set --vault-name $KV_NAME --name blob-conn        --value $blobConn | Out-Null
az keyvault secret set --vault-name $KV_NAME --name servicebus-conn  --value $sbConn   | Out-Null
az keyvault secret set --vault-name $KV_NAME --name azure-openai-key      --value $aoaiKey      | Out-Null
az keyvault secret set --vault-name $KV_NAME --name azure-openai-endpoint --value $AOAI_ENDPOINT | Out-Null

Write-Host "==> Setting up `$BUDGET_AMOUNT/month budget with alerts at 50/80/95% actual + 100% forecasted"
$startDate = (Get-Date -Day 1).ToString("yyyy-MM-dd")
$endDate = (Get-Date -Day 1).AddYears(1).ToString("yyyy-MM-dd")
$budgetJson = @"
{
  "properties": {
    "category": "Cost",
    "amount": $BUDGET_AMOUNT,
    "timeGrain": "Monthly",
    "timePeriod": { "startDate": "$startDate", "endDate": "$endDate" },
    "notifications": {
      "Actual_50":   { "enabled": true, "operator": "GreaterThan", "threshold": 50,  "contactEmails": ["$OWNER_EMAIL"], "thresholdType": "Actual"     },
      "Actual_80":   { "enabled": true, "operator": "GreaterThan", "threshold": 80,  "contactEmails": ["$OWNER_EMAIL"], "thresholdType": "Actual"     },
      "Actual_95":   { "enabled": true, "operator": "GreaterThan", "threshold": 95,  "contactEmails": ["$OWNER_EMAIL"], "thresholdType": "Actual"     },
      "Forecast_100":{ "enabled": true, "operator": "GreaterThan", "threshold": 100, "contactEmails": ["$OWNER_EMAIL"], "thresholdType": "Forecasted" }
    }
  }
}
"@
$budgetJson | Out-File -Encoding utf8 budget.json
az rest --method put `
  --uri "https://management.azure.com/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RG/providers/Microsoft.Consumption/budgets/voyager-monthly?api-version=2023-05-01" `
  --body "@budget.json" | Out-Null
Remove-Item budget.json

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  DEPLOY COMPLETE" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  Resource Group:    $RG"
Write-Host "  Key Vault:         $KV_NAME"
Write-Host "  Postgres host:     $PG_HOST"
Write-Host "  Storage account:   $ST_NAME"
Write-Host "  Service Bus:       $SB_NAME"
Write-Host "  Container Apps Env:$CAE_NAME"
Write-Host "  Azure OpenAI:      $AOAI_NAME ($AOAI_LOCATION)"
Write-Host "  AOAI endpoint:     $AOAI_ENDPOINT"
Write-Host "  Budget alerts ->   $OWNER_EMAIL @ 50/80/95/100% of `$$BUDGET_AMOUNT"
Write-Host "------------------------------------------------------------"
Write-Host "Send the Key Vault name back to the agent: $KV_NAME" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Green

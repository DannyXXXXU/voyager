# Voyager Infra

One-shot Azure baseline for the Voyager project. Cost: ~$45-60/month. Hard cap: $150.

## Prerequisites (Windows)

```powershell
# 1. Install Azure CLI if you haven't:
winget install -e --id Microsoft.AzureCLI

# 2. Install Bicep (az will prompt anyway; this avoids the prompt mid-deploy):
az bicep install

# 3. Sign in
az login
```

## Deploy

From the Voyager repo root in PowerShell:

```powershell
./infra/deploy.ps1
```

The script will:
1. Set the subscription (`2654ac92-a639-463c-b5a5-976b9fd563b5`)
2. Register required resource providers
3. Create resource group `rg-voyager-prod` in `japaneast`
4. Deploy `main.bicep` — Key Vault, Postgres Flex B1ms, Storage (4 blob containers), Service Bus Basic, Log Analytics, Container Apps Environment
5. Deploy `aoai.bicep` in `swedencentral` (Whisper + gpt-4o + gpt-4o-mini)
6. Grant your account "Key Vault Secrets Officer" role
7. Generate Postgres admin password and store all connection strings + keys as Key Vault secrets:
   - `pg-conn`
   - `pg-admin-pwd`
   - `blob-conn`
   - `servicebus-conn`
   - `azure-openai-key`
   - `azure-openai-endpoint`
8. Create the $150/month budget with alerts at 50/80/95% actual + 100% forecasted to **dingyi.xu11@gmail.com**

Total runtime: ~10–15 minutes.

## Add YouTube + Langfuse keys (manual)

After deploy, you still need to add three secrets manually:

```powershell
# 1. YouTube Data API v3 key — create at https://console.cloud.google.com → APIs & Services → Credentials
az keyvault secret set --vault-name <KV_NAME> --name youtube-api-key --value "<your-key>"

# 2. Langfuse Cloud — sign up at https://cloud.langfuse.com → create project "voyager-eric"
az keyvault secret set --vault-name <KV_NAME> --name langfuse-public-key --value "pk-lf-..."
az keyvault secret set --vault-name <KV_NAME> --name langfuse-secret-key --value "sk-lf-..."
az keyvault secret set --vault-name <KV_NAME> --name langfuse-host       --value "https://cloud.langfuse.com"
```

Replace `<KV_NAME>` with the Key Vault name printed at the end of `deploy.ps1`.

## Verify

```powershell
az consumption budget list -g rg-voyager-prod
az keyvault secret list --vault-name <KV_NAME> --query "[].name" -o tsv
az postgres flexible-server show -n <PG_NAME> -g rg-voyager-prod --query state
```

You should see budget present, 9 secrets listed, Postgres state = `Ready`.

## Send back to the agent

After a successful run, paste the **Key Vault name** (e.g. `kv-voyager-abc123`) back in the chat. The agent uses it to write the secrets-pull script for local dev.

## Tear down (if ever needed)

```powershell
az group delete -n rg-voyager-prod --yes --no-wait
```

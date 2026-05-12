# Azure Marketplace — Testing Guide

Two independent scenarios before submitting to Partner Center.

---

## Scenario 1 — Local Docker + tunnel (fastest)

Tests webhook logic and ADO Service Hook end-to-end. No Azure resources required.
Uses API key auth instead of managed identity.

### 1. Install tunnel tool

**Azure Dev Tunnels** (Microsoft, free):
```bash
brew install --cask devtunnel        # macOS
winget install Microsoft.devtunnel   # Windows

devtunnel user login                 # one-time
```

Alternative: `ngrok http 8080` (free, no login required).

### 2. Run the container locally

```bash
docker run -p 8080:8080 \
  -e AZURE_OPENAI_BASE_URL=https://{your-openai}.openai.azure.com/openai \
  -e AZURE_OPENAI_DEPLOYMENT=gpt-4o \
  -e AZURE_OPENAI_API_KEY={api-key} \
  -e WEBHOOK_USERNAME=test \
  -e WEBHOOK_PASSWORD=testpass \
  ghcr.io/kamilpieronczyk/ado-pr-agent:latest
```

### 3. Expose the port

```bash
devtunnel host -p 8080
# Returns: https://xxx-8080.euw.devtunnels.ms
```

### 4. Verify health

```bash
curl https://xxx-8080.euw.devtunnels.ms/health
# {"status": "ok"}
```

### 5. Configure ADO Service Hooks

The webhook handles two event types. Create **both** hooks in the same ADO project.

Go to: ADO → Project Settings → Service Hooks → `+` → **Web Hooks**

#### Hook 1 — Pull request commented (primary trigger)

This is the main hook. Fires when someone writes `/ai review`, `/ai security`, or `/ai fix`
in a PR comment. The webhook reads the comment text directly from the payload.

| Field | Value |
|-------|-------|
| Publisher | Azure DevOps |
| Event | **Pull request commented** |
| Repository | select your repo (or leave blank for all repos) |
| Target branch | leave blank (all branches) |
| Comment contains | leave blank (filter handled by the app) |
| URL | `https://xxx-8080.euw.devtunnels.ms/webhook/ado` |
| Basic Auth Username | `test` |
| Basic Auth Password | `testpass` |
| HTTP headers | leave blank |
| Resource details to send | **All** |
| Messages to send | **All** |
| Detailed messages to send | **All** |

#### Hook 2 — Pull request created (onboarding trigger)

Fires when a new PR is opened. The app scans all existing threads for `/ai` commands;
if none found, it posts a welcome comment with available commands and bootstraps
missing config files into the repository.

| Field | Value |
|-------|-------|
| Publisher | Azure DevOps |
| Event | **Pull request created** |
| Repository | same repo as Hook 1 |
| Target branch | leave blank |
| URL | `https://xxx-8080.euw.devtunnels.ms/webhook/ado` |
| Basic Auth Username | `test` |
| Basic Auth Password | `testpass` |
| Resource details to send | **All** |
| Messages to send | **All** |
| Detailed messages to send | **All** |

> **Note:** Pull request updated events are not needed — the app re-reads the full diff
> on every trigger, so it always works on the current state of the PR.

After saving each hook, click **Test** to verify that ADO can reach the endpoint
and receives HTTP 200.

### 6. End-to-end test

Open a PR in your ADO project:

1. New PR is created → Hook 2 fires → app posts an onboarding comment listing available commands
2. Add a comment `/ai review` → Hook 1 fires → app posts code review findings
3. Add a comment `/ai security` → Hook 1 fires → app posts security findings
4. Add a comment `/ai fix` → Hook 1 fires → app creates a fix branch (if mechanical fixes found)

---

## Scenario 2 — Direct ARM deployment (no Marketplace)

Tests the full ARM template and all Azure resources: Key Vault secret refs,
managed identity auth to OpenAI, Container Apps deployment. Identical to what
Marketplace deploys — without the Partner Center wrapper.

### 1. Create a resource group

```bash
az group create --name ado-ai-test --location westeurope
```

### 2. Deploy the template

```bash
az deployment group create \
  --resource-group ado-ai-test \
  --template-file infra/mainTemplate.json \
  --parameters \
      appName=adoaitest \
      openAiDeploymentName=gpt-4o \
      webhookUsername=test \
      webhookPassword=testpassword123 \
  --verbose
```

Deployment takes ~10-15 minutes. The output includes `webhookUrl`, `healthUrl`, `managedIdentityClientId`, and `managedIdentityPrincipalId`.

> **Post-deployment:** Add the managed identity to your Azure DevOps organization as a user with Basic access and grant it Code Read and Pull Request Threads (Read & Write) permissions. Retrieve the principal ID from the deployment outputs:
> ```bash
> az deployment group show -g ado-ai-test -n <deployment-name> --query properties.outputs.managedIdentityPrincipalId.value
> ```

### 3. Verify health

```bash
curl https://{fqdn}.westeurope.azurecontainerapps.io/health
# {"status": "ok"}
```

### 4. Configure ADO Service Hooks

Same hooks as Scenario 1, step 5 — use the `webhookUrl` from the deployment output
as the URL in both hooks.

### 5. Clean up

```bash
az group delete --name ado-ai-test --yes --no-wait
```

---

## What each scenario covers

| | Scenario 1 (tunnel) | Scenario 2 (ARM deploy) |
|---|---|---|
| Webhook logic (application code) | Yes | Yes |
| ADO Service Hook end-to-end | Yes | Yes |
| ARM template / Azure resources | No | Yes |
| Key Vault secret refs | No | Yes |
| Managed identity auth to OpenAI | No (uses API key) | Yes |
| Cost | Free | Azure costs (~few PLN/hour) |
| Setup time | ~2 min | ~15 min |

**Recommended order:** Run Scenario 1 first to validate application logic quickly,
then Scenario 2 to confirm the ARM template is correct before submitting to Partner Center.

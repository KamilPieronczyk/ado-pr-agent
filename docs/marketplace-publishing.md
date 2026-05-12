# Azure Marketplace — Publishing Guide

This document covers how to package and publish ADO AI PR Review as a free
**Azure Managed Application** offer in the Azure Marketplace.

For background on the offer type and architecture decisions see
[`docs/research-azure-marketplace-managed-app.md`](research-azure-marketplace-managed-app.md).

---

## Prerequisites

- Microsoft AI Cloud Partner Program account (free) at [partner.microsoft.com](https://partner.microsoft.com)
- Partner Center account enrolled in the commercial marketplace
- `zip` installed locally (`brew install zip` on macOS)
- An Azure subscription for preview testing

---

## Repository structure

```
infra/
  mainTemplate.json       ARM template — resources deployed in the customer's subscription
  createUiDefinition.json Portal wizard shown to the customer at purchase time
  package.sh              Script that produces app.zip for Partner Center upload
app.zip                   Generated artifact — not committed to git
```

---

## Step 1 — Build the package

```bash
chmod +x infra/package.sh   # first time only
./infra/package.sh
```

This creates `app.zip` in the repository root containing both required files at the
root level of the archive (Partner Center rejects packages where files are in a subfolder).

Expected output:
```
Created: /path/to/ado-ai-pr-review/app.zip
Contents:
Archive:  app.zip
  Length      Date    Time    Name
---------  ---------- -----   ----
    10xxx  2026-05-10 12:00   mainTemplate.json
     4xxx  2026-05-10 12:00   createUiDefinition.json
```

---

## Step 2 — Test the UI wizard

Before uploading to Partner Center, validate `createUiDefinition.json` in the Azure portal sandbox:

1. Open [CreateUiDefinition Sandbox](https://portal.azure.com/#blade/Microsoft_Azure_CreateUIDef/SandboxBlade)
2. Paste the contents of `infra/createUiDefinition.json` into the editor
3. Click **Preview**
4. Step through all 4 tabs and verify validation messages

The wizard has 4 steps:

| Step | Fields |
|------|--------|
| Application | App name (3-12 chars), image tag |
| Azure OpenAI | Model deployment name (e.g. `gpt-4o`) |
| Azure DevOps | ADO Personal Access Token |
| Webhook Security | Basic Auth username and password |

---

## Step 3 — Create the offer in Partner Center

1. Go to [Partner Center → Marketplace offers](https://partner.microsoft.com/dashboard/marketplace-offers/overview)
2. **+ New offer → Azure Application**
3. Set **Offer ID**: `ado-ai-pr-review` (lowercase, hyphens only, max 50 chars, permanent)
4. Set **Offer alias** (internal name, can be changed later)

### Offer listing (Offer listing tab)

| Field | Value |
|-------|-------|
| Name | ADO AI PR Review |
| Search results summary | AI-powered pull request reviewer for Azure DevOps (max 100 chars) |
| Short description | Webhook-based AI reviewer that reacts to `/ai` commands in pull request comments using your own Azure OpenAI instance. (max 256 chars) |
| Description | Full HTML description, max 5 000 chars |
| Category | AI Apps and Agents → Tools & Connectors |
| Logo (Large) | PNG, 216×216 to 350×350 px (required) |

### Contacts

Fill in **Support contact** (name, email, phone, URL) and **Engineering contact** (name, email, phone).
These are required before submission.

---

## Step 4 — Create a plan

1. Plans tab → **+ Create new plan**
2. Plan ID: `free` (permanent)
3. Plan name: `Free`
4. Plan type: **Managed Application**

### Pricing and availability

- Per-month price: **$0.00** (free tier — customers pay only Azure infrastructure costs)
- Markets: select all or a subset

### Technical configuration

| Field | Value |
|-------|-------|
| Version | `1.0.0` (increment on every republish: `1.0.1`, `1.0.2`, …) |
| Package file | Upload `app.zip` |
| Deployment mode | **Incremental** |

### Publisher management access

Enable **Publisher Management Access** and add at least one authorization:

| Field | Value |
|-------|-------|
| Microsoft Entra Tenant ID | Your publisher tenant directory ID |
| Principal ID | Object ID of your user, group, or service principal |
| Role definition | **Contributor** (`b24988ac-6180-42a0-ab88-20f7382dd24c`) |

Use a security group's object ID rather than an individual user so group membership
can be updated without republishing the offer.

### Customer access

Leave as **Full access** for the initial release (no deny assignment).

---

## Step 5 — Preview deployment

1. Preview tab → add your Azure subscription ID as the preview audience
2. Submit the offer for review → status changes to **Publisher signoff**
3. Deploy the offer from the preview Marketplace link to your own subscription
4. Verify:
   - All 6 Azure resources are created correctly
   - The Container App health endpoint returns `{"status": "ok"}` at the `healthUrl` output
   - ADO service hook can reach the `webhookUrl` output with the configured Basic Auth credentials

---

## Step 6 — Publish

Once preview testing passes, click **Go live** in Partner Center.
Microsoft certification takes approximately 3–5 business days and checks:

- ARM template correctness
- `createUiDefinition.json` validity
- Security policies

---

## What gets deployed in the customer's subscription

When a customer purchases and deploys the offer, the following resources are created in
their subscription inside a managed resource group:

| Resource | Name pattern | Purpose |
|----------|-------------|---------|
| User-assigned managed identity | `{appName}-identity` | Keyless auth from container to OpenAI and Key Vault |
| Azure OpenAI (S0) | `{appName}-openai` | Customer's own OpenAI instance |
| Key Vault | `{appName}-kv` | Stores ADO PAT and webhook password |
| Container Apps environment | `{appName}-env` | Runtime environment |
| Container App | `{appName}` | Webhook server on port 8080 |
| Role assignment × 2 | — | Identity → Key Vault Secrets User; Identity → Cognitive Services OpenAI User |

The customer pays for all Azure resource costs directly. The offer software fee is $0.

---

## Republishing after a code change

1. Build and push a new Docker image tag (handled by `.github/workflows/publish.yml` on semver tags)
2. Update `infra/mainTemplate.json` if the ARM template changed
3. Run `./infra/package.sh` to regenerate `app.zip`
4. In Partner Center → plan → Technical configuration → increment the version number → upload new `app.zip`
5. Submit for review

---

## Troubleshooting

**Portal wizard does not display after Preview in sandbox**
Open browser developer tools → Console for JSON syntax errors. Red scroll-bar indicators mark
the problem line.

**Certification fails with "languageVersion not supported"**
`mainTemplate.json` must not contain `"languageVersion": "2.0"`. The current template uses
the standard `$schema` header only (languageVersion 1.0 by default).

**Container App cannot read Key Vault secrets**
The role assignment resource (`Microsoft.Authorization/roleAssignments`) must complete before
the Key Vault secret resources. The `dependsOn` chain in `mainTemplate.json` enforces this order.

**DefaultAzureCredential cannot find identity**
`AZURE_CLIENT_ID` is set in the Container App to the managed identity's `clientId`.
If authentication fails, verify the `Cognitive Services OpenAI User` role assignment was applied
to the OpenAI account (not the resource group).

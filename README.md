# ADO AI PR Review

Azure DevOps AI pull request reviewer. Runs in two modes:

- **Webhook** — FastAPI server in Azure Container Apps, receives ADO service hooks, authenticates to ADO using managed identity (`ADO_AUTH_MODE=entra`, default) or PAT fallback (`ADO_AUTH_MODE=pat`)
- **Local** — CLI against the current git branch, output to stdout (no ADO credentials needed)

Reacts to `/ai` commands in PR comments and posts code review findings, security findings,
and mechanical fix suggestions.

## Available Commands

Comment one of these in any PR discussion thread:

| Command | Description |
|---------|-------------|
| `/ai review` | General code review: correctness, test gaps, readability, maintainability. |
| `/ai security` | Security baseline: secrets, injection, auth, authorization, input validation. |
| `/ai fix` | Mechanical fixes only: formatting, lint, imports, safe renames. |

On the first run (no command yet), the worker posts an onboarding comment listing the commands
and bootstraps missing configuration files into the repository.

## Azure DevOps Identity Onboarding

Before the webhook can post PR comments and read repositories, the managed identity (or
service principal) must be added to the Azure DevOps organization. Azure RBAC permissions
do **not** grant Azure DevOps permissions — they must be configured separately in ADO.

1. **Get the managed identity's principal ID** from deployment outputs:

   ```bash
   az deployment group show -g <resource-group> -n <deployment-name> \
     --query properties.outputs.managedIdentityPrincipalId.value
   ```

2. **Add the identity to ADO:** Organization Settings → Users → Add user → paste the
   principal ID, assign **Basic** access level.

3. **Grant project permissions:** Add the identity to the target project with at minimum:
   - Code (Read)
   - Pull Request Threads (Read & Write)

4. **For `/ai fix` to create fix branches:** additionally grant Contribute on the target
   branch.

## Webhook / Container Apps

The `serve` subcommand starts a FastAPI server that receives Azure DevOps service hooks and
runs reviews automatically.

### Setup

1. Deploy the Docker image to Azure Container Apps with the environment variables below.
2. In your ADO project, go to **Project Settings → Service hooks → Create subscription**.
3. Select **Web Hooks** and configure it to trigger on:
   - *Pull request created*
   - *Pull request updated*
   - *Pull request commented on*
4. Set the webhook URL to `https://<your-container-app>/webhook/ado`.
5. Set Basic Auth credentials in the service hook subscription to match `WEBHOOK_USERNAME`
   and `WEBHOOK_PASSWORD` (see table below).

### Additional Environment Variables (webhook mode only)

| Variable | Required | Description |
|----------|----------|-------------|
| `ADO_AUTH_MODE` | No | Authentication mode for ADO REST API. `entra` (default) uses managed identity/DefaultAzureCredential. `pat` requires `ADO_PAT`. |
| `ADO_PAT` | Only when `ADO_AUTH_MODE=pat` | Personal access token for ADO REST API. For local testing only. |
| `WEBHOOK_USERNAME` | No | Basic Auth username for the webhook endpoint. Required if `WEBHOOK_PASSWORD` is set. |
| `WEBHOOK_PASSWORD` | No | Basic Auth password for the webhook endpoint. |

The `AZURE_OPENAI_*` variables listed under [Environment Variables](#environment-variables) are also required in webhook mode.

### Running locally

For local testing of the webhook server, use PAT-based auth:

```bash
export ADO_AUTH_MODE=pat
export ADO_PAT=<your-personal-access-token>
export AZURE_OPENAI_BASE_URL=https://...openai.azure.com/openai/v1/
export AZURE_OPENAI_DEPLOYMENT=gpt-4o
ado-ai-pr-review serve --host 0.0.0.0 --port 8080
```

The server exposes:
- `POST /webhook/ado` — ADO service hook receiver (returns 200 immediately, processes async)
  The response body includes a `request_id` field. Callers may pass `X-Request-ID` or `X-Correlation-ID` to set a custom request ID; otherwise one is generated automatically.
- `GET /health` — liveness/readiness probe for Container Apps

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `AZURE_OPENAI_BASE_URL` | Yes | Azure OpenAI or AI Foundry base URL. Must end in `/openai/v1/`. Example: `https://myinstance.openai.azure.com/openai/v1/` |
| `AZURE_OPENAI_DEPLOYMENT` | Yes | Model deployment name. Example: `gpt-4o` |
| `AZURE_OPENAI_API_KEY` | No | API key. Omit to use Microsoft Entra / managed identity authentication instead. |

## Configuration

On first run, the worker creates `.ado-ai-review.yml` and the instruction/guideline files
in the repository. Edit them to customise review behaviour.

### `.ado-ai-review.yml` Reference

```yaml
version: 1

commands:
  review:
    enabled: true     # enable /ai review
  security:
    enabled: true     # enable /ai security
  fix:
    enabled: true     # enable /ai fix

instructions:
  reviewer: .ado-ai-review/instructions/reviewer.md   # agent instructions for code review
  security: .ado-ai-review/instructions/security.md   # agent instructions for security review
  indexer:  .ado-ai-review/instructions/indexer.md    # agent instructions for repo indexing
  fixer:    .ado-ai-review/instructions/fixer.md      # agent instructions for mechanical fixes

guidelines:
  code_style:
    - .ado-ai-review/guidelines/code-style.md   # always loaded for every review
    - AGENTS.md                                  # optional: existing files picked up if present
    - CLAUDE.md
    - .github/copilot-instructions.md
  security:
    - .ado-ai-review/guidelines/security.md

review:
  focus:
    - bug-risk          # logic errors, incorrect behaviour
    - test-gaps         # missing or inadequate tests
    - readability       # confusing names, unclear control flow
    - maintainability   # coupling, duplication
  max_findings: 20
  severity_threshold: medium   # suppress findings below this level (low | medium | high | critical)

security:
  enabled: true
  rules:
    - secrets
    - injection
    - authz
    - authn
    - input-validation
    - unsafe-deserialization

fix:
  enabled: true
  mode: mechanical-only
  inline_suggestions:
    enabled: true
    max_lines: 20   # inline suggestions longer than this go to a fix branch instead
  branch:
    enabled: true
    name_template: ai-fix/pr-{pr_id}/{run_id}
    one_commit_per_change: true

context:
  index:
    enabled: true
    exclude:
      - node_modules/**
      - bin/**
      - obj/**
      - dist/**
      - build/**
      - .git/**
  dynamic_context:
    enabled: true
    max_files: 20   # max repository files loaded as context per review

observability:
  langfuse:
    enabled: true
    trace_pr_reviews: true
    capture_token_usage: true
    capture_costs: true
    capture_prompts: false        # set true only for debugging; prompts may contain code
    capture_code_context: false   # set true only for debugging; context may contain sensitive data
```

### Instruction Files

The files under `.ado-ai-review/instructions/` guide each agent module:

| File | Purpose |
|------|---------|
| `reviewer.md` | Focus areas, severity guidance, and output style for code review. |
| `security.md` | Security checklist, severity mapping, and constraints for security review. |
| `indexer.md` | How to tag and describe repository files for context selection. |
| `fixer.md` | Mechanical fix whitelist and delivery format rules. |

### Guideline Files

The files under `.ado-ai-review/guidelines/` are always-on context loaded for every review:

| File | Purpose |
|------|---------|
| `code-style.md` | Project-specific code style and naming conventions. |
| `security.md` | Team-specific security requirements and sensitive data policies. |

Existing files like `AGENTS.md`, `CLAUDE.md`, and `.github/copilot-instructions.md` are
loaded automatically if they exist and are listed under `guidelines.code_style`.

## Local Mode

Run a review against the current git branch without any ADO credentials. The diff is
computed against a remote branch (`origin/main` by default) and results are printed to
stdout.

```bash
# Using Azure OpenAI (requires AZURE_OPENAI_* env vars)
export AZURE_OPENAI_BASE_URL=https://...openai.azure.com/openai/v1/
export AZURE_OPENAI_DEPLOYMENT=gpt-4o
ado-ai-pr-review local --command review

# Using GitHub Copilot (requires an active Copilot subscription + gh CLI login)
gh auth login
ado-ai-pr-review local --command review --llm copilot

# Review against a different base branch
ado-ai-pr-review local --command security --target-branch develop
```

Available `--command` values: `review`, `security`, `fix`.

No ADO environment variables are needed in local mode. Bootstrap files are created in the
current repository if they are missing.

### Azure OpenAI Authentication in Local Mode

Three authentication options are supported when `AZURE_OPENAI_API_KEY` is not set:

**Interactive (az login) — for developer workstations:**

```bash
az login
export AZURE_OPENAI_BASE_URL=https://acme-openai.openai.azure.com/openai/v1/
export AZURE_OPENAI_DEPLOYMENT=gpt-4o
unset AZURE_OPENAI_API_KEY
ado-ai-pr-review local --command review --target-branch main
```

**Service principal — for non-interactive / CI use:**

```bash
export AZURE_TENANT_ID=<tenant-id>
export AZURE_CLIENT_ID=<client-id>
export AZURE_CLIENT_SECRET=<client-secret>
export AZURE_OPENAI_BASE_URL=https://acme-openai.openai.azure.com/openai/v1/
export AZURE_OPENAI_DEPLOYMENT=gpt-4o
ado-ai-pr-review local --command review --target-branch main
```

Both paths use `DefaultAzureCredential` from the Azure Identity SDK, which picks up `az login`
sessions, service principal environment variables, managed identity, and other credential
sources automatically (in that order).

**API key — for users with a direct OpenAI API key:**

```bash
export AZURE_OPENAI_API_KEY=<api-key>
export AZURE_OPENAI_BASE_URL=https://acme-openai.openai.azure.com/openai/v1/
export AZURE_OPENAI_DEPLOYMENT=gpt-4o
ado-ai-pr-review local --command review --target-branch main
```

When `AZURE_OPENAI_API_KEY` is set it takes priority and `DefaultAzureCredential` is not used.

## Security Boundary

The model never receives a raw shell tool. Every write action (git push, PR comment) is
performed by Python code that validates model output first. Secret values detected locally
are redacted before any model call.

Fix commits are never written directly to the PR source branch. They go to a separate
`ai-fix/...` branch and a fix PR.

Repository file reads, context indexing, command cwd values, and mechanical fix writes are constrained to the request workspace. The worker rejects parent traversal, absolute paths outside the workspace, and symlink targets that could escape into another cloned repository. Runtime logs are emitted as JSON and include `request_id`; configured secrets and known token formats are redacted before output.

## Local Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check src tests
mypy src
```

# ADO AI PR Review

Azure DevOps AI pull request reviewer. Runs in three modes:

- **Pipeline** — Docker container in Azure DevOps Pipelines (current production mode)
- **Local** — CLI against the current git branch, output to stdout (no ADO credentials needed)
- **Webhook** — persistent FastAPI server in Azure Container Apps, receives ADO service hooks

Reacts to `/ai` commands in PR comments and posts code review findings, security findings,
and mechanical fix suggestions.

## Quick Start

1. Create a GitHub service connection in your ADO project (Project Settings → Service connections → GitHub).
2. Add a pipeline file to your repository (see [Pipeline Setup](#pipeline-setup)).
3. Create a branch policy that triggers the pipeline on every PR.
4. Set the required pipeline variables (see [Environment Variables](#environment-variables)).
5. Open a PR and comment `/ai review`.

> **Note:** The Docker image is published to the GitHub Container Registry (GHCR) as a public
> package. If the package shows as private, set it to public at
> GitHub → your profile → Packages → `ado-pr-agent` → Package settings → Change visibility.

## Available Commands

Comment one of these in any PR discussion thread:

| Command | Description |
|---------|-------------|
| `/ai review` | General code review: correctness, test gaps, readability, maintainability. |
| `/ai security` | Security baseline: secrets, injection, auth, authorization, input validation. |
| `/ai fix` | Mechanical fixes only: formatting, lint, imports, safe renames. |

On the first run (no command yet), the worker posts an onboarding comment listing the commands
and bootstraps missing configuration files into the repository.

## Pipeline Setup

### Option A — Extends template (recommended)

Add a small pipeline file to your repository that references this repo directly.
No files to copy or maintain — updates are pulled by changing the tag pin.

```yaml
# azure-pipelines.ado-ai-review.yml  (in your repository)
trigger: none

pr:
  branches:
    include: ["*"]

resources:
  repositories:
    - repository: ado-ai-pr-review
      type: github
      name: KamilPieronczyk/ado-pr-agent
      ref: refs/tags/v1.0.1          # pin to a release tag — check releases for latest
      endpoint: MyGitHubServiceConnection

extends:
  template: templates/pipeline.yml@ado-ai-pr-review
  parameters:
    imageVersion: v1.0.1             # must match the tag above
```

**Requirements:**
- A GitHub service connection named `MyGitHubServiceConnection` (or any name — update `endpoint:` accordingly).
- "Grant access to all pipelines" checked on the service connection.

The `checkout`, `persistCredentials`, `fetchDepth`, and `SYSTEM_ACCESSTOKEN` mapping are
already included in `templates/pipeline.yml` — no extra step configuration needed.

### Option B — Standalone copy

Copy `azure-pipelines.ado-ai-review.yml` from this repository into your target repo.
Useful when you cannot create a GitHub service connection or need full local control.

The standalone pipeline pulls a pre-built image from GHCR. Override the `imageVersion`
pipeline variable to pin to a specific release (default: `latest`).

Create an Azure DevOps branch policy that triggers this pipeline on PR creation and update.

### Required ADO Permissions

Grant these permissions to the **project build service** identity:

| Permission | Reason |
|-----------|--------|
| Code read | Read repository files and PR diff. |
| Pull Request contribute | Post PR comments and threads. |
| Contribute (branch) | Create bootstrap commits and fix branches. Required only for `/ai fix` and bootstrap. |

> **Option B only:** the pipeline YAML must map `SYSTEM_ACCESSTOKEN` and the OpenAI
> variables explicitly in the `env:` block of the `docker run` step. Option A handles
> this inside `templates/pipeline.yml`.

## Environment Variables

### Set in Pipeline Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `AZURE_OPENAI_BASE_URL` | Yes | Azure OpenAI or AI Foundry base URL. Must end in `/openai/v1/`. Example: `https://myinstance.openai.azure.com/openai/v1/` |
| `AZURE_OPENAI_DEPLOYMENT` | Yes | Model deployment name. Example: `gpt-4o` |
| `AZURE_OPENAI_API_KEY` | No | API key. Omit to use Microsoft Entra / managed identity authentication instead. |

### Injected Automatically by Azure DevOps Pipelines

These are standard ADO variables. The pipeline YAML maps them to the container via `-e`:

| Variable | Required | Description |
|----------|----------|-------------|
| `SYSTEM_ACCESSTOKEN` | Yes | ADO access token. Must be explicitly passed via `env:` in the step. |
| `SYSTEM_TEAMFOUNDATIONCOLLECTIONURI` | Yes | ADO organization URL. Example: `https://dev.azure.com/myorg/` |
| `SYSTEM_TEAMPROJECT` | Yes | ADO project name. |
| `BUILD_REPOSITORY_ID` | Yes | Repository GUID. |
| `SYSTEM_PULLREQUEST_PULLREQUESTID` | Yes | PR ID integer. Only set when the pipeline runs as a branch policy. |
| `BUILD_REPOSITORY_NAME` | No | Repository name. Defaults to empty string. |
| `SYSTEM_PULLREQUEST_SOURCEBRANCH` | No | Source branch ref. Example: `refs/heads/feature/my-branch` |
| `SYSTEM_PULLREQUEST_TARGETBRANCH` | No | Target branch ref. Example: `refs/heads/main` |
| `SYSTEM_PULLREQUEST_ISFORK` | No | `True` when the PR comes from a fork. Fix branches and bootstrap commits are disabled for forks. |
| `BUILD_BUILDID` | No | Build ID used in fix branch names. Defaults to `local`. |

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

## Webhook / Container Apps

The `serve` subcommand starts a FastAPI server that receives Azure DevOps service hooks and
runs reviews automatically, without a pipeline job.

### Setup

1. Deploy the Docker image to Azure Container Apps with the environment variables below.
2. In your ADO project, go to **Project Settings → Service hooks → Create subscription**.
3. Select **Web Hooks** and configure it to trigger on:
   - *Pull request created*
   - *Pull request updated*
   - *Pull request commented on*
4. Set the webhook URL to `https://<your-container-app>/webhook/ado`.
5. Set the HTTP header `ADO_AUTH_TOKEN` via the service hook basic auth or a custom header
   (see `docs/follow-ups/webhook-auth.md` for authentication options and current limitations).

### Additional Environment Variable (webhook mode only)

| Variable | Required | Description |
|----------|----------|-------------|
| `ADO_AUTH_TOKEN` | Yes | Personal access token or managed identity token for ADO REST API calls from the webhook server. |

The `AZURE_OPENAI_*` variables listed above are also required in webhook mode.

### Running locally

```bash
export ADO_AUTH_TOKEN=...
export AZURE_OPENAI_BASE_URL=https://...openai.azure.com/openai/v1/
export AZURE_OPENAI_DEPLOYMENT=gpt-4o
ado-ai-pr-review serve --host 0.0.0.0 --port 8080
```

The server exposes:
- `POST /webhook/ado` — ADO service hook receiver (returns 200 immediately, processes async)
  The response body includes a `request_id` field. Callers may pass `X-Request-ID` or `X-Correlation-ID` to set a custom request ID; otherwise one is generated automatically.
- `GET /health` — liveness/readiness probe for Container Apps

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

To run the pipeline adapter locally against a real PR (read-only, no writes):

```bash
export SYSTEM_ACCESSTOKEN=...
export SYSTEM_TEAMFOUNDATIONCOLLECTIONURI=https://dev.azure.com/myorg/
export SYSTEM_TEAMPROJECT=myproject
export BUILD_REPOSITORY_ID=...
export SYSTEM_PULLREQUEST_PULLREQUESTID=123
export AZURE_OPENAI_BASE_URL=https://...openai.azure.com/openai/v1/
export AZURE_OPENAI_DEPLOYMENT=gpt-4o
ado-ai-pr-review pipeline --repo-root . --dry-run
```

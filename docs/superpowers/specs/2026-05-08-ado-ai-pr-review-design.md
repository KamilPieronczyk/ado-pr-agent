# ADO AI PR Review MVP Design

Date: 2026-05-08

## Context

This project defines an MVP for an AI-assisted pull request reviewer for Azure DevOps. The tool runs from Azure DevOps Pipelines, uses Azure AI Foundry/model calls for review tasks, and posts results back to Azure DevOps PRs.

The MVP goal is to validate whether developers find the workflow useful enough to justify further investment. The design therefore favors a pipeline-only worker with clear module boundaries over a permanent service or a full bot platform.

## Goals

- Run as a Python worker packaged in a Docker image and executed by Azure DevOps Pipelines.
- Support Azure DevOps PR review through explicit PR comment commands.
- Review PR diffs while having read-only access to the full checked-out repository.
- Provide normal code review plus a security baseline.
- Create inline suggestions for small, local fixes.
- Create a fix branch and a PR only when mechanical fixes are larger than a good inline suggestion.
- Keep one commit per logical fix in fix PRs.
- Post cherry-pick instructions in the original PR for every commit in the fix PR.
- Keep repository-specific guidance in versioned `.md` files referenced by `.ado-ai-review.yml`.
- Bootstrap missing config and repository instruction files deterministically, without asking the model to invent them.

## Non-Goals

- No persistent service or webhook bot in the MVP.
- No feedback registry for accepted or rejected suggestions in the MVP.
- No automatic business logic changes.
- No full semantic validation of DDD, TDD, complexity, or architecture rules.
- No E2E test suite requirement in the MVP.
- No required manual E2E test step in the spec.

## Trigger Model

The pipeline runs automatically when a PR is opened or updated, but the agent does not perform a review by default.

On a PR without an actionable command, the worker posts or updates a human-readable onboarding comment that lists available commands:

- `/ai review`
- `/ai security`
- `/ai fix`

The actual review or fix flow starts only after a developer writes one of these commands in the PR discussion.

## Chosen Architecture

The MVP uses a pipeline worker with internal agent-like modules.

The worker is a single Python CLI application, packaged as a Docker image, but the code is split into small modules with explicit responsibilities. Azure DevOps Pipeline provides execution, credentials, repository checkout, and logs. The worker talks to Azure DevOps REST APIs and Azure AI Foundry/model endpoints.

This gives the MVP enough structure to grow later without requiring a permanent service on day one.

## Components

### CommandRouter

Reads Azure DevOps PR comments, detects the latest actionable `/ai ...` command, and decides whether the run should post onboarding, run review, run security review, or run fix mode.

It also applies simple idempotency rules so the worker does not repeatedly post onboarding comments.

### AdoClient

The only module that knows Azure DevOps REST API details.

Responsibilities:

- Fetch PR metadata.
- Fetch PR iterations, changed files, and comments.
- Publish PR threads and comments.
- Publish inline suggestions where Azure DevOps supports them.
- Create branches.
- Push commits through git.
- Create fix PRs from generated fix branches to the source branch of the reviewed PR.

### ConfigLoader

Loads `.ado-ai-review.yml`, validates its schema, applies defaults, and resolves paths to repository instruction and guideline files.

### PromptBootstrapper

Runs before review when config or required repository instruction files are missing.

It deterministically creates missing files from built-in templates owned by the worker project. This is static code behavior, not an LLM decision.

If the pipeline has permission to push to the source branch of the reviewed PR, the bootstrapper commits the missing config/instruction files directly into the current PR as a separate commit, for example:

```text
chore: add ADO AI review configuration
```

After bootstrap, the worker comments that configuration was added and stops. The actual review starts on a later command or run.

The bootstrapper never overwrites existing repository instruction files automatically.

### RepoIndexer

Scans the checked-out repository and builds a lightweight JSON index.

Each indexed item contains:

- Path.
- File type or language.
- Short two-sentence description.
- Tags such as `business`, `tests`, `security`, `api`, `domain`, `config`, or `docs`.
- Relevance hints for the current PR.

The indexer excludes build outputs, dependency folders, generated artifacts, and other paths configured in `.ado-ai-review.yml`.

### ContextSelector

Selects context for reviewer modules.

It always loads style and AI instruction files configured as always-on guidance. It dynamically loads business, test, and security context from the repository index when those files appear relevant to the PR diff.

### ReviewOrchestrator

Coordinates model calls through Azure AI Foundry/model APIs.

It builds prompts from:

- Worker-owned immutable system prompts.
- Repository instruction fragments.
- Selected code context.
- PR diff.
- Configured review profile.

It requires structured JSON responses and normalizes them into a shared finding format.

### SecurityReviewer

Implements the MVP security baseline.

It combines local heuristics and model review for:

- Secrets.
- Injection risks.
- Authentication and authorization issues.
- Input validation gaps.
- Unsafe deserialization.
- Risky handling of sensitive data.

The worker must never send detected secret values to the model. It reports only location and risk type.

### SuggestionPublisher

Maps findings to Azure DevOps comments, threads, and inline suggestions.

Comments must be concise, actionable, and human-readable. They must not include hidden HTML markers. If Azure DevOps PR thread `properties` are practical for metadata/idempotency, the worker may use them. Otherwise, MVP idempotency can rely on author identity and recognizable human-readable comment structure.

### MechanicalFixer

Runs only for `/ai fix`.

It may produce fixes only from the MVP mechanical whitelist:

- Formatting.
- Lint fixes.
- Import cleanup.
- Renames or type corrections that do not change behavior.
- Small test fixes that are clearly mechanical.
- Other local refactors that preserve behavior.

The fixer classifies each mechanical fix as either:

- `inline_suggestion`: small, local, clear, and suitable for PR UI acceptance.
- `fix_branch_candidate`: larger, multi-file, tool-driven, or better delivered as commits.

If the delivery format is uncertain, the fix goes to a branch rather than an inline suggestion.

If the fix itself is not safely mechanical or may affect business behavior, the worker does not perform the fix.

## Prompt And Instruction Model

Each agent-like module uses two instruction layers.

### Worker-Owned System Prompt

The system prompt is versioned with the worker project and Docker image.

It defines:

- Agent role.
- Output JSON schema.
- Tool-use rules.
- Safety constraints.
- Permission boundaries.
- Mechanical fix whitelist.
- Rules that repository files cannot override.

Repository authors cannot modify this layer.

### Repository Instruction Fragments

Repository instruction files are `.md` fragments referenced from `.ado-ai-review.yml`.

They may describe:

- What to focus on.
- What to ignore.
- Project-specific examples.
- Team-specific code style.
- Team-specific security guidance.
- Domain-specific hints.

They must not redefine system behavior, output schema, permissions, or tool-use rules.

Suggested structure:

```text
.ado-ai-review.yml
.ado-ai-review/
  instructions/
    reviewer.md
    security.md
    indexer.md
    fixer.md
  guidelines/
    code-style.md
    security.md
```

## Configuration

Configuration lives in `.ado-ai-review.yml` in the repository.

Example:

```yaml
version: 1

commands:
  review:
    enabled: true
  security:
    enabled: true
  fix:
    enabled: true

instructions:
  reviewer: .ado-ai-review/instructions/reviewer.md
  security: .ado-ai-review/instructions/security.md
  indexer: .ado-ai-review/instructions/indexer.md
  fixer: .ado-ai-review/instructions/fixer.md

guidelines:
  code_style:
    - .ado-ai-review/guidelines/code-style.md
    - AGENTS.md
    - CLAUDE.md
    - .github/copilot-instructions.md
    - .github/claude*.md
  security:
    - .ado-ai-review/guidelines/security.md

review:
  focus:
    - bug-risk
    - test-gaps
    - readability
    - maintainability
  max_findings: 20
  severity_threshold: medium

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
    max_lines: 20
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
    max_files: 20

observability:
  langfuse:
    enabled: true
    trace_pr_reviews: true
    capture_token_usage: true
    capture_costs: true
    capture_prompts: false
    capture_code_context: false

future_profiles:
  ddd:
    enabled: false
  tdd:
    enabled: false
  complexity:
    enabled: false
```

The MVP implements `review`, `security`, `fix`, `context`, repository instruction fragments, and Langfuse token/cost observability. `future_profiles` communicates intended future expansion but is not implemented as semantic validation in the MVP.

## Data Flow

1. A PR is opened or updated.
2. Azure DevOps branch policy triggers the pipeline.
3. Worker checks out the repository and reads PR metadata.
4. Worker checks whether `.ado-ai-review.yml` and required repository instruction files exist.
5. If required config or instruction files are missing, `PromptBootstrapper` creates them if push permissions allow it, comments on the PR, and exits without running review.
6. `ConfigLoader` loads and validates `.ado-ai-review.yml`.
7. `CommandRouter` reads PR comments.
8. If no actionable command exists, the worker posts or updates onboarding and exits.
9. If `/ai review` exists:
   - Build the repository index.
   - Load always-on style and AI instructions.
   - Select dynamic context from the index.
   - Run general review.
   - Publish comments and inline suggestions.
10. If `/ai security` exists:
   - Build the repository index.
   - Load always-on style and security guidance.
   - Prioritize security-relevant context.
   - Run security baseline review.
   - Publish comments and inline suggestions.
11. If `/ai fix` exists:
   - Build the repository index.
   - Identify mechanical fix candidates.
   - Publish small, local fixes as inline suggestions.
   - Create a fix branch only if branch candidates exist.
   - Commit each logical branch candidate separately.
   - Create a fix PR from the fix branch to the source branch of the reviewed PR.
   - Comment in the original PR with the fix PR link and `git cherry-pick <sha>` instructions for every commit.

## Error Handling And Permissions

- If comment permissions are missing, the worker fails with a clear pipeline error.
- If branch push permissions are missing, `/ai review` and `/ai security` still work, but `/ai fix` can only publish inline suggestions.
- If bootstrap push permissions are missing, the worker reports the missing files and stops.
- If config is invalid, the worker reports the validation error and does not call the model.
- If the model returns invalid JSON, the worker performs one repair attempt. If repair fails, the run reports a model-output error.
- If the PR source is unsafe for writes, such as a fork or untrusted source, bootstrap commits and fix branches are disabled.
- If the repo is large, indexing and context selection obey configured limits.
- Secret values detected locally are redacted before any model call.
- Code fixes are never committed directly to the source branch, except deterministic bootstrap config/instruction files.

## Testing

MVP test scope:

- Unit tests for `ConfigLoader`.
- Unit tests for `CommandRouter`.
- Unit tests for `RepoIndexer`.
- Unit tests for `ContextSelector`.
- Unit tests for `SuggestionPublisher`.
- Unit tests for `MechanicalFixer`.
- Contract tests for model response JSON schemas.

E2E tests and required manual E2E validation are out of scope for the MVP spec.

## Adoption And Observability Metrics

The MVP should capture lightweight metrics from pipeline logs, Azure DevOps activity, and Langfuse.

Product/adoption metrics:

- Number of PRs that received onboarding comments.
- Number of `/ai review` commands.
- Number of `/ai security` commands.
- Number of `/ai fix` commands.
- Number of findings published.
- Number of inline suggestions published.
- Number of fix PRs created.
- Number of commits included in fix PRs and therefore available for cherry-pick.

Langfuse/model usage metrics:

- Token usage per PR run.
- Token usage per module, such as indexer, reviewer, security reviewer, context selector, and fixer.
- Estimated model cost per PR run.
- Estimated model cost per command type.
- Model latency per module.
- Failed or repaired model responses.

For the MVP, Langfuse should not capture full prompts or code context by default. It should capture run metadata, module names, token usage, costs, latency, and status.

## Open Follow-Ups For Implementation Planning

- Choose the exact Azure AI Foundry SDK/API integration pattern.
- Confirm Azure DevOps support for PR thread `properties` in the chosen API/client path.
- Define the exact JSON schemas for findings, index entries, and fix candidates.
- Define the deterministic bootstrap templates.
- Define the Azure DevOps Pipeline YAML template and required permissions.
- Define how Langfuse credentials are provided in pipeline variables.

# Bootstrap Templates and Docs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move bootstrap file templates from inline Python strings to actual `.yml`/`.md` data files with rich agent guidance content, and write a complete README with environment variable reference and setup instructions.

**Architecture:** Store templates as real files in `src/ado_ai_pr_review/data/`, load them at runtime via `importlib.resources`, and include them in the wheel via hatchling's default non-Python file inclusion. README documents all env vars, pipeline setup, and configuration.

**Tech Stack:** Python 3.12 `importlib.resources`, hatchling (existing build), Markdown.

---

## File Map

| Action | Path |
|--------|------|
| Create | `src/ado_ai_pr_review/data/__init__.py` |
| Create | `src/ado_ai_pr_review/data/ado-ai-review.yml` |
| Create | `src/ado_ai_pr_review/data/instructions/reviewer.md` |
| Create | `src/ado_ai_pr_review/data/instructions/security.md` |
| Create | `src/ado_ai_pr_review/data/instructions/indexer.md` |
| Create | `src/ado_ai_pr_review/data/instructions/fixer.md` |
| Create | `src/ado_ai_pr_review/data/guidelines/code-style.md` |
| Create | `src/ado_ai_pr_review/data/guidelines/security.md` |
| Modify | `src/ado_ai_pr_review/templates.py` |
| Modify | `pyproject.toml` |
| Modify | `README.md` |
| Create | `tests/test_templates.py` |

---

## Task 1: Test that BOOTSTRAP_FILES loads from real data files

**Files:**
- Create: `tests/test_templates.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_templates.py
from ado_ai_pr_review.templates import BOOTSTRAP_FILES


EXPECTED_KEYS = {
    ".ado-ai-review.yml",
    ".ado-ai-review/instructions/reviewer.md",
    ".ado-ai-review/instructions/security.md",
    ".ado-ai-review/instructions/indexer.md",
    ".ado-ai-review/instructions/fixer.md",
    ".ado-ai-review/guidelines/code-style.md",
    ".ado-ai-review/guidelines/security.md",
}


def test_bootstrap_files_has_all_expected_keys() -> None:
    assert BOOTSTRAP_FILES.keys() == EXPECTED_KEYS


def test_bootstrap_files_all_non_empty() -> None:
    for path, content in BOOTSTRAP_FILES.items():
        assert isinstance(content, str), f"{path!r}: expected str"
        assert len(content) > 50, f"{path!r}: content too short ({len(content)} chars)"


def test_bootstrap_config_is_valid_yaml() -> None:
    import yaml
    data = yaml.safe_load(BOOTSTRAP_FILES[".ado-ai-review.yml"])
    assert data["version"] == 1
    assert "instructions" in data
    assert "reviewer" in data["instructions"]


def test_bootstrap_instruction_files_have_headings() -> None:
    instruction_keys = [k for k in BOOTSTRAP_FILES if "/instructions/" in k]
    for key in instruction_keys:
        assert BOOTSTRAP_FILES[key].startswith("#"), f"{key!r}: should start with a Markdown heading"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_templates.py -v
```

Expected: FAIL — `BOOTSTRAP_FILES` values are currently short inline strings, not loaded from files.

---

## Task 2: Create the data package and all template files

**Files:**
- Create: `src/ado_ai_pr_review/data/__init__.py`
- Create: `src/ado_ai_pr_review/data/ado-ai-review.yml`
- Create: `src/ado_ai_pr_review/data/instructions/reviewer.md`
- Create: `src/ado_ai_pr_review/data/instructions/security.md`
- Create: `src/ado_ai_pr_review/data/instructions/indexer.md`
- Create: `src/ado_ai_pr_review/data/instructions/fixer.md`
- Create: `src/ado_ai_pr_review/data/guidelines/code-style.md`
- Create: `src/ado_ai_pr_review/data/guidelines/security.md`

- [ ] **Step 1: Create the data package marker**

```bash
touch src/ado_ai_pr_review/data/__init__.py
```

- [ ] **Step 2: Create `src/ado_ai_pr_review/data/ado-ai-review.yml`**

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
```

- [ ] **Step 3: Create `src/ado_ai_pr_review/data/instructions/reviewer.md`**

```markdown
# Reviewer Instructions

## Focus Areas

Prioritize findings in this order:

1. **Correctness** – logic errors, off-by-one mistakes, wrong null/empty handling, race conditions,
   incorrect return values.
2. **Test gaps** – missing tests for new behaviour, tests that only cover already-tested paths,
   assertions that do not actually verify the intent.
3. **Readability** – confusing names, unclear control flow, missing context that forces readers
   to guess about intent or side effects.
4. **Maintainability** – unnecessary coupling, duplicated logic, abstractions that do not pay
   for their complexity.

## What to Skip

- Style issues already enforced by the project formatter.
- Bikeshedding about naming when the existing name is clear enough.
- Refactors that are outside the scope of the PR.
- Speculative performance concerns without evidence of a hot path.

## Finding Quality

Each finding must have a clear title and a short explanation that covers:
1. What the problem is.
2. Why it matters (consequence, not just rule citation).
3. A concrete suggestion or code example.

Avoid vague comments like "this could be improved" or "consider refactoring". Be specific.

## Severity Guide

- **critical**: data loss, security hole, or crash in a common path.
- **high**: incorrect behaviour visible to users or callers.
- **medium**: likely to cause a bug under common conditions; test gap for important path.
- **low**: code clarity, naming, minor style concerns.
```

- [ ] **Step 4: Create `src/ado_ai_pr_review/data/instructions/security.md`**

```markdown
# Security Instructions

## Security Checklist

For every PR diff, check each category:

1. **Secrets** – API keys, tokens, passwords, certificates, or any credential in code or config.
2. **Injection** – SQL, shell command, LDAP, XPath, template injection in user-controlled input.
3. **Authentication** – Endpoints or operations that require authentication actually enforce it.
4. **Authorization** – Users cannot access or modify resources they do not own; checks happen
   server-side, not only client-side.
5. **Input validation** – External inputs are validated at the boundary before processing or storage.
6. **Unsafe deserialization** – No untrusted data deserialized into live objects without type checks.
7. **Sensitive data handling** – PII, tokens, and secrets are not logged, returned in errors,
   cached in plain text, or stored without encryption.

## Severity Guide

- **critical**: Direct exploit path — injection with user control, exposed credential, auth bypass.
- **high**: Privilege escalation, sensitive data leak, missing authz on a write endpoint.
- **medium**: Defence-in-depth gap, missing validation on a non-critical path, risky pattern.
- **low**: Hardening suggestion, informational observation.

## Hard Constraint

Never include secret values in findings, explanations, or suggested code.
Report only location (file path, line range) and risk type.
```

- [ ] **Step 5: Create `src/ado_ai_pr_review/data/instructions/indexer.md`**

```markdown
# Indexer Instructions

## Goal

Produce a short, accurate description of each file so the reviewer can decide whether
to load it as context for the current PR.

## Description Format

Two sentences maximum:
1. What the file does or contains.
2. What domain, layer, or role it belongs to (e.g. "API handler", "domain model",
   "database migration", "CI pipeline configuration", "test fixture").

## Tags

Apply every relevant tag from this set:

- `business` – core domain logic, entities, aggregates, use cases, business rules.
- `tests` – test files, fixtures, test utilities, test configuration.
- `security` – authentication, authorization, encryption, secret handling, input validation.
- `api` – HTTP handlers, serializers, route definitions, protocol adapters.
- `domain` – value objects, aggregates, domain events, domain services.
- `config` – environment loading, application configuration, feature flags, infrastructure config.
- `docs` – documentation, ADRs, specs, changelogs.

## Relevance Hints

Flag a file as relevant to the current PR if:
- It defines a type, class, or function that the diff directly modifies or calls.
- It contains tests for code touched by the diff.
- It enforces a security policy that the diff may bypass or weaken.
- It provides domain context that a reviewer would need to judge correctness.

## Exclusions

Do not index build outputs, vendored dependencies, lock files, generated protobuf/OpenAPI files,
or binary assets. Respect the `exclude` patterns from the config.
```

- [ ] **Step 6: Create `src/ado_ai_pr_review/data/instructions/fixer.md`**

```markdown
# Fixer Instructions

## Mechanical Fix Whitelist

Only propose fixes from this list:

- **Formatting** – changes that match the project formatter output exactly
  (e.g. `black`, `ruff format`, `prettier`).
- **Lint fixes** – unused imports, shadowed names, obvious missing type annotations
  where the pattern is already established in the file.
- **Import cleanup** – removing unused imports, reordering to match the project convention.
- **Safe renames** – a variable or function name is clearly wrong or inconsistent with
  the surrounding codebase, and the rename is purely local (no cross-file callers).
- **Type annotation corrections** – adding or fixing annotations that do not change
  runtime behaviour.
- **Trivially equivalent refactors** – `if x == True:` → `if x:`,
  `len(lst) == 0` → `not lst`, `x is not None and x.foo()` → `x and x.foo()`.
- **Test mechanical fixes** – wrong assertion on a stable interface, obvious typo in a
  test description, assert on wrong variable when the intent is unambiguous.

## Hard Rules

- Do not change business logic, algorithm implementations, or API contracts.
- Do not add new functionality, even if it seems obviously useful.
- Do not fix anything that requires semantic understanding of the domain.
- Do not produce a fix when there is any doubt about whether it is purely mechanical.
- If in doubt, emit a review comment instead of a fix candidate.

## Delivery Format

Use `inline_suggestion` for single-file, single-hunk changes under 20 lines.
Use `fix_branch_candidate` for multi-file changes or when the fix spans many locations.
When uncertain, prefer `fix_branch_candidate`.
```

- [ ] **Step 7: Create `src/ado_ai_pr_review/data/guidelines/code-style.md`**

```markdown
# Code Style Guidelines

> This is the default placeholder. Replace or extend it with your project's actual style guide.
> Reference this file from `.ado-ai-review.yml` under `guidelines.code_style`.

## General Principles

- Prefer clarity over cleverness. Write code for the next reader.
- Follow the project formatter; do not argue with its output.
- Use consistent naming conventions throughout the codebase.
- Comments explain *why*, not *what*. The code explains what.

## Naming

- Use the conventions already established in the file you are editing.
- Avoid abbreviations unless they are universally understood in the domain (e.g. `id`, `url`).

## Error Handling

- Fail fast at system boundaries; handle errors at the layer where you have enough context
  to recover or report meaningfully.
- Do not swallow exceptions silently.
- Prefer specific exception types over bare `except Exception`.

## Tests

- Each test covers one behaviour. One assertion per test is a good heuristic.
- Test names describe the scenario: `test_returns_empty_list_when_no_files_exist`.
- Prefer real objects over mocks when the cost is low.
```

- [ ] **Step 8: Create `src/ado_ai_pr_review/data/guidelines/security.md`**

```markdown
# Security Guidelines

> This is the default placeholder. Replace or extend it with your team's actual security requirements.
> Reference this file from `.ado-ai-review.yml` under `guidelines.security`.

## Baseline Requirements

- All external inputs must be validated and sanitized before processing or storage.
- Secrets must never appear in logs, error messages, API responses, or test fixtures.
- Use parameterized queries or ORM-level escaping for all database access.
- Enforce authentication and authorization at every API endpoint — never rely solely on
  client-side checks.

## Dependencies

- Review newly added dependencies for known CVEs before merging.
- Pin dependency versions in production manifests.
- Avoid transitive dependencies on abandoned or unreviewed packages for security-sensitive paths.

## Secrets Management

- Store credentials in environment variables or a secrets manager. Never commit them.
- Rotate credentials immediately if accidentally exposed.
- Treat anything in `.env` files as a local-only convenience; never commit `.env`.

## Sensitive Data

- Do not log PII (names, emails, IDs) in production log levels.
- Store passwords hashed with a modern algorithm (bcrypt, argon2). Never plain text or MD5/SHA1.
- Encrypt sensitive fields at rest if the database does not provide full-disk encryption.
```

---

## Task 3: Update `templates.py` to load from data files

**Files:**
- Modify: `src/ado_ai_pr_review/templates.py`

- [ ] **Step 1: Replace inline strings with `importlib.resources` loading**

Replace the entire content of `src/ado_ai_pr_review/templates.py` with:

```python
from __future__ import annotations

from importlib.resources import files

_DATA = files("ado_ai_pr_review") / "data"


def _read(rel: str) -> str:
    parts = rel.split("/")
    node = _DATA
    for part in parts:
        node = node / part
    return node.read_text(encoding="utf-8")  # type: ignore[union-attr]


BOOTSTRAP_FILES: dict[str, str] = {
    ".ado-ai-review.yml": _read("ado-ai-review.yml"),
    ".ado-ai-review/instructions/reviewer.md": _read("instructions/reviewer.md"),
    ".ado-ai-review/instructions/security.md": _read("instructions/security.md"),
    ".ado-ai-review/instructions/indexer.md": _read("instructions/indexer.md"),
    ".ado-ai-review/instructions/fixer.md": _read("instructions/fixer.md"),
    ".ado-ai-review/guidelines/code-style.md": _read("guidelines/code-style.md"),
    ".ado-ai-review/guidelines/security.md": _read("guidelines/security.md"),
}
```

- [ ] **Step 2: Run the template tests**

```bash
pytest tests/test_templates.py -v
```

Expected: All 4 tests PASS.

- [ ] **Step 3: Run the full test suite to verify no regressions**

```bash
pytest -v
```

Expected: All tests PASS. The existing `test_bootstrap.py` tests use `Bootstrapper` which calls `BOOTSTRAP_FILES`, so they must still pass.

- [ ] **Step 4: Commit**

```bash
git add src/ado_ai_pr_review/data/ src/ado_ai_pr_review/templates.py tests/test_templates.py
git commit -m "feat: move bootstrap templates to data files with rich agent guidance"
```

---

## Task 4: Verify hatchling packages the data files

**Files:**
- Modify: `pyproject.toml` (only if the verification below fails)

- [ ] **Step 1: Build a wheel and inspect its contents**

```bash
python -m pip install --quiet build
python -m build --wheel --outdir /tmp/ado-ai-dist .
python -c "
import zipfile, sys
with zipfile.ZipFile(list(__import__('pathlib').Path('/tmp/ado-ai-dist').glob('*.whl'))[0]) as z:
    data_files = [n for n in z.namelist() if 'data/' in n]
    print('\n'.join(sorted(data_files)))
"
```

Expected output contains entries like:
```
ado_ai_pr_review/data/__init__.py
ado_ai_pr_review/data/ado-ai-review.yml
ado_ai_pr_review/data/guidelines/code-style.md
ado_ai_pr_review/data/guidelines/security.md
ado_ai_pr_review/data/instructions/fixer.md
ado_ai_pr_review/data/instructions/indexer.md
ado_ai_pr_review/data/instructions/reviewer.md
ado_ai_pr_review/data/instructions/security.md
```

- [ ] **Step 2: If any data files are missing, add explicit includes to `pyproject.toml`**

Add this section to `pyproject.toml` only if Step 1 shows missing files:

```toml
[tool.hatch.build.targets.wheel.force-include]
"src/ado_ai_pr_review/data" = "ado_ai_pr_review/data"
```

- [ ] **Step 3: If pyproject.toml was modified, re-run tests and commit**

```bash
pytest -v
git add pyproject.toml
git commit -m "chore: explicitly include data files in wheel"
```

---

## Task 5: Write the README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace README.md with complete documentation**

```markdown
# ADO AI PR Review

Azure DevOps AI pull request reviewer. Runs as a Docker container in Azure DevOps Pipelines,
reacts to `/ai` commands in PR comments, and posts code review findings, security findings,
and mechanical fix suggestions.

## Quick Start

1. Add `azure-pipelines.ado-ai-review.yml` to your repository (copy from this repo).
2. Create a branch policy that triggers the pipeline on every PR.
3. Set the required pipeline variables (see [Environment Variables](#environment-variables)).
4. Open a PR and comment `/ai review`.

## Available Commands

Comment one of these in any PR discussion thread:

| Command | Description |
|---------|-------------|
| `/ai review` | General code review: correctness, test gaps, readability, maintainability. |
| `/ai security` | Security baseline: secrets, injection, auth, authorization, input validation. |
| `/ai fix` | Mechanical fixes only: formatting, lint, imports, safe renames. |

On the first run (no command yet), the worker posts an onboarding comment listing the commands
and bootstraps missing configuration files.

## Pipeline Setup

Copy `azure-pipelines.ado-ai-review.yml` from this repository into your target repo.
Create an Azure DevOps branch policy that triggers this pipeline on PR creation and update.

### Required ADO Permissions

Grant these permissions to the **project build service** identity:

| Permission | Reason |
|-----------|--------|
| Code read | Read repository files and PR diff. |
| Pull Request contribute | Post PR comments and threads. |
| Contribute (branch) | Create bootstrap commits and fix branches. Required only for `/ai fix` and bootstrap. |

The pipeline YAML must include:

```yaml
steps:
  - checkout: self
    persistCredentials: true   # required for git push
    fetchDepth: 0              # required for full diff

  - script: ...
    env:
      SYSTEM_ACCESSTOKEN: $(System.AccessToken)   # must be explicitly mapped
```

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
    - AGENTS.md                                  # optional: existing files are picked up if they exist
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
    max_files: 20   # max number of repository files loaded as context per review

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

The files under `.ado-ai-review/guidelines/` are loaded as always-on context:

| File | Purpose |
|------|---------|
| `code-style.md` | Project-specific code style and naming conventions. |
| `security.md` | Team-specific security requirements and sensitive data policies. |

Existing files like `AGENTS.md`, `CLAUDE.md`, and `.github/copilot-instructions.md` are
loaded automatically if they exist and are listed under `guidelines.code_style`.

## Security Boundary

The model never receives a raw shell tool. Every write action (git push, PR comment) is
performed by Python code that validates model output first. Secret values detected locally
are redacted before any model call.

Fix commits are never written directly to the PR source branch. They go to a separate
`ai-fix/...` branch and a fix PR.

## Local Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check src tests
mypy src
```

To run against a real PR (read-only, no writes):

```bash
export SYSTEM_ACCESSTOKEN=...
export SYSTEM_TEAMFOUNDATIONCOLLECTIONURI=https://dev.azure.com/myorg/
export SYSTEM_TEAMPROJECT=myproject
export BUILD_REPOSITORY_ID=...
export SYSTEM_PULLREQUEST_PULLREQUESTID=123
export AZURE_OPENAI_BASE_URL=https://...openai.azure.com/openai/v1/
export AZURE_OPENAI_DEPLOYMENT=gpt-4o
ado-ai-pr-review run --repo-root . --dry-run
```
```

- [ ] **Step 2: Verify README renders correctly (spot-check)**

```bash
python -c "
import re, pathlib
text = pathlib.Path('README.md').read_text()
sections = re.findall(r'^## .+', text, re.MULTILINE)
print('\n'.join(sections))
"
```

Expected output:
```
## Quick Start
## Available Commands
## Pipeline Setup
## Environment Variables
## Configuration
## Security Boundary
## Local Development
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: write full README with env var reference and configuration guide"
```

---

## Self-Review Against Spec

**Spec coverage:**

| Spec requirement | Task |
|-----------------|------|
| Bootstrap files not in .py | Task 2 (data files) + Task 3 (templates.py) |
| Rich instructions for reviewer, security, indexer, fixer | Task 2 steps 3–6 |
| Rich guidelines for code-style, security | Task 2 steps 7–8 |
| README configuration docs | Task 5 |
| Env var list | Task 5 |

**Placeholder scan:** No TBD, TODO, or vague steps — all steps contain complete content.

**Type consistency:** `BOOTSTRAP_FILES: dict[str, str]` matches existing `bootstrap.py` usage.

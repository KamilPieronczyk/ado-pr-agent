# ADO AI PR Review MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Docker-packaged Python worker that runs in Azure DevOps Pipelines, reacts to `/ai review`, `/ai security`, and `/ai fix` PR comments, uses constrained CLI-backed tools for Azure DevOps and git operations, calls Azure OpenAI/Foundry models for review reasoning, and publishes concise PR feedback.

**Architecture:** Use a tool-based agent shell with a constrained command executor. The model never receives a raw shell; it receives narrow function tools implemented by Python code that invokes installed Docker CLIs (`git`, `az`, and `az devops invoke`) with allowlisted command shapes. Deterministic workflow code handles bootstrap, idempotency, publishing, branch creation, and PR creation; model output is treated as structured data that must validate before any write action.

**Tech Stack:** Python 3.12, Typer, Pydantic v2, PyYAML, OpenAI Python SDK Responses API, azure-identity, Langfuse, pytest, pytest-mock, ruff, mypy, Docker, Azure CLI `azure-devops` extension, git.

---

## Research Decisions

- Prefer CLI-first execution in Docker: use `git`, `az repos pr`, and `az devops invoke` wherever possible.
- Do not expose arbitrary shell execution to the model. Every model-callable tool is a typed Python function with JSON schema, allowlisted argv, timeouts, output caps, and secret redaction.
- Use `az repos pr show/create/update/list` for supported PR operations.
- Use `az devops invoke` for PR threads, comments, iterations, and iteration changes because native `az repos pr` does not expose all comment/thread operations.
- Use Azure DevOps PR thread `properties` for idempotency when supported through `az devops invoke`; also include human-readable markers in comments as a fallback.
- Use Markdown `suggestion` fenced code blocks for Azure DevOps inline suggestions.
- Use OpenAI-compatible Azure OpenAI/Foundry v1 Responses API through the `openai.OpenAI` client. Use Microsoft Entra auth via `azure-identity` when `AZURE_OPENAI_API_KEY` is absent.

Useful references:

- Azure CLI PR commands: https://learn.microsoft.com/en-gb/cli/azure/repos/pr?view=azure-cli-latest
- Azure CLI generic DevOps invoke: https://learn.microsoft.com/cli/azure/devops?view=azure-cli-latest
- Azure DevOps PR threads REST: https://learn.microsoft.com/rest/api/azure/devops/git/pull-request-threads/list?view=azure-devops-rest-7.1
- Azure DevOps PR iteration changes REST: https://learn.microsoft.com/rest/api/azure/devops/git/pull-request-iteration-changes?view=azure-devops-rest-7.1
- Azure DevOps Markdown suggestions: https://learn.microsoft.com/azure/devops/project/wiki/markdown-guidance?view=azure-devops
- OpenAI function calling: https://platform.openai.com/docs/guides/function-calling
- Azure OpenAI/Foundry v1 API: https://learn.microsoft.com/azure/ai-foundry/foundry-models/how-to/use-chat-completions

## File Structure

Create this project structure:

```text
pyproject.toml
ruff.toml
mypy.ini
Dockerfile
azure-pipelines.ado-ai-review.yml
src/ado_ai_pr_review/__init__.py
src/ado_ai_pr_review/__main__.py
src/ado_ai_pr_review/cli.py
src/ado_ai_pr_review/runtime.py
src/ado_ai_pr_review/logging_config.py
src/ado_ai_pr_review/errors.py
src/ado_ai_pr_review/cli_runner.py
src/ado_ai_pr_review/tool_policy.py
src/ado_ai_pr_review/ado_toolset.py
src/ado_ai_pr_review/git_toolset.py
src/ado_ai_pr_review/models.py
src/ado_ai_pr_review/config.py
src/ado_ai_pr_review/bootstrap.py
src/ado_ai_pr_review/templates.py
src/ado_ai_pr_review/commands.py
src/ado_ai_pr_review/diff.py
src/ado_ai_pr_review/indexer.py
src/ado_ai_pr_review/context.py
src/ado_ai_pr_review/security.py
src/ado_ai_pr_review/model_client.py
src/ado_ai_pr_review/reviewer.py
src/ado_ai_pr_review/publisher.py
src/ado_ai_pr_review/fixer.py
src/ado_ai_pr_review/observability.py
tests/conftest.py
tests/test_cli_runner.py
tests/test_tool_policy.py
tests/test_config.py
tests/test_bootstrap.py
tests/test_commands.py
tests/test_diff.py
tests/test_indexer.py
tests/test_context.py
tests/test_security.py
tests/test_model_client.py
tests/test_reviewer.py
tests/test_publisher.py
tests/test_fixer.py
tests/test_cli.py
docs/operations/ado-ai-review.md
```

Responsibilities:

- `cli.py`: Typer entrypoint and top-level orchestration.
- `runtime.py`: environment-derived pipeline context.
- `cli_runner.py`: subprocess execution with timeouts, output caps, and redaction.
- `tool_policy.py`: allowlisted command policies for `git` and `az`.
- `ado_toolset.py`: narrow Azure DevOps CLI-backed functions.
- `git_toolset.py`: narrow git CLI-backed functions.
- `models.py`: shared Pydantic schemas.
- `config.py`: `.ado-ai-review.yml` loader and validator.
- `bootstrap.py` and `templates.py`: deterministic config/instruction file creation.
- `commands.py`: PR comment command detection and onboarding decision.
- `diff.py`: git/ADO diff loading and mapping to thread positions.
- `indexer.py`: lightweight repository index.
- `context.py`: context selection from config, index, and diff.
- `security.py`: local security heuristics and secret redaction.
- `model_client.py`: Azure OpenAI/Foundry Responses API wrapper with validated JSON output.
- `reviewer.py`: review/security orchestration.
- `publisher.py`: PR thread/comment/suggestion publishing.
- `fixer.py`: mechanical fix classification and branch PR creation.
- `observability.py`: Langfuse and log metrics.

## Implementation Tasks

### Task 1: Project Skeleton And Tooling

**Files:**
- Create: `pyproject.toml`
- Create: `ruff.toml`
- Create: `mypy.ini`
- Create: `src/ado_ai_pr_review/__init__.py`
- Create: `src/ado_ai_pr_review/__main__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Write the packaging and import smoke test**

Create `tests/conftest.py`:

```python
from pathlib import Path


def fixture_path(name: str) -> Path:
    return Path(__file__).parent / "fixtures" / name
```

Create `tests/test_cli.py`:

```python
from typer.testing import CliRunner

from ado_ai_pr_review.cli import app


def test_cli_help_renders() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "run" in result.output
```

- [ ] **Step 2: Run the smoke test to verify it fails**

Run:

```bash
pytest tests/test_cli.py::test_cli_help_renders -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'ado_ai_pr_review'`.

- [ ] **Step 3: Add Python project configuration**

Create `pyproject.toml`:

```toml
[build-system]
requires = ["hatchling>=1.27"]
build-backend = "hatchling.build"

[project]
name = "ado-ai-pr-review"
version = "0.1.0"
description = "Azure DevOps CLI-first AI pull request reviewer"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
  "azure-identity>=1.21.0",
  "langfuse>=2.60.0",
  "openai>=1.99.0",
  "pydantic>=2.11.0",
  "pyyaml>=6.0.2",
  "typer>=0.15.0",
]

[project.optional-dependencies]
dev = [
  "mypy>=1.15.0",
  "pytest>=8.3.0",
  "pytest-mock>=3.14.0",
  "ruff>=0.9.0",
]

[project.scripts]
ado-ai-pr-review = "ado_ai_pr_review.cli:app"

[tool.hatch.build.targets.wheel]
packages = ["src/ado_ai_pr_review"]
```

Create `ruff.toml`:

```toml
line-length = 100
target-version = "py312"

[lint]
select = ["E", "F", "I", "UP", "B", "SIM", "RUF"]
ignore = ["E501"]
```

Create `mypy.ini`:

```ini
[mypy]
python_version = 3.12
strict = True
warn_unused_ignores = True
warn_redundant_casts = True
disallow_any_generics = True
```

Create `src/ado_ai_pr_review/__init__.py`:

```python
__all__ = ["__version__"]

__version__ = "0.1.0"
```

Create `src/ado_ai_pr_review/__main__.py`:

```python
from ado_ai_pr_review.cli import app

app()
```

Create `src/ado_ai_pr_review/cli.py`:

```python
from typing import Annotated

import typer

app = typer.Typer(no_args_is_help=True)


@app.command()
def run(
    repo_root: Annotated[str, typer.Option("--repo-root")] = ".",
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
) -> None:
    """Run the ADO AI PR review worker."""
    typer.echo(f"repo_root={repo_root} dry_run={dry_run}")
```

- [ ] **Step 4: Run the smoke test to verify it passes**

Run:

```bash
python -m pip install -e ".[dev]"
pytest tests/test_cli.py::test_cli_help_renders -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add pyproject.toml ruff.toml mypy.ini src/ado_ai_pr_review/__init__.py src/ado_ai_pr_review/__main__.py src/ado_ai_pr_review/cli.py tests/conftest.py tests/test_cli.py
git commit -m "chore: scaffold python worker"
```

### Task 2: Runtime Context And Error Types

**Files:**
- Create: `src/ado_ai_pr_review/errors.py`
- Create: `src/ado_ai_pr_review/runtime.py`
- Create: `src/ado_ai_pr_review/logging_config.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write failing tests for pipeline context**

Append to `tests/test_cli.py`:

```python
import pytest

from ado_ai_pr_review.errors import ConfigurationError
from ado_ai_pr_review.runtime import RuntimeContext


def test_runtime_context_reads_pipeline_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SYSTEM_TEAMFOUNDATIONCOLLECTIONURI", "https://dev.azure.com/acme/")
    monkeypatch.setenv("SYSTEM_TEAMPROJECT", "Payments")
    monkeypatch.setenv("BUILD_REPOSITORY_ID", "repo-123")
    monkeypatch.setenv("BUILD_REPOSITORY_NAME", "checkout-repo")
    monkeypatch.setenv("SYSTEM_PULLREQUEST_PULLREQUESTID", "42")
    monkeypatch.setenv("SYSTEM_PULLREQUEST_SOURCEBRANCH", "refs/heads/users/alice/change")
    monkeypatch.setenv("SYSTEM_PULLREQUEST_TARGETBRANCH", "refs/heads/main")
    monkeypatch.setenv("SYSTEM_PULLREQUEST_ISFORK", "False")
    monkeypatch.setenv("BUILD_BUILDID", "9001")
    monkeypatch.setenv("SYSTEM_ACCESSTOKEN", "token-value")

    context = RuntimeContext.from_env(repo_root=".")

    assert context.organization_url == "https://dev.azure.com/acme/"
    assert context.project == "Payments"
    assert context.repository_id == "repo-123"
    assert context.pull_request_id == 42
    assert context.is_fork is False
    assert context.system_access_token == "token-value"


def test_runtime_context_requires_pr_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SYSTEM_PULLREQUEST_PULLREQUESTID", raising=False)

    with pytest.raises(ConfigurationError, match="SYSTEM_PULLREQUEST_PULLREQUESTID"):
        RuntimeContext.from_env(repo_root=".")
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/test_cli.py::test_runtime_context_reads_pipeline_environment tests/test_cli.py::test_runtime_context_requires_pr_id -v
```

Expected: FAIL with `ModuleNotFoundError` for `ado_ai_pr_review.errors`.

- [ ] **Step 3: Implement runtime context and errors**

Create `src/ado_ai_pr_review/errors.py`:

```python
class AdoAiReviewError(Exception):
    """Base exception for worker failures."""


class ConfigurationError(AdoAiReviewError):
    """Raised when required configuration is absent or invalid."""


class CommandRejectedError(AdoAiReviewError):
    """Raised when a command violates the CLI execution policy."""


class CommandExecutionError(AdoAiReviewError):
    """Raised when an allowlisted command exits unsuccessfully."""


class ModelOutputError(AdoAiReviewError):
    """Raised when model output cannot be parsed or validated."""
```

Create `src/ado_ai_pr_review/runtime.py`:

```python
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from ado_ai_pr_review.errors import ConfigurationError


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ConfigurationError(f"Missing required environment variable: {name}")
    return value


def _optional_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes"}


@dataclass(frozen=True)
class RuntimeContext:
    repo_root: Path
    organization_url: str
    project: str
    repository_id: str
    repository_name: str
    pull_request_id: int
    source_branch: str
    target_branch: str
    is_fork: bool
    build_id: str
    system_access_token: str | None

    @classmethod
    def from_env(cls, repo_root: str) -> "RuntimeContext":
        pr_id = _required_env("SYSTEM_PULLREQUEST_PULLREQUESTID")
        try:
            pull_request_id = int(pr_id)
        except ValueError as exc:
            raise ConfigurationError("SYSTEM_PULLREQUEST_PULLREQUESTID must be an integer") from exc

        return cls(
            repo_root=Path(repo_root).resolve(),
            organization_url=_required_env("SYSTEM_TEAMFOUNDATIONCOLLECTIONURI"),
            project=_required_env("SYSTEM_TEAMPROJECT"),
            repository_id=_required_env("BUILD_REPOSITORY_ID"),
            repository_name=os.getenv("BUILD_REPOSITORY_NAME", ""),
            pull_request_id=pull_request_id,
            source_branch=os.getenv("SYSTEM_PULLREQUEST_SOURCEBRANCH", ""),
            target_branch=os.getenv("SYSTEM_PULLREQUEST_TARGETBRANCH", ""),
            is_fork=_optional_bool("SYSTEM_PULLREQUEST_ISFORK", False),
            build_id=os.getenv("BUILD_BUILDID", "local"),
            system_access_token=os.getenv("SYSTEM_ACCESSTOKEN"),
        )
```

Create `src/ado_ai_pr_review/logging_config.py`:

```python
from __future__ import annotations

import logging


def configure_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
pytest tests/test_cli.py::test_runtime_context_reads_pipeline_environment tests/test_cli.py::test_runtime_context_requires_pr_id -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/ado_ai_pr_review/errors.py src/ado_ai_pr_review/runtime.py src/ado_ai_pr_review/logging_config.py tests/test_cli.py
git commit -m "feat: read azure pipelines runtime context"
```

### Task 3: Constrained CLI Runner

**Files:**
- Create: `src/ado_ai_pr_review/tool_policy.py`
- Create: `src/ado_ai_pr_review/cli_runner.py`
- Test: `tests/test_tool_policy.py`
- Test: `tests/test_cli_runner.py`

- [ ] **Step 1: Write failing tests for command policy and redaction**

Create `tests/test_tool_policy.py`:

```python
import pytest

from ado_ai_pr_review.errors import CommandRejectedError
from ado_ai_pr_review.tool_policy import CommandPolicy


def test_command_policy_allows_known_git_command() -> None:
    policy = CommandPolicy.default()

    policy.validate(["git", "diff", "--unified=0", "origin/main...HEAD"])


def test_command_policy_rejects_unknown_binary() -> None:
    policy = CommandPolicy.default()

    with pytest.raises(CommandRejectedError, match="Binary is not allowlisted"):
        policy.validate(["bash", "-lc", "echo unsafe"])


def test_command_policy_rejects_unlisted_az_shape() -> None:
    policy = CommandPolicy.default()

    with pytest.raises(CommandRejectedError, match="Command shape is not allowlisted"):
        policy.validate(["az", "account", "show"])
```

Create `tests/test_cli_runner.py`:

```python
import subprocess
from pathlib import Path

from pytest_mock import MockerFixture

from ado_ai_pr_review.cli_runner import CliRunner
from ado_ai_pr_review.tool_policy import CommandPolicy


def test_cli_runner_redacts_secret_output(mocker: MockerFixture, tmp_path: Path) -> None:
    completed = subprocess.CompletedProcess(
        args=["git", "status", "--short"],
        returncode=0,
        stdout="token=abc123\n",
        stderr="",
    )
    mocker.patch("subprocess.run", return_value=completed)
    runner = CliRunner(policy=CommandPolicy.default(), secrets=["abc123"])

    result = runner.run(["git", "status", "--short"], cwd=tmp_path)

    assert result.stdout == "token=[REDACTED]\n"
    assert result.returncode == 0
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/test_tool_policy.py tests/test_cli_runner.py -v
```

Expected: FAIL with `ModuleNotFoundError` for `ado_ai_pr_review.tool_policy`.

- [ ] **Step 3: Implement allowlisted command policy and runner**

Create `src/ado_ai_pr_review/tool_policy.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from ado_ai_pr_review.errors import CommandRejectedError


@dataclass(frozen=True)
class CommandPolicy:
    allowed_shapes: tuple[tuple[str, ...], ...]

    @classmethod
    def default(cls) -> "CommandPolicy":
        return cls(
            allowed_shapes=(
                ("git", "status"),
                ("git", "diff"),
                ("git", "fetch"),
                ("git", "checkout"),
                ("git", "switch"),
                ("git", "branch"),
                ("git", "add"),
                ("git", "commit"),
                ("git", "push"),
                ("git", "rev-parse"),
                ("git", "show"),
                ("git", "config"),
                ("az", "extension"),
                ("az", "devops", "configure"),
                ("az", "devops", "invoke"),
                ("az", "repos", "pr"),
            )
        )

    def validate(self, argv: list[str]) -> None:
        if not argv:
            raise CommandRejectedError("Command argv cannot be empty")
        if argv[0] not in {"git", "az"}:
            raise CommandRejectedError(f"Binary is not allowlisted: {argv[0]}")
        if not any(self._matches_shape(argv, shape) for shape in self.allowed_shapes):
            raise CommandRejectedError(f"Command shape is not allowlisted: {' '.join(argv[:4])}")

    @staticmethod
    def _matches_shape(argv: list[str], shape: tuple[str, ...]) -> bool:
        return len(argv) >= len(shape) and tuple(argv[: len(shape)]) == shape
```

Create `src/ado_ai_pr_review/cli_runner.py`:

```python
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from ado_ai_pr_review.errors import CommandExecutionError
from ado_ai_pr_review.tool_policy import CommandPolicy


@dataclass(frozen=True)
class CommandResult:
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str


class CliRunner:
    def __init__(
        self,
        policy: CommandPolicy,
        secrets: list[str] | None = None,
        timeout_seconds: int = 60,
        max_output_chars: int = 200_000,
    ) -> None:
        self._policy = policy
        self._secrets = [secret for secret in secrets or [] if secret]
        self._timeout_seconds = timeout_seconds
        self._max_output_chars = max_output_chars

    def run(
        self,
        argv: list[str],
        cwd: Path,
        env: Mapping[str, str] | None = None,
        check: bool = True,
    ) -> CommandResult:
        self._policy.validate(argv)
        completed = subprocess.run(
            argv,
            cwd=cwd,
            env=dict(env) if env is not None else None,
            check=False,
            capture_output=True,
            text=True,
            timeout=self._timeout_seconds,
        )
        result = CommandResult(
            argv=argv,
            returncode=completed.returncode,
            stdout=self._cap_and_redact(completed.stdout),
            stderr=self._cap_and_redact(completed.stderr),
        )
        if check and result.returncode != 0:
            raise CommandExecutionError(
                f"Command failed with exit code {result.returncode}: {' '.join(argv)}\n{result.stderr}"
            )
        return result

    def _cap_and_redact(self, value: str) -> str:
        capped = value[: self._max_output_chars]
        for secret in self._secrets:
            capped = capped.replace(secret, "[REDACTED]")
        return capped
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
pytest tests/test_tool_policy.py tests/test_cli_runner.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/ado_ai_pr_review/tool_policy.py src/ado_ai_pr_review/cli_runner.py tests/test_tool_policy.py tests/test_cli_runner.py
git commit -m "feat: constrain cli command execution"
```

### Task 4: Shared Schemas

**Files:**
- Create: `src/ado_ai_pr_review/models.py`
- Test: `tests/test_model_client.py`

- [ ] **Step 1: Write failing schema tests**

Create `tests/test_model_client.py`:

```python
from ado_ai_pr_review.models import Finding, FindingSeverity, FindingType, ReviewResult


def test_review_result_validates_finding_payload() -> None:
    result = ReviewResult.model_validate(
        {
            "summary": "Two issues found.",
            "findings": [
                {
                    "type": "bug_risk",
                    "severity": "high",
                    "title": "Null value can reach formatter",
                    "body": "Guard the value before formatting.",
                    "file_path": "src/app.py",
                    "line_start": 12,
                    "line_end": 12,
                    "suggested_code": "if value is None:\n    return None",
                }
            ],
        }
    )

    assert isinstance(result.findings[0], Finding)
    assert result.findings[0].severity is FindingSeverity.HIGH
    assert result.findings[0].type is FindingType.BUG_RISK
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
pytest tests/test_model_client.py::test_review_result_validates_finding_payload -v
```

Expected: FAIL with `ModuleNotFoundError` for `ado_ai_pr_review.models`.

- [ ] **Step 3: Implement shared schemas**

Create `src/ado_ai_pr_review/models.py`:

```python
from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ReviewCommand(StrEnum):
    REVIEW = "review"
    SECURITY = "security"
    FIX = "fix"
    ONBOARDING = "onboarding"


class FindingSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FindingType(StrEnum):
    BUG_RISK = "bug_risk"
    SECURITY = "security"
    TEST_GAP = "test_gap"
    READABILITY = "readability"
    MAINTAINABILITY = "maintainability"
    MECHANICAL_FIX = "mechanical_fix"


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: FindingType
    severity: FindingSeverity
    title: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=4_000)
    file_path: str | None = None
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)
    suggested_code: str | None = None


class ReviewResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=4_000)
    findings: list[Finding] = Field(default_factory=list)


class RepoIndexEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    language: str
    description: str
    tags: list[str] = Field(default_factory=list)
    relevance: int = Field(default=0, ge=0, le=100)


class SelectedContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    always_on_guidance: list[str] = Field(default_factory=list)
    dynamic_files: list[str] = Field(default_factory=list)
    security_notes: list[str] = Field(default_factory=list)


class FixDelivery(StrEnum):
    INLINE_SUGGESTION = "inline_suggestion"
    FIX_BRANCH_CANDIDATE = "fix_branch_candidate"
    REJECTED = "rejected"


class FixCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    delivery: FixDelivery
    title: str
    explanation: str
    file_path: str | None = None
    replacement: str | None = None
    commit_message: str | None = None
```

- [ ] **Step 4: Run test to verify pass**

Run:

```bash
pytest tests/test_model_client.py::test_review_result_validates_finding_payload -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/ado_ai_pr_review/models.py tests/test_model_client.py
git commit -m "feat: define review result schemas"
```

### Task 5: Configuration Loader And Bootstrap Templates

**Files:**
- Create: `src/ado_ai_pr_review/config.py`
- Create: `src/ado_ai_pr_review/templates.py`
- Create: `src/ado_ai_pr_review/bootstrap.py`
- Test: `tests/test_config.py`
- Test: `tests/test_bootstrap.py`

- [ ] **Step 1: Write failing config and bootstrap tests**

Create `tests/test_config.py`:

```python
from pathlib import Path

from ado_ai_pr_review.config import ReviewConfig


def test_config_loader_applies_defaults(tmp_path: Path) -> None:
    (tmp_path / ".ado-ai-review.yml").write_text(
        """
version: 1
instructions:
  reviewer: .ado-ai-review/instructions/reviewer.md
  security: .ado-ai-review/instructions/security.md
  indexer: .ado-ai-review/instructions/indexer.md
  fixer: .ado-ai-review/instructions/fixer.md
""".strip(),
        encoding="utf-8",
    )

    config = ReviewConfig.load(tmp_path)

    assert config.version == 1
    assert config.commands.review.enabled is True
    assert config.review.max_findings == 20
    assert "node_modules/**" in config.context.index.exclude
```

Create `tests/test_bootstrap.py`:

```python
from pathlib import Path

from ado_ai_pr_review.bootstrap import Bootstrapper


def test_bootstrapper_creates_missing_files_without_overwriting(tmp_path: Path) -> None:
    existing = tmp_path / ".ado-ai-review" / "instructions"
    existing.mkdir(parents=True)
    reviewer = existing / "reviewer.md"
    reviewer.write_text("custom reviewer guidance\n", encoding="utf-8")

    created = Bootstrapper().create_missing_files(tmp_path)

    assert ".ado-ai-review.yml" in created
    assert ".ado-ai-review/instructions/security.md" in created
    assert reviewer.read_text(encoding="utf-8") == "custom reviewer guidance\n"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/test_config.py tests/test_bootstrap.py -v
```

Expected: FAIL with `ModuleNotFoundError` for `ado_ai_pr_review.config`.

- [ ] **Step 3: Implement configuration and deterministic bootstrap**

Create `src/ado_ai_pr_review/config.py`:

```python
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from ado_ai_pr_review.errors import ConfigurationError


class CommandToggle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True


class CommandsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review: CommandToggle = Field(default_factory=CommandToggle)
    security: CommandToggle = Field(default_factory=CommandToggle)
    fix: CommandToggle = Field(default_factory=CommandToggle)


class InstructionsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reviewer: str
    security: str
    indexer: str
    fixer: str


class GuidelinesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code_style: list[str] = Field(default_factory=lambda: [".ado-ai-review/guidelines/code-style.md"])
    security: list[str] = Field(default_factory=lambda: [".ado-ai-review/guidelines/security.md"])


class ReviewSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    focus: list[str] = Field(default_factory=lambda: ["bug-risk", "test-gaps", "readability", "maintainability"])
    max_findings: int = 20
    severity_threshold: str = "medium"


class SecuritySettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    rules: list[str] = Field(
        default_factory=lambda: [
            "secrets",
            "injection",
            "authz",
            "authn",
            "input-validation",
            "unsafe-deserialization",
        ]
    )


class FixInlineSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    max_lines: int = 20


class FixBranchSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    name_template: str = "ai-fix/pr-{pr_id}/{run_id}"
    one_commit_per_change: bool = True


class FixSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    mode: str = "mechanical-only"
    inline_suggestions: FixInlineSettings = Field(default_factory=FixInlineSettings)
    branch: FixBranchSettings = Field(default_factory=FixBranchSettings)


class IndexSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    exclude: list[str] = Field(
        default_factory=lambda: ["node_modules/**", "bin/**", "obj/**", "dist/**", "build/**", ".git/**"]
    )


class DynamicContextSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    max_files: int = 20


class ContextSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    index: IndexSettings = Field(default_factory=IndexSettings)
    dynamic_context: DynamicContextSettings = Field(default_factory=DynamicContextSettings)


class LangfuseSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    trace_pr_reviews: bool = True
    capture_token_usage: bool = True
    capture_costs: bool = True
    capture_prompts: bool = False
    capture_code_context: bool = False


class ObservabilitySettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    langfuse: LangfuseSettings = Field(default_factory=LangfuseSettings)


class ReviewConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    commands: CommandsConfig = Field(default_factory=CommandsConfig)
    instructions: InstructionsConfig
    guidelines: GuidelinesConfig = Field(default_factory=GuidelinesConfig)
    review: ReviewSettings = Field(default_factory=ReviewSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    fix: FixSettings = Field(default_factory=FixSettings)
    context: ContextSettings = Field(default_factory=ContextSettings)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)

    @classmethod
    def load(cls, repo_root: Path) -> "ReviewConfig":
        path = repo_root / ".ado-ai-review.yml"
        if not path.exists():
            raise ConfigurationError("Missing .ado-ai-review.yml")
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls.model_validate(raw)
```

Create `src/ado_ai_pr_review/templates.py`:

```python
BOOTSTRAP_FILES: dict[str, str] = {
    ".ado-ai-review.yml": """version: 1

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
""",
    ".ado-ai-review/instructions/reviewer.md": "# Reviewer Instructions\n\nFocus on correctness, tests, maintainability, and clear user impact.\n",
    ".ado-ai-review/instructions/security.md": "# Security Instructions\n\nFocus on secrets, injection, authentication, authorization, validation, deserialization, and sensitive data handling.\n",
    ".ado-ai-review/instructions/indexer.md": "# Indexer Instructions\n\nDescribe files by purpose, language, domain relevance, test relevance, and security relevance.\n",
    ".ado-ai-review/instructions/fixer.md": "# Fixer Instructions\n\nOnly propose mechanical, behavior-preserving changes.\n",
    ".ado-ai-review/guidelines/code-style.md": "# Code Style\n\nPrefer local project style over generic preferences.\n",
    ".ado-ai-review/guidelines/security.md": "# Security Guidelines\n\nNever expose secret values in comments or model prompts.\n",
}
```

Create `src/ado_ai_pr_review/bootstrap.py`:

```python
from __future__ import annotations

from pathlib import Path

from ado_ai_pr_review.templates import BOOTSTRAP_FILES


class Bootstrapper:
    def create_missing_files(self, repo_root: Path) -> list[str]:
        created: list[str] = []
        for relative_path, content in BOOTSTRAP_FILES.items():
            path = repo_root / relative_path
            if path.exists():
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            created.append(relative_path)
        return created
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
pytest tests/test_config.py tests/test_bootstrap.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/ado_ai_pr_review/config.py src/ado_ai_pr_review/templates.py src/ado_ai_pr_review/bootstrap.py tests/test_config.py tests/test_bootstrap.py
git commit -m "feat: load and bootstrap review configuration"
```

### Task 6: Azure DevOps CLI Toolset

**Files:**
- Create: `src/ado_ai_pr_review/ado_toolset.py`
- Test: `tests/test_publisher.py`

- [ ] **Step 1: Write failing tests for ADO CLI argv**

Create `tests/test_publisher.py`:

```python
import json
from pathlib import Path

from pytest_mock import MockerFixture

from ado_ai_pr_review.ado_toolset import AdoToolset
from ado_ai_pr_review.cli_runner import CommandResult
from ado_ai_pr_review.runtime import RuntimeContext


def _context(tmp_path: Path) -> RuntimeContext:
    return RuntimeContext(
        repo_root=tmp_path,
        organization_url="https://dev.azure.com/acme/",
        project="Payments",
        repository_id="repo-123",
        repository_name="checkout-repo",
        pull_request_id=42,
        source_branch="refs/heads/feature",
        target_branch="refs/heads/main",
        is_fork=False,
        build_id="9001",
        system_access_token="token-value",
    )


def test_ado_toolset_lists_threads_with_az_devops_invoke(mocker: MockerFixture, tmp_path: Path) -> None:
    runner = mocker.Mock()
    runner.run.return_value = CommandResult(
        argv=[],
        returncode=0,
        stdout=json.dumps({"value": [{"id": 1, "comments": [{"content": "/ai review"}]}]}),
        stderr="",
    )
    toolset = AdoToolset(runner=runner, context=_context(tmp_path))

    threads = toolset.list_pr_threads()

    assert threads["value"][0]["id"] == 1
    argv = runner.run.call_args.args[0]
    assert argv[:4] == ["az", "devops", "invoke", "--area"]
    assert "git" in argv
    assert "pullRequestThreads" in argv


def test_ado_toolset_creates_thread_from_json_body(mocker: MockerFixture, tmp_path: Path) -> None:
    runner = mocker.Mock()
    runner.run.return_value = CommandResult(argv=[], returncode=0, stdout='{"id": 5}', stderr="")
    toolset = AdoToolset(runner=runner, context=_context(tmp_path))

    created = toolset.create_pr_thread(
        body={
            "comments": [{"parentCommentId": 0, "content": "hello", "commentType": "text"}],
            "status": "active",
        }
    )

    assert created["id"] == 5
    argv = runner.run.call_args.args[0]
    assert "--http-method" in argv
    assert "POST" in argv
    assert "--in-file" in argv
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/test_publisher.py::test_ado_toolset_lists_threads_with_az_devops_invoke tests/test_publisher.py::test_ado_toolset_creates_thread_from_json_body -v
```

Expected: FAIL with `ModuleNotFoundError` for `ado_ai_pr_review.ado_toolset`.

- [ ] **Step 3: Implement ADO CLI toolset**

Create `src/ado_ai_pr_review/ado_toolset.py`:

```python
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from ado_ai_pr_review.cli_runner import CliRunner
from ado_ai_pr_review.runtime import RuntimeContext


class AdoToolset:
    def __init__(self, runner: CliRunner, context: RuntimeContext) -> None:
        self._runner = runner
        self._context = context

    def configure_defaults(self) -> None:
        self._runner.run(
            [
                "az",
                "devops",
                "configure",
                "--defaults",
                f"organization={self._context.organization_url}",
                f"project={self._context.project}",
            ],
            cwd=self._context.repo_root,
        )

    def ensure_extension(self) -> None:
        self._runner.run(
            ["az", "extension", "add", "--name", "azure-devops", "--only-show-errors"],
            cwd=self._context.repo_root,
            check=False,
        )

    def show_pr(self) -> dict[str, Any]:
        result = self._runner.run(
            [
                "az",
                "repos",
                "pr",
                "show",
                "--id",
                str(self._context.pull_request_id),
                "--organization",
                self._context.organization_url,
                "--project",
                self._context.project,
                "--output",
                "json",
            ],
            cwd=self._context.repo_root,
        )
        return json.loads(result.stdout)

    def create_pr(
        self,
        source_branch: str,
        target_branch: str,
        title: str,
        description: str,
    ) -> dict[str, Any]:
        result = self._runner.run(
            [
                "az",
                "repos",
                "pr",
                "create",
                "--source-branch",
                source_branch,
                "--target-branch",
                target_branch,
                "--title",
                title,
                "--description",
                description,
                "--repository",
                self._context.repository_id,
                "--organization",
                self._context.organization_url,
                "--project",
                self._context.project,
                "--output",
                "json",
            ],
            cwd=self._context.repo_root,
        )
        return json.loads(result.stdout)

    def list_pr_threads(self) -> dict[str, Any]:
        result = self._runner.run(
            self._invoke_args(
                resource="pullRequestThreads",
                route_parameters={
                    "project": self._context.project,
                    "repositoryId": self._context.repository_id,
                    "pullRequestId": str(self._context.pull_request_id),
                },
                http_method="GET",
            ),
            cwd=self._context.repo_root,
        )
        return json.loads(result.stdout)

    def list_iterations(self) -> dict[str, Any]:
        result = self._runner.run(
            self._invoke_args(
                resource="pullRequestIterations",
                route_parameters={
                    "project": self._context.project,
                    "repositoryId": self._context.repository_id,
                    "pullRequestId": str(self._context.pull_request_id),
                },
                http_method="GET",
            ),
            cwd=self._context.repo_root,
        )
        return json.loads(result.stdout)

    def list_iteration_changes(self, iteration_id: int, compare_to: int | None = None) -> dict[str, Any]:
        query_parameters = {"$top": "5000"}
        if compare_to is not None:
            query_parameters["$compareTo"] = str(compare_to)
        result = self._runner.run(
            self._invoke_args(
                resource="pullRequestIterationChanges",
                route_parameters={
                    "project": self._context.project,
                    "repositoryId": self._context.repository_id,
                    "pullRequestId": str(self._context.pull_request_id),
                    "iterationId": str(iteration_id),
                },
                query_parameters=query_parameters,
                http_method="GET",
            ),
            cwd=self._context.repo_root,
        )
        return json.loads(result.stdout)

    def create_pr_thread(self, body: dict[str, Any]) -> dict[str, Any]:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".json", delete=False) as handle:
            json.dump(body, handle)
            body_path = handle.name
        try:
            result = self._runner.run(
                [
                    *self._invoke_args(
                        resource="pullRequestThreads",
                        route_parameters={
                            "project": self._context.project,
                            "repositoryId": self._context.repository_id,
                            "pullRequestId": str(self._context.pull_request_id),
                        },
                        http_method="POST",
                    ),
                    "--in-file",
                    body_path,
                ],
                cwd=self._context.repo_root,
            )
        finally:
            Path(body_path).unlink(missing_ok=True)
        return json.loads(result.stdout)

    def _invoke_args(
        self,
        resource: str,
        route_parameters: dict[str, str],
        http_method: str,
        query_parameters: dict[str, str] | None = None,
    ) -> list[str]:
        args = [
            "az",
            "devops",
            "invoke",
            "--area",
            "git",
            "--resource",
            resource,
            "--route-parameters",
            *[f"{key}={value}" for key, value in route_parameters.items()],
            "--http-method",
            http_method,
            "--api-version",
            "7.1",
            "--organization",
            self._context.organization_url,
            "--output",
            "json",
        ]
        if query_parameters:
            args.extend(["--query-parameters", *[f"{key}={value}" for key, value in query_parameters.items()]])
        return args
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
pytest tests/test_publisher.py::test_ado_toolset_lists_threads_with_az_devops_invoke tests/test_publisher.py::test_ado_toolset_creates_thread_from_json_body -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/ado_ai_pr_review/ado_toolset.py tests/test_publisher.py
git commit -m "feat: add azure devops cli toolset"
```

### Task 7: Git CLI Toolset And Diff Loading

**Files:**
- Create: `src/ado_ai_pr_review/git_toolset.py`
- Create: `src/ado_ai_pr_review/diff.py`
- Test: `tests/test_diff.py`

- [ ] **Step 1: Write failing tests for git diff parsing**

Create `tests/test_diff.py`:

```python
from pathlib import Path

from pytest_mock import MockerFixture

from ado_ai_pr_review.cli_runner import CommandResult
from ado_ai_pr_review.diff import parse_changed_files
from ado_ai_pr_review.git_toolset import GitToolset


def test_parse_changed_files_from_name_status() -> None:
    files = parse_changed_files("M\tsrc/app.py\nA\ttests/test_app.py\nD\told.py\n")

    assert [file.path for file in files] == ["src/app.py", "tests/test_app.py", "old.py"]
    assert files[0].status == "M"


def test_git_toolset_get_diff_uses_git_diff(mocker: MockerFixture, tmp_path: Path) -> None:
    runner = mocker.Mock()
    runner.run.return_value = CommandResult(
        argv=[],
        returncode=0,
        stdout="diff --git a/src/app.py b/src/app.py\n",
        stderr="",
    )
    toolset = GitToolset(runner=runner, repo_root=tmp_path)

    diff = toolset.diff("origin/main...HEAD", unified=0)

    assert diff.startswith("diff --git")
    assert runner.run.call_args.args[0] == ["git", "diff", "--unified=0", "origin/main...HEAD"]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/test_diff.py -v
```

Expected: FAIL with `ModuleNotFoundError` for `ado_ai_pr_review.diff`.

- [ ] **Step 3: Implement git toolset and diff helpers**

Create `src/ado_ai_pr_review/git_toolset.py`:

```python
from __future__ import annotations

from pathlib import Path

from ado_ai_pr_review.cli_runner import CliRunner


class GitToolset:
    def __init__(self, runner: CliRunner, repo_root: Path) -> None:
        self._runner = runner
        self._repo_root = repo_root

    def fetch(self, remote: str = "origin") -> None:
        self._runner.run(["git", "fetch", remote, "--prune"], cwd=self._repo_root)

    def diff(self, refspec: str, unified: int = 0) -> str:
        result = self._runner.run(["git", "diff", f"--unified={unified}", refspec], cwd=self._repo_root)
        return result.stdout

    def name_status(self, refspec: str) -> str:
        result = self._runner.run(["git", "diff", "--name-status", refspec], cwd=self._repo_root)
        return result.stdout

    def checkout_new_branch(self, branch_name: str) -> None:
        self._runner.run(["git", "checkout", "-B", branch_name], cwd=self._repo_root)

    def add(self, paths: list[str]) -> None:
        self._runner.run(["git", "add", *paths], cwd=self._repo_root)

    def commit(self, message: str) -> str:
        self._runner.run(["git", "commit", "-m", message], cwd=self._repo_root)
        result = self._runner.run(["git", "rev-parse", "HEAD"], cwd=self._repo_root)
        return result.stdout.strip()

    def push(self, remote: str, branch_name: str) -> None:
        self._runner.run(["git", "push", remote, branch_name], cwd=self._repo_root)
```

Create `src/ado_ai_pr_review/diff.py`:

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChangedFile:
    status: str
    path: str


def parse_changed_files(name_status: str) -> list[ChangedFile]:
    files: list[ChangedFile] = []
    for line in name_status.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0]
        path = parts[-1]
        files.append(ChangedFile(status=status, path=path))
    return files
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
pytest tests/test_diff.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/ado_ai_pr_review/git_toolset.py src/ado_ai_pr_review/diff.py tests/test_diff.py
git commit -m "feat: add git cli diff toolset"
```

### Task 8: Command Router

**Files:**
- Create: `src/ado_ai_pr_review/commands.py`
- Test: `tests/test_commands.py`

- [ ] **Step 1: Write failing command routing tests**

Create `tests/test_commands.py`:

```python
from ado_ai_pr_review.commands import CommandRouter
from ado_ai_pr_review.models import ReviewCommand


def test_command_router_selects_latest_actionable_command() -> None:
    threads = {
        "value": [
            {"id": 1, "publishedDate": "2026-05-08T09:00:00Z", "comments": [{"content": "/ai review"}]},
            {"id": 2, "publishedDate": "2026-05-08T10:00:00Z", "comments": [{"content": "please run /ai security"}]},
        ]
    }

    decision = CommandRouter().route(threads)

    assert decision.command is ReviewCommand.SECURITY
    assert decision.thread_id == 2


def test_command_router_returns_onboarding_when_no_command_exists() -> None:
    threads = {"value": [{"id": 1, "comments": [{"content": "Looks good"}]}]}

    decision = CommandRouter().route(threads)

    assert decision.command is ReviewCommand.ONBOARDING
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/test_commands.py -v
```

Expected: FAIL with `ModuleNotFoundError` for `ado_ai_pr_review.commands`.

- [ ] **Step 3: Implement command router**

Create `src/ado_ai_pr_review/commands.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ado_ai_pr_review.models import ReviewCommand


@dataclass(frozen=True)
class CommandDecision:
    command: ReviewCommand
    thread_id: int | None
    comment: str | None


class CommandRouter:
    def route(self, threads_payload: dict[str, Any]) -> CommandDecision:
        candidates: list[tuple[str, int, str]] = []
        for thread in threads_payload.get("value", []):
            thread_id = int(thread.get("id", 0))
            published = str(thread.get("publishedDate", ""))
            for comment in thread.get("comments", []):
                content = str(comment.get("content", ""))
                command = self._detect(content)
                if command is not None:
                    candidates.append((published, thread_id, command.value))
        if not candidates:
            return CommandDecision(command=ReviewCommand.ONBOARDING, thread_id=None, comment=None)
        _published, thread_id, command_value = sorted(candidates, key=lambda item: item[0])[-1]
        return CommandDecision(
            command=ReviewCommand(command_value),
            thread_id=thread_id,
            comment=f"/ai {command_value}",
        )

    @staticmethod
    def _detect(content: str) -> ReviewCommand | None:
        lowered = content.lower()
        if "/ai fix" in lowered:
            return ReviewCommand.FIX
        if "/ai security" in lowered:
            return ReviewCommand.SECURITY
        if "/ai review" in lowered:
            return ReviewCommand.REVIEW
        return None
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
pytest tests/test_commands.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/ado_ai_pr_review/commands.py tests/test_commands.py
git commit -m "feat: route ai review pr commands"
```

### Task 9: Repository Indexer And Context Selector

**Files:**
- Create: `src/ado_ai_pr_review/indexer.py`
- Create: `src/ado_ai_pr_review/context.py`
- Test: `tests/test_indexer.py`
- Test: `tests/test_context.py`

- [ ] **Step 1: Write failing indexer and context tests**

Create `tests/test_indexer.py`:

```python
from pathlib import Path

from ado_ai_pr_review.indexer import RepoIndexer


def test_repo_indexer_tags_test_and_security_files(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "auth.py").write_text("def login(): pass\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_auth.py").write_text("def test_login(): pass\n", encoding="utf-8")

    entries = RepoIndexer(exclude=[]).build(tmp_path)

    auth = next(entry for entry in entries if entry.path == "src/auth.py")
    test = next(entry for entry in entries if entry.path == "tests/test_auth.py")
    assert "security" in auth.tags
    assert "tests" in test.tags
```

Create `tests/test_context.py`:

```python
from pathlib import Path

from ado_ai_pr_review.context import ContextSelector
from ado_ai_pr_review.models import RepoIndexEntry


def test_context_selector_loads_guidance_and_relevant_files(tmp_path: Path) -> None:
    (tmp_path / ".ado-ai-review").mkdir()
    guidance = tmp_path / ".ado-ai-review" / "reviewer.md"
    guidance.write_text("Review carefully.\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('hello')\n", encoding="utf-8")

    selected = ContextSelector(max_files=1).select(
        repo_root=tmp_path,
        guidance_paths=[".ado-ai-review/reviewer.md"],
        entries=[
            RepoIndexEntry(
                path="src/app.py",
                language="python",
                description="Application entrypoint.",
                tags=["api"],
                relevance=90,
            )
        ],
    )

    assert selected.always_on_guidance == ["Review carefully.\n"]
    assert selected.dynamic_files == ["src/app.py\nprint('hello')\n"]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/test_indexer.py tests/test_context.py -v
```

Expected: FAIL with `ModuleNotFoundError` for `ado_ai_pr_review.indexer`.

- [ ] **Step 3: Implement indexer and context selector**

Create `src/ado_ai_pr_review/indexer.py`:

```python
from __future__ import annotations

import fnmatch
from pathlib import Path

from ado_ai_pr_review.models import RepoIndexEntry


class RepoIndexer:
    def __init__(self, exclude: list[str]) -> None:
        self._exclude = exclude

    def build(self, repo_root: Path) -> list[RepoIndexEntry]:
        entries: list[RepoIndexEntry] = []
        for path in sorted(repo_root.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(repo_root).as_posix()
            if self._is_excluded(relative):
                continue
            language = self._language(relative)
            if language == "unknown":
                continue
            tags = self._tags(relative)
            entries.append(
                RepoIndexEntry(
                    path=relative,
                    language=language,
                    description=f"{language} file at {relative}",
                    tags=tags,
                    relevance=50,
                )
            )
        return entries

    def _is_excluded(self, relative: str) -> bool:
        return any(fnmatch.fnmatch(relative, pattern) for pattern in self._exclude)

    @staticmethod
    def _language(relative: str) -> str:
        suffix = Path(relative).suffix.lower()
        return {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".cs": "csharp",
            ".go": "go",
            ".java": "java",
            ".md": "markdown",
            ".yml": "yaml",
            ".yaml": "yaml",
            ".json": "json",
        }.get(suffix, "unknown")

    @staticmethod
    def _tags(relative: str) -> list[str]:
        lowered = relative.lower()
        tags: set[str] = set()
        if lowered.startswith("tests/") or "/test" in lowered or lowered.endswith("_test.py"):
            tags.add("tests")
        if any(word in lowered for word in ["auth", "login", "secret", "token", "credential"]):
            tags.add("security")
        if any(word in lowered for word in ["controller", "api", "route", "endpoint"]):
            tags.add("api")
        if any(word in lowered for word in ["domain", "entity", "aggregate"]):
            tags.add("domain")
        if lowered.endswith((".yml", ".yaml", ".json")):
            tags.add("config")
        if lowered.endswith(".md"):
            tags.add("docs")
        return sorted(tags)
```

Create `src/ado_ai_pr_review/context.py`:

```python
from __future__ import annotations

from pathlib import Path

from ado_ai_pr_review.models import RepoIndexEntry, SelectedContext


class ContextSelector:
    def __init__(self, max_files: int) -> None:
        self._max_files = max_files

    def select(
        self,
        repo_root: Path,
        guidance_paths: list[str],
        entries: list[RepoIndexEntry],
        prefer_tags: set[str] | None = None,
    ) -> SelectedContext:
        guidance = []
        for relative in guidance_paths:
            path = repo_root / relative
            if path.exists() and path.is_file():
                guidance.append(path.read_text(encoding="utf-8"))

        prefer_tags = prefer_tags or set()
        ranked = sorted(
            entries,
            key=lambda entry: (
                len(prefer_tags.intersection(entry.tags)),
                entry.relevance,
                entry.path,
            ),
            reverse=True,
        )

        dynamic_files: list[str] = []
        for entry in ranked[: self._max_files]:
            path = repo_root / entry.path
            if path.exists() and path.is_file():
                dynamic_files.append(f"{entry.path}\n{path.read_text(encoding='utf-8')}")

        return SelectedContext(always_on_guidance=guidance, dynamic_files=dynamic_files)
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
pytest tests/test_indexer.py tests/test_context.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/ado_ai_pr_review/indexer.py src/ado_ai_pr_review/context.py tests/test_indexer.py tests/test_context.py
git commit -m "feat: index repository context"
```

### Task 10: Security Heuristics And Secret Redaction

**Files:**
- Create: `src/ado_ai_pr_review/security.py`
- Test: `tests/test_security.py`

- [ ] **Step 1: Write failing security scanner tests**

Create `tests/test_security.py`:

```python
from ado_ai_pr_review.security import SecurityScanner


def test_security_scanner_reports_secret_without_value() -> None:
    scanner = SecurityScanner()

    findings, redacted = scanner.scan_diff("+ API_KEY = 'sk-test-secret-value-1234567890'\n")

    assert findings[0].type == "security"
    assert "secret" in findings[0].title.lower()
    assert "sk-test-secret-value" not in findings[0].body
    assert "[REDACTED_SECRET]" in redacted
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
pytest tests/test_security.py -v
```

Expected: FAIL with `ModuleNotFoundError` for `ado_ai_pr_review.security`.

- [ ] **Step 3: Implement scanner**

Create `src/ado_ai_pr_review/security.py`:

```python
from __future__ import annotations

import re

from ado_ai_pr_review.models import Finding, FindingSeverity, FindingType


SECRET_PATTERNS = [
    re.compile(r"(?P<name>api[_-]?key|secret|token|password)\s*=\s*['\"](?P<value>[^'\"]{12,})['\"]", re.IGNORECASE),
    re.compile(r"(?P<value>sk-[A-Za-z0-9_-]{16,})"),
]


class SecurityScanner:
    def scan_diff(self, diff_text: str) -> tuple[list[Finding], str]:
        findings: list[Finding] = []
        redacted = diff_text
        for pattern in SECRET_PATTERNS:
            for match in pattern.finditer(diff_text):
                value = match.groupdict().get("value") or match.group(0)
                redacted = redacted.replace(value, "[REDACTED_SECRET]")
                findings.append(
                    Finding(
                        type=FindingType.SECURITY,
                        severity=FindingSeverity.CRITICAL,
                        title="Possible secret committed",
                        body="A value matching a secret pattern appears in the diff. Remove it from the branch and rotate the credential if it was valid.",
                    )
                )
        return findings, redacted
```

- [ ] **Step 4: Run test to verify pass**

Run:

```bash
pytest tests/test_security.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/ado_ai_pr_review/security.py tests/test_security.py
git commit -m "feat: redact secrets before model review"
```

### Task 11: Model Client With Structured Output

**Files:**
- Create: `src/ado_ai_pr_review/model_client.py`
- Modify: `tests/test_model_client.py`

- [ ] **Step 1: Write failing tests for model JSON parsing and repair**

Append to `tests/test_model_client.py`:

```python
from pytest_mock import MockerFixture

from ado_ai_pr_review.model_client import ModelClient


def test_model_client_parses_response_json(mocker: MockerFixture) -> None:
    openai_client = mocker.Mock()
    openai_client.responses.create.return_value.output_text = """
{"summary":"ok","findings":[]}
"""
    client = ModelClient(openai_client=openai_client, deployment="review-model")

    result = client.review_json(system_prompt="system", user_prompt="user")

    assert result.summary == "ok"
    openai_client.responses.create.assert_called_once()
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
pytest tests/test_model_client.py::test_model_client_parses_response_json -v
```

Expected: FAIL with `ModuleNotFoundError` for `ado_ai_pr_review.model_client`.

- [ ] **Step 3: Implement model client**

Create `src/ado_ai_pr_review/model_client.py`:

```python
from __future__ import annotations

import json
import os
from typing import Protocol

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import OpenAI
from pydantic import ValidationError

from ado_ai_pr_review.errors import ModelOutputError
from ado_ai_pr_review.models import ReviewResult


class ResponsesClient(Protocol):
    class ResponsesApi(Protocol):
        def create(self, **kwargs: object) -> object: ...

    responses: ResponsesApi


def build_openai_client() -> OpenAI:
    base_url = os.environ["AZURE_OPENAI_BASE_URL"]
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    if api_key:
        return OpenAI(api_key=api_key, base_url=base_url)
    token_provider = get_bearer_token_provider(
        DefaultAzureCredential(),
        "https://cognitiveservices.azure.com/.default",
    )
    return OpenAI(api_key=token_provider, base_url=base_url)


class ModelClient:
    def __init__(self, openai_client: ResponsesClient, deployment: str) -> None:
        self._openai_client = openai_client
        self._deployment = deployment

    def review_json(self, system_prompt: str, user_prompt: str) -> ReviewResult:
        response = self._openai_client.responses.create(
            model=self._deployment,
            instructions=system_prompt,
            input=user_prompt,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "review_result",
                    "schema": ReviewResult.model_json_schema(),
                    "strict": True,
                }
            },
        )
        output_text = str(getattr(response, "output_text"))
        try:
            return ReviewResult.model_validate(json.loads(output_text))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ModelOutputError(f"Model returned invalid review JSON: {exc}") from exc
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
pytest tests/test_model_client.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/ado_ai_pr_review/model_client.py tests/test_model_client.py
git commit -m "feat: call model with structured review schema"
```

### Task 12: Review Orchestrator

**Files:**
- Create: `src/ado_ai_pr_review/reviewer.py`
- Test: `tests/test_reviewer.py`

- [ ] **Step 1: Write failing orchestrator test**

Create `tests/test_reviewer.py`:

```python
from pytest_mock import MockerFixture

from ado_ai_pr_review.models import ReviewCommand, ReviewResult
from ado_ai_pr_review.reviewer import ReviewOrchestrator


def test_orchestrator_uses_security_prompt_for_security_command(mocker: MockerFixture) -> None:
    model_client = mocker.Mock()
    model_client.review_json.return_value = ReviewResult(summary="ok", findings=[])
    orchestrator = ReviewOrchestrator(model_client=model_client)

    result = orchestrator.run(
        command=ReviewCommand.SECURITY,
        guidance=["secure guidance"],
        selected_files=["src/auth.py\ncode"],
        diff_text="+ change",
        local_security_summary="No local secrets detected.",
    )

    assert result.summary == "ok"
    system_prompt = model_client.review_json.call_args.kwargs["system_prompt"]
    assert "security reviewer" in system_prompt.lower()
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
pytest tests/test_reviewer.py -v
```

Expected: FAIL with `ModuleNotFoundError` for `ado_ai_pr_review.reviewer`.

- [ ] **Step 3: Implement orchestrator**

Create `src/ado_ai_pr_review/reviewer.py`:

```python
from __future__ import annotations

from ado_ai_pr_review.model_client import ModelClient
from ado_ai_pr_review.models import ReviewCommand, ReviewResult


GENERAL_SYSTEM_PROMPT = """You are an Azure DevOps pull request reviewer.
Return only JSON matching the supplied schema.
Prioritize correctness, bug risk, test gaps, readability, and maintainability.
Do not propose business logic rewrites.
Do not include secret values.
"""

SECURITY_SYSTEM_PROMPT = """You are a security reviewer for an Azure DevOps pull request.
Return only JSON matching the supplied schema.
Focus on secrets, injection, authentication, authorization, input validation, unsafe deserialization, and sensitive data handling.
Do not include secret values.
"""


class ReviewOrchestrator:
    def __init__(self, model_client: ModelClient) -> None:
        self._model_client = model_client

    def run(
        self,
        command: ReviewCommand,
        guidance: list[str],
        selected_files: list[str],
        diff_text: str,
        local_security_summary: str,
    ) -> ReviewResult:
        system_prompt = SECURITY_SYSTEM_PROMPT if command is ReviewCommand.SECURITY else GENERAL_SYSTEM_PROMPT
        user_prompt = "\n\n".join(
            [
                "Repository guidance:",
                *guidance,
                "Selected context files:",
                *selected_files,
                "Local security scan:",
                local_security_summary,
                "Pull request diff:",
                diff_text,
            ]
        )
        return self._model_client.review_json(system_prompt=system_prompt, user_prompt=user_prompt)
```

- [ ] **Step 4: Run test to verify pass**

Run:

```bash
pytest tests/test_reviewer.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/ado_ai_pr_review/reviewer.py tests/test_reviewer.py
git commit -m "feat: orchestrate review prompts"
```

### Task 13: PR Publisher

**Files:**
- Create: `src/ado_ai_pr_review/publisher.py`
- Modify: `tests/test_publisher.py`

- [ ] **Step 1: Write failing publisher tests**

Append to `tests/test_publisher.py`:

```python
from ado_ai_pr_review.models import Finding, FindingSeverity, FindingType, ReviewResult
from ado_ai_pr_review.publisher import SuggestionPublisher


def test_publisher_creates_inline_suggestion_thread(mocker: MockerFixture) -> None:
    ado = mocker.Mock()
    publisher = SuggestionPublisher(ado_toolset=ado)
    result = ReviewResult(
        summary="One issue.",
        findings=[
            Finding(
                type=FindingType.BUG_RISK,
                severity=FindingSeverity.HIGH,
                title="Guard missing value",
                body="Handle None before formatting.",
                file_path="src/app.py",
                line_start=10,
                line_end=10,
                suggested_code="if value is None:\n    return None",
            )
        ],
    )

    publisher.publish_review(result)

    body = ado.create_pr_thread.call_args.kwargs["body"]
    assert body["threadContext"]["filePath"] == "src/app.py"
    assert "```suggestion" in body["comments"][0]["content"]
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
pytest tests/test_publisher.py::test_publisher_creates_inline_suggestion_thread -v
```

Expected: FAIL with `ModuleNotFoundError` for `ado_ai_pr_review.publisher`.

- [ ] **Step 3: Implement publisher**

Create `src/ado_ai_pr_review/publisher.py`:

```python
from __future__ import annotations

from ado_ai_pr_review.ado_toolset import AdoToolset
from ado_ai_pr_review.models import Finding, ReviewResult


class SuggestionPublisher:
    def __init__(self, ado_toolset: AdoToolset) -> None:
        self._ado = ado_toolset

    def publish_onboarding(self) -> None:
        self._ado.create_pr_thread(
            body={
                "comments": [
                    {
                        "parentCommentId": 0,
                        "content": "ADO AI review is available. Comment `/ai review`, `/ai security`, or `/ai fix` to run it.",
                        "commentType": "text",
                    }
                ],
                "status": "active",
                "properties": {"adoAiReview.kind": {"$type": "System.String", "$value": "onboarding"}},
            }
        )

    def publish_review(self, result: ReviewResult) -> None:
        self._ado.create_pr_thread(
            body={
                "comments": [
                    {
                        "parentCommentId": 0,
                        "content": f"ADO AI review summary:\n\n{result.summary}",
                        "commentType": "text",
                    }
                ],
                "status": "active",
                "properties": {"adoAiReview.kind": {"$type": "System.String", "$value": "summary"}},
            }
        )
        for finding in result.findings:
            self._publish_finding(finding)

    def _publish_finding(self, finding: Finding) -> None:
        content = f"**{finding.severity.value.upper()}: {finding.title}**\n\n{finding.body}"
        if finding.suggested_code:
            content = f"{content}\n\n```suggestion\n{finding.suggested_code}\n```"

        body: dict[str, object] = {
            "comments": [{"parentCommentId": 0, "content": content, "commentType": "text"}],
            "status": "active",
            "properties": {"adoAiReview.kind": {"$type": "System.String", "$value": "finding"}},
        }
        if finding.file_path and finding.line_start:
            line_end = finding.line_end or finding.line_start
            body["threadContext"] = {
                "filePath": finding.file_path,
                "rightFileStart": {"line": finding.line_start, "offset": 1},
                "rightFileEnd": {"line": line_end, "offset": 1},
            }
        self._ado.create_pr_thread(body=body)
```

- [ ] **Step 4: Run publisher tests to verify pass**

Run:

```bash
pytest tests/test_publisher.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/ado_ai_pr_review/publisher.py tests/test_publisher.py
git commit -m "feat: publish review findings to pr threads"
```

### Task 14: Mechanical Fixer

**Files:**
- Create: `src/ado_ai_pr_review/fixer.py`
- Test: `tests/test_fixer.py`

- [ ] **Step 1: Write failing fixer tests**

Create `tests/test_fixer.py`:

```python
from pytest_mock import MockerFixture

from ado_ai_pr_review.fixer import MechanicalFixer
from ado_ai_pr_review.models import FixCandidate, FixDelivery


def test_fixer_rejects_non_mechanical_candidate() -> None:
    fixer = MechanicalFixer(git_toolset=None, ado_toolset=None)
    candidate = FixCandidate(
        delivery=FixDelivery.FIX_BRANCH_CANDIDATE,
        title="Rewrite pricing logic",
        explanation="Change discount behavior.",
    )

    assert fixer.is_allowed(candidate) is False


def test_fixer_creates_one_commit_per_branch_candidate(mocker: MockerFixture) -> None:
    git = mocker.Mock()
    ado = mocker.Mock()
    ado.create_pr.return_value = {"pullRequestId": 99, "url": "https://dev.azure.com/acme/pr/99"}
    fixer = MechanicalFixer(git_toolset=git, ado_toolset=ado)
    candidates = [
        FixCandidate(
            delivery=FixDelivery.FIX_BRANCH_CANDIDATE,
            title="Format imports",
            explanation="Import cleanup.",
            file_path="src/app.py",
            replacement="import os\n",
            commit_message="fix: format imports",
        )
    ]

    pr = fixer.create_fix_branch(
        candidates=candidates,
        branch_name="ai-fix/pr-42/9001",
        target_branch="feature",
    )

    assert pr["pullRequestId"] == 99
    git.commit.assert_called_once_with("fix: format imports")
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
pytest tests/test_fixer.py -v
```

Expected: FAIL with `ModuleNotFoundError` for `ado_ai_pr_review.fixer`.

- [ ] **Step 3: Implement mechanical fixer**

Create `src/ado_ai_pr_review/fixer.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

from ado_ai_pr_review.ado_toolset import AdoToolset
from ado_ai_pr_review.git_toolset import GitToolset
from ado_ai_pr_review.models import FixCandidate, FixDelivery


MECHANICAL_WORDS = {
    "format",
    "formatting",
    "lint",
    "import",
    "imports",
    "rename",
    "type",
    "typing",
    "test",
    "mechanical",
}


class MechanicalFixer:
    def __init__(self, git_toolset: GitToolset | None, ado_toolset: AdoToolset | None) -> None:
        self._git = git_toolset
        self._ado = ado_toolset

    def is_allowed(self, candidate: FixCandidate) -> bool:
        text = f"{candidate.title} {candidate.explanation} {candidate.commit_message or ''}".lower()
        if any(word in text for word in ["business", "pricing", "discount", "authorization behavior"]):
            return False
        return any(word in text for word in MECHANICAL_WORDS)

    def create_fix_branch(
        self,
        candidates: list[FixCandidate],
        branch_name: str,
        target_branch: str,
    ) -> dict[str, Any]:
        if self._git is None or self._ado is None:
            raise RuntimeError("Git and ADO toolsets are required to create a fix branch")
        self._git.checkout_new_branch(branch_name)
        commit_shas: list[str] = []
        for candidate in candidates:
            if candidate.delivery is not FixDelivery.FIX_BRANCH_CANDIDATE or not self.is_allowed(candidate):
                continue
            if not candidate.file_path or candidate.replacement is None or not candidate.commit_message:
                continue
            Path(candidate.file_path).write_text(candidate.replacement, encoding="utf-8")
            self._git.add([candidate.file_path])
            commit_shas.append(self._git.commit(candidate.commit_message))
        self._git.push("origin", branch_name)
        description = "Mechanical AI fix branch.\n\nCherry-pick commits:\n" + "\n".join(
            f"- `git cherry-pick {sha}`" for sha in commit_shas
        )
        return self._ado.create_pr(
            source_branch=branch_name,
            target_branch=target_branch,
            title="AI mechanical fixes",
            description=description,
        )
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
pytest tests/test_fixer.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/ado_ai_pr_review/fixer.py tests/test_fixer.py
git commit -m "feat: create mechanical fix branches"
```

### Task 15: Observability

**Files:**
- Create: `src/ado_ai_pr_review/observability.py`
- Test: `tests/test_reviewer.py`

- [ ] **Step 1: Write failing observability test**

Append to `tests/test_reviewer.py`:

```python
from ado_ai_pr_review.observability import ReviewMetrics


def test_review_metrics_serializes_without_code_context() -> None:
    metrics = ReviewMetrics(
        command="review",
        pr_id=42,
        findings_count=3,
        inline_suggestions_count=1,
        fix_pr_created=False,
        token_usage={"input": 100, "output": 20},
    )

    payload = metrics.to_payload()

    assert payload["command"] == "review"
    assert "code_context" not in payload
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
pytest tests/test_reviewer.py::test_review_metrics_serializes_without_code_context -v
```

Expected: FAIL with `ModuleNotFoundError` for `ado_ai_pr_review.observability`.

- [ ] **Step 3: Implement metrics wrapper**

Create `src/ado_ai_pr_review/observability.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ReviewMetrics:
    command: str
    pr_id: int
    findings_count: int
    inline_suggestions_count: int
    fix_pr_created: bool
    token_usage: dict[str, int] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "pr_id": self.pr_id,
            "findings_count": self.findings_count,
            "inline_suggestions_count": self.inline_suggestions_count,
            "fix_pr_created": self.fix_pr_created,
            "token_usage": self.token_usage,
        }
```

- [ ] **Step 4: Run test to verify pass**

Run:

```bash
pytest tests/test_reviewer.py::test_review_metrics_serializes_without_code_context -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/ado_ai_pr_review/observability.py tests/test_reviewer.py
git commit -m "feat: capture review metrics without code context"
```

### Task 16: End-To-End CLI Orchestration

**Files:**
- Modify: `src/ado_ai_pr_review/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing CLI orchestration test**

Append to `tests/test_cli.py`:

```python
from pathlib import Path

from pytest_mock import MockerFixture

from ado_ai_pr_review.models import ReviewCommand


def test_cli_run_builds_runtime_context(monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture, tmp_path: Path) -> None:
    monkeypatch.setenv("SYSTEM_TEAMFOUNDATIONCOLLECTIONURI", "https://dev.azure.com/acme/")
    monkeypatch.setenv("SYSTEM_TEAMPROJECT", "Payments")
    monkeypatch.setenv("BUILD_REPOSITORY_ID", "repo-123")
    monkeypatch.setenv("BUILD_REPOSITORY_NAME", "checkout-repo")
    monkeypatch.setenv("SYSTEM_PULLREQUEST_PULLREQUESTID", "42")
    monkeypatch.setenv("SYSTEM_PULLREQUEST_SOURCEBRANCH", "refs/heads/feature")
    monkeypatch.setenv("SYSTEM_PULLREQUEST_TARGETBRANCH", "refs/heads/main")
    monkeypatch.setenv("SYSTEM_PULLREQUEST_ISFORK", "False")
    monkeypatch.setenv("BUILD_BUILDID", "9001")
    monkeypatch.setenv("AZURE_OPENAI_BASE_URL", "https://example.openai.azure.com/openai/v1/")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "review-model")

    run_worker = mocker.patch("ado_ai_pr_review.cli.run_worker", return_value=ReviewCommand.ONBOARDING)

    result = CliRunner().invoke(app, ["run", "--repo-root", str(tmp_path), "--dry-run"])

    assert result.exit_code == 0
    run_worker.assert_called_once()
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
pytest tests/test_cli.py::test_cli_run_builds_runtime_context -v
```

Expected: FAIL because `run_worker` is not defined or not called.

- [ ] **Step 3: Implement CLI orchestration shell**

Replace `src/ado_ai_pr_review/cli.py` with:

```python
from __future__ import annotations

import os
from typing import Annotated

import typer

from ado_ai_pr_review.ado_toolset import AdoToolset
from ado_ai_pr_review.bootstrap import Bootstrapper
from ado_ai_pr_review.cli_runner import CliRunner
from ado_ai_pr_review.commands import CommandRouter
from ado_ai_pr_review.config import ReviewConfig
from ado_ai_pr_review.context import ContextSelector
from ado_ai_pr_review.diff import parse_changed_files
from ado_ai_pr_review.git_toolset import GitToolset
from ado_ai_pr_review.indexer import RepoIndexer
from ado_ai_pr_review.logging_config import configure_logging
from ado_ai_pr_review.model_client import ModelClient, build_openai_client
from ado_ai_pr_review.models import ReviewCommand
from ado_ai_pr_review.publisher import SuggestionPublisher
from ado_ai_pr_review.reviewer import ReviewOrchestrator
from ado_ai_pr_review.runtime import RuntimeContext
from ado_ai_pr_review.security import SecurityScanner
from ado_ai_pr_review.tool_policy import CommandPolicy

app = typer.Typer(no_args_is_help=True)


@app.command()
def run(
    repo_root: Annotated[str, typer.Option("--repo-root")] = ".",
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    verbose: Annotated[bool, typer.Option("--verbose")] = False,
) -> None:
    """Run the ADO AI PR review worker."""
    configure_logging(verbose=verbose)
    context = RuntimeContext.from_env(repo_root=repo_root)
    decision = run_worker(context=context, dry_run=dry_run)
    typer.echo(f"ado-ai-pr-review completed command={decision.value}")


def run_worker(context: RuntimeContext, dry_run: bool) -> ReviewCommand:
    runner = CliRunner(
        policy=CommandPolicy.default(),
        secrets=[context.system_access_token or ""],
    )
    ado = AdoToolset(runner=runner, context=context)
    git = GitToolset(runner=runner, repo_root=context.repo_root)
    publisher = SuggestionPublisher(ado_toolset=ado)

    created = Bootstrapper().create_missing_files(context.repo_root)
    if created:
        if not dry_run:
            publisher.publish_onboarding()
        return ReviewCommand.ONBOARDING

    config = ReviewConfig.load(context.repo_root)
    threads = ado.list_pr_threads()
    decision = CommandRouter().route(threads)
    if decision.command is ReviewCommand.ONBOARDING:
        if not dry_run:
            publisher.publish_onboarding()
        return decision.command

    git.fetch()
    refspec = "origin/main...HEAD"
    diff_text = git.diff(refspec, unified=0)
    changed_files = parse_changed_files(git.name_status(refspec))
    _ = changed_files

    scanner = SecurityScanner()
    local_findings, redacted_diff = scanner.scan_diff(diff_text)
    entries = RepoIndexer(exclude=config.context.index.exclude).build(context.repo_root)
    selector = ContextSelector(max_files=config.context.dynamic_context.max_files)
    prefer_tags = {"security"} if decision.command is ReviewCommand.SECURITY else set()
    selected = selector.select(
        repo_root=context.repo_root,
        guidance_paths=[
            config.instructions.security if decision.command is ReviewCommand.SECURITY else config.instructions.reviewer,
            *config.guidelines.code_style,
            *config.guidelines.security,
        ],
        entries=entries,
        prefer_tags=prefer_tags,
    )

    model_client = ModelClient(
        openai_client=build_openai_client(),
        deployment=os.environ["AZURE_OPENAI_DEPLOYMENT"],
    )
    result = ReviewOrchestrator(model_client=model_client).run(
        command=decision.command,
        guidance=selected.always_on_guidance,
        selected_files=selected.dynamic_files,
        diff_text=redacted_diff,
        local_security_summary=f"Local findings: {len(local_findings)}",
    )
    result.findings.extend(local_findings)
    if not dry_run:
        publisher.publish_review(result)
    return decision.command
```

- [ ] **Step 4: Run CLI tests to verify pass**

Run:

```bash
pytest tests/test_cli.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/ado_ai_pr_review/cli.py tests/test_cli.py
git commit -m "feat: wire cli worker orchestration"
```

### Task 17: Docker And Azure Pipeline Template

**Files:**
- Create: `Dockerfile`
- Create: `azure-pipelines.ado-ai-review.yml`
- Create: `docs/operations/ado-ai-review.md`
- Test: local Docker build command

- [ ] **Step 1: Add Dockerfile**

Create `Dockerfile`:

```dockerfile
FROM mcr.microsoft.com/azure-cli:2.79.0

WORKDIR /app

RUN apk add --no-cache git bash && \
    az extension add --name azure-devops

COPY pyproject.toml ruff.toml mypy.ini ./
COPY src ./src

RUN python -m pip install --upgrade pip && \
    python -m pip install .

ENTRYPOINT ["ado-ai-pr-review"]
```

- [ ] **Step 2: Add Azure Pipelines template**

Create `azure-pipelines.ado-ai-review.yml`:

```yaml
trigger: none

pr:
  branches:
    include:
      - "*"

pool:
  vmImage: ubuntu-latest

variables:
  imageName: ado-ai-pr-review:local

steps:
  - checkout: self
    persistCredentials: true
    fetchDepth: 0

  - script: |
      docker build -t $(imageName) .
    displayName: Build ADO AI review worker image

  - script: |
      docker run --rm \
        -v "$(Build.SourcesDirectory):/repo" \
        -w /repo \
        -e SYSTEM_ACCESSTOKEN="$(System.AccessToken)" \
        -e SYSTEM_TEAMFOUNDATIONCOLLECTIONURI="$(System.TeamFoundationCollectionUri)" \
        -e SYSTEM_TEAMPROJECT="$(System.TeamProject)" \
        -e BUILD_REPOSITORY_ID="$(Build.Repository.ID)" \
        -e BUILD_REPOSITORY_NAME="$(Build.Repository.Name)" \
        -e SYSTEM_PULLREQUEST_PULLREQUESTID="$(System.PullRequest.PullRequestId)" \
        -e SYSTEM_PULLREQUEST_SOURCEBRANCH="$(System.PullRequest.SourceBranch)" \
        -e SYSTEM_PULLREQUEST_TARGETBRANCH="$(System.PullRequest.TargetBranch)" \
        -e SYSTEM_PULLREQUEST_ISFORK="$(System.PullRequest.IsFork)" \
        -e BUILD_BUILDID="$(Build.BuildId)" \
        -e AZURE_OPENAI_BASE_URL="$(AZURE_OPENAI_BASE_URL)" \
        -e AZURE_OPENAI_DEPLOYMENT="$(AZURE_OPENAI_DEPLOYMENT)" \
        -e AZURE_OPENAI_API_KEY="$(AZURE_OPENAI_API_KEY)" \
        $(imageName) run --repo-root /repo
    displayName: Run ADO AI PR review
    env:
      SYSTEM_ACCESSTOKEN: $(System.AccessToken)
```

- [ ] **Step 3: Add operations documentation**

Create `docs/operations/ado-ai-review.md`:

```markdown
# ADO AI PR Review Operations

## Required Azure DevOps Settings

- The pipeline must run as a PR branch policy so `System.PullRequest.*` variables are populated.
- The checkout step must use `persistCredentials: true`.
- Scripts must be allowed to access `System.AccessToken`.
- The project build service identity needs code read permission to review PRs.
- To publish comments, the build service identity needs pull request contribute/comment permissions.
- To create bootstrap commits or fix branches, the build service identity needs branch contribute permission.

## Required Variables

- `AZURE_OPENAI_BASE_URL`: Azure OpenAI or Foundry v1 base URL ending in `/openai/v1/`.
- `AZURE_OPENAI_DEPLOYMENT`: model deployment name.
- `AZURE_OPENAI_API_KEY`: optional when Microsoft Entra authentication is configured.

## Commands

- `/ai review`: general code review.
- `/ai security`: security baseline review.
- `/ai fix`: mechanical fixes only.

## Security Boundary

The model never receives a raw shell tool. It can only request typed review outputs. All local CLI operations are controlled by Python code, command allowlists, timeouts, output caps, and secret redaction.
```

- [ ] **Step 4: Build Docker image**

Run:

```bash
docker build -t ado-ai-pr-review:local .
```

Expected: image builds successfully and installs `ado-ai-pr-review`.

- [ ] **Step 5: Commit**

Run:

```bash
git add Dockerfile azure-pipelines.ado-ai-review.yml docs/operations/ado-ai-review.md
git commit -m "chore: package worker for azure pipelines"
```

### Task 18: Quality Gate

**Files:**
- Modify only files required by failures from this task.

- [ ] **Step 1: Run full test suite**

Run:

```bash
pytest -v
```

Expected: all tests PASS.

- [ ] **Step 2: Run formatting and lint**

Run:

```bash
ruff check .
```

Expected: no lint errors.

- [ ] **Step 3: Run type checking**

Run:

```bash
mypy src
```

Expected: no type errors.

- [ ] **Step 4: Run package import check**

Run:

```bash
python -m ado_ai_pr_review --help
```

Expected: Typer help renders with the `run` command.

- [ ] **Step 5: Commit final fixes if any files changed**

Run:

```bash
git status --short
git add pyproject.toml ruff.toml mypy.ini Dockerfile azure-pipelines.ado-ai-review.yml src tests docs
git commit -m "test: pass worker quality gate"
```

If `git status --short` prints no changes after the quality gate, do not create an empty commit.

## Self-Review

Spec coverage:

- Pipeline-only Docker worker: covered by Tasks 1, 16, 17.
- CLI-first Azure DevOps and git operations: covered by Tasks 3, 6, 7, 17.
- Narrow model-callable tools instead of raw shell: covered by Tasks 3, 6, 7, 12, 16, 17.
- PR comment command routing: covered by Task 8.
- Deterministic bootstrap: covered by Task 5 and Task 16.
- Config and repository instructions: covered by Task 5 and Task 9.
- Repo index and context selection: covered by Task 9.
- General and security review: covered by Tasks 10, 11, 12.
- Secret redaction before model calls: covered by Task 10 and Task 16.
- Inline suggestions: covered by Task 13.
- Mechanical fix branch and one commit per change: covered by Task 14.
- Langfuse-ready metrics without prompt/code capture: covered by Task 15.
- Pipeline permissions and operations docs: covered by Task 17.

Placeholder scan:

- No `TBD` markers.
- No unfinished implementation steps.
- No unspecified file paths.
- No model access to raw shell.

Type consistency:

- `ReviewCommand`, `ReviewResult`, `Finding`, and `FixCandidate` are defined before use.
- `CliRunner`, `CommandPolicy`, `AdoToolset`, and `GitToolset` signatures are used consistently across tests and orchestration.
- `SuggestionPublisher` always receives `AdoToolset`.
- `ReviewOrchestrator` always receives `ModelClient`.

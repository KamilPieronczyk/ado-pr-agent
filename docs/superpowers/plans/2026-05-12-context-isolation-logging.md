# Context Isolation + Structured Error Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Zbudować twardą izolację request/workspace oraz strukturalne JSON logowanie z korelacją `request_id`, redakcją sekretów i bezpiecznym dostępem do plików w trybach `local` i `webhook`.

**Architecture:** Dodać małe, jednoodpowiedzialne serwisy: `WorkspaceBoundary` do walidacji ścieżek i cwd, `ProcessContext` do per-request env/cwd, `SecretRedactor` do wspólnej redakcji oraz `log_context` do propagacji `request_id` przez `contextvars`. `ContextSelector`, `RepoIndexer`, `CliRunner`, adaptery i `MechanicalFixer` mają korzystać z tych serwisów zamiast lokalnie składać ścieżki i warunki. Pipeline mode jest usuwany w osobnym planie `2026-05-12-ado-auth-pipeline-removal.md`; ten plan nie dodaje żadnego nowego zachowania pipeline.

**Tech Stack:** Python 3.12, dataclasses, pathlib, contextvars, logging stdlib, FastAPI, Typer, pytest, pytest-mock, ruff, mypy.

---

## File Structure

- Create: `src/ado_ai_pr_review/redaction.py` - wspólny `SecretRedactor`.
- Create: `src/ado_ai_pr_review/log_context.py` - `bind_request_context()`, `current_request_id()`, `RequestContextFilter`.
- Create: `src/ado_ai_pr_review/workspace.py` - `WorkspaceBoundary`, `ProcessContext`.
- Create: `src/ado_ai_pr_review/git_clone.py` - wąski serwis klonowania do przydzielonego katalogu.
- Create: `tests/test_redaction.py`, `tests/test_logging_config.py`, `tests/test_workspace.py`.
- Create: `docs/context-isolation-logging.md`.
- Modify: `src/ado_ai_pr_review/errors.py`, `logging_config.py`, `cli_runner.py`, `context.py`, `indexer.py`, `fixer.py`, `adapters/local.py`, `adapters/webhook.py`, `webhook_server.py`, `ports.py`, `engine.py`.
- Modify tests: `tests/test_cli_runner.py`, `tests/test_context.py`, `tests/test_indexer.py`, `tests/test_fixer.py`, `tests/test_local_adapter.py`, `tests/test_webhook_server.py`, `tests/test_webhook_adapter.py`, `tests/test_engine.py`, `tests/test_ports.py`.

## Task 1: Shared Secret Redaction

**Files:**
- Create: `src/ado_ai_pr_review/redaction.py`
- Create: `tests/test_redaction.py`
- Modify: `src/ado_ai_pr_review/cli_runner.py`
- Test: `tests/test_redaction.py`, `tests/test_cli_runner.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_redaction.py`:

```python
from ado_ai_pr_review.redaction import SecretRedactor


def test_secret_redactor_replaces_configured_secret() -> None:
    redactor = SecretRedactor(secrets=["abc123"])

    assert redactor.redact("token=abc123") == "token=[REDACTED]"


def test_secret_redactor_replaces_known_token_patterns() -> None:
    redactor = SecretRedactor()

    text = "openai=sk-abcdefghijklmnopqrstuvwxyz github=ghp_abcdefghijklmnopqrstuvwxyzABCDEFGHIJ"
    redacted = redactor.redact(text)

    assert "sk-" not in redacted
    assert "ghp_" not in redacted
    assert redacted.count("[REDACTED]") == 2


def test_secret_redactor_handles_empty_values() -> None:
    redactor = SecretRedactor(secrets=["", "   ", "real-secret"])

    assert redactor.redact("real-secret visible") == "[REDACTED] visible"
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
.venv/bin/pytest tests/test_redaction.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'ado_ai_pr_review.redaction'`.

- [ ] **Step 3: Implement redaction service**

Create `src/ado_ai_pr_review/redaction.py`:

```python
from __future__ import annotations

import re
from collections.abc import Iterable

_DEFAULT_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{36,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{82}"),
    re.compile(r"DefaultEndpointsProtocol=https;AccountName=[^;]+;AccountKey=[A-Za-z0-9+/=]{40,}"),
    re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----", re.MULTILINE),
)


class SecretRedactor:
    def __init__(self, secrets: Iterable[str] = ()) -> None:
        self._secrets = tuple(secret.strip() for secret in secrets if secret and secret.strip())

    def redact(self, value: object) -> str:
        redacted = "" if value is None else str(value)
        for secret in self._secrets:
            redacted = redacted.replace(secret, "[REDACTED]")
        for pattern in _DEFAULT_PATTERNS:
            redacted = pattern.sub("[REDACTED]", redacted)
        return redacted
```

Update `src/ado_ai_pr_review/cli_runner.py`:

```python
from ado_ai_pr_review.redaction import SecretRedactor
```

Replace `_secrets` storage with:

```python
self._redactor = SecretRedactor(secrets or ())
```

Replace `_cap_and_redact()` with:

```python
def _cap_and_redact(self, output: str) -> str:
    redacted = self._redactor.redact(output)
    return redacted[: self._max_output_chars]
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
.venv/bin/pytest tests/test_redaction.py tests/test_cli_runner.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ado_ai_pr_review/redaction.py src/ado_ai_pr_review/cli_runner.py tests/test_redaction.py tests/test_cli_runner.py
git commit -m "feat: add shared secret redaction"
```

## Task 2: JSON Logs With Request Context

**Files:**
- Create: `src/ado_ai_pr_review/log_context.py`
- Modify: `src/ado_ai_pr_review/logging_config.py`
- Create: `tests/test_logging_config.py`

- [ ] **Step 1: Write failing logging tests**

Create `tests/test_logging_config.py`:

```python
from __future__ import annotations

import json
import logging
from io import StringIO

from ado_ai_pr_review.log_context import bind_request_context
from ado_ai_pr_review.logging_config import configure_logging


def test_configure_logging_emits_json_with_request_id() -> None:
    stream = StringIO()
    configure_logging(verbose=False, stream=stream, secrets=["abc123"], force=True)

    logger = logging.getLogger("ado_ai_pr_review.test")
    with bind_request_context(request_id="req-123"):
        logger.info("processed token abc123", extra={"pr_id": 42})

    payload = json.loads(stream.getvalue())

    assert payload["level"] == "INFO"
    assert payload["logger"] == "ado_ai_pr_review.test"
    assert payload["request_id"] == "req-123"
    assert payload["message"] == "processed token [REDACTED]"
    assert payload["pr_id"] == 42
    assert "abc123" not in stream.getvalue()


def test_configure_logging_includes_exception_type() -> None:
    stream = StringIO()
    configure_logging(verbose=True, stream=stream, force=True)

    logger = logging.getLogger("ado_ai_pr_review.test")
    with bind_request_context(request_id="req-err"):
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            logger.exception("failed")

    payload = json.loads(stream.getvalue())

    assert payload["level"] == "ERROR"
    assert payload["request_id"] == "req-err"
    assert payload["exc_type"] == "RuntimeError"
    assert "traceback" in payload
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
.venv/bin/pytest tests/test_logging_config.py -v
```

Expected: FAIL because `log_context` does not exist and `configure_logging()` has no `stream`, `secrets`, or `force`.

- [ ] **Step 3: Implement request log context**

Create `src/ado_ai_pr_review/log_context.py`:

```python
from __future__ import annotations

import contextlib
import contextvars
import logging
from collections.abc import Iterator

_request_id: contextvars.ContextVar[str] = contextvars.ContextVar("ado_ai_request_id", default="unknown")


def current_request_id() -> str:
    return _request_id.get()


@contextlib.contextmanager
def bind_request_context(request_id: str) -> Iterator[None]:
    token = _request_id.set(request_id or "unknown")
    try:
        yield
    finally:
        _request_id.reset(token)


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = current_request_id()
        return True
```

- [ ] **Step 4: Implement JSON logging**

Replace `src/ado_ai_pr_review/logging_config.py` with a JSON formatter that emits `timestamp`, `level`, `logger`, `message`, `request_id`, selected `extra` fields, `exc_type`, and redacted `traceback`. Use `SecretRedactor` for `record.getMessage()`, string extras, and tracebacks. Preserve this callable signature:

```python
def configure_logging(
    verbose: bool = False,
    *,
    stream: TextIO | None = None,
    secrets: Iterable[str] = (),
    force: bool = False,
) -> None:
    ...
```

Use `root.handlers[:] = [handler]` after optional `root.handlers.clear()` so repeated test setup is deterministic.

- [ ] **Step 5: Run focused tests**

Run:

```bash
.venv/bin/pytest tests/test_logging_config.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/ado_ai_pr_review/log_context.py src/ado_ai_pr_review/logging_config.py tests/test_logging_config.py
git commit -m "feat: emit structured request logs"
```

## Task 3: Workspace Boundary Service

**Files:**
- Create: `src/ado_ai_pr_review/workspace.py`
- Modify: `src/ado_ai_pr_review/errors.py`
- Create: `tests/test_workspace.py`

- [ ] **Step 1: Write failing workspace tests**

Create `tests/test_workspace.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from ado_ai_pr_review.errors import WorkspaceBoundaryError
from ado_ai_pr_review.workspace import ProcessContext, WorkspaceBoundary


def test_workspace_reads_relative_file_inside_root(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('ok')\n", encoding="utf-8")

    workspace = WorkspaceBoundary(tmp_path)

    assert workspace.safe_read_text("src/app.py") == "print('ok')\n"


def test_workspace_rejects_parent_traversal(tmp_path: Path) -> None:
    workspace = WorkspaceBoundary(tmp_path)

    with pytest.raises(WorkspaceBoundaryError, match="outside workspace"):
        workspace.safe_read_text("../other-repo/secret.py")


def test_workspace_rejects_absolute_path_outside_root(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    workspace = WorkspaceBoundary(tmp_path)

    with pytest.raises(WorkspaceBoundaryError, match="outside workspace"):
        workspace.safe_read_text(str(outside))


def test_workspace_rejects_symlink_to_outside_root(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-secret.txt"
    outside.write_text("secret", encoding="utf-8")
    link = tmp_path / "link.txt"
    link.symlink_to(outside)
    workspace = WorkspaceBoundary(tmp_path)

    with pytest.raises(WorkspaceBoundaryError, match="symlink"):
        workspace.safe_read_text("link.txt")


def test_process_context_builds_env_and_validates_cwd(tmp_path: Path) -> None:
    workspace = WorkspaceBoundary(tmp_path)
    process = ProcessContext(workspace=workspace, request_id="req-1", base_env={"PATH": "/bin"})

    env = process.build_env({"CUSTOM": "yes"})

    assert env["PATH"] == "/bin"
    assert env["CUSTOM"] == "yes"
    assert env["ADO_AI_REQUEST_ID"] == "req-1"
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    assert process.require_cwd(tmp_path) == tmp_path.resolve()
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
.venv/bin/pytest tests/test_workspace.py -v
```

Expected: FAIL because `WorkspaceBoundaryError`, `WorkspaceBoundary`, and `ProcessContext` do not exist.

- [ ] **Step 3: Add workspace error**

Modify `src/ado_ai_pr_review/errors.py`:

```python
class WorkspaceBoundaryError(AdoAiReviewError):
    """Raised when a path or process cwd escapes the request workspace."""
```

- [ ] **Step 4: Implement workspace service**

Create `src/ado_ai_pr_review/workspace.py` with:

```python
@dataclass(frozen=True)
class WorkspaceBoundary:
    root: Path

    def safe_read_text(self, relative_path: str, *, max_chars: int | None = None) -> str: ...
    def safe_write_text(self, relative_path: str, content: str) -> Path: ...
    def resolve_existing_file(self, relative_path: str) -> Path: ...
    def resolve_write_path(self, relative_path: str) -> Path: ...
    def require_cwd(self, cwd: Path) -> Path: ...
    def iter_relative_files(self, exclude: list[str]) -> Iterator[Path]: ...
```

Implementation requirements:
- `root` is resolved in `__post_init__`.
- Absolute paths outside `root` raise `WorkspaceBoundaryError`.
- Parent traversal outside `root` raises `WorkspaceBoundaryError`.
- Symlink files are rejected for reads.
- Symlink parents or symlink targets are rejected for writes.
- `iter_relative_files()` skips symlinks and only yields files resolving inside `root`.
- Exclude matching uses posix relative paths and `fnmatch.fnmatch`.

Create `ProcessContext`:

```python
@dataclass(frozen=True)
class ProcessContext:
    workspace: WorkspaceBoundary
    request_id: str
    base_env: Mapping[str, str]

    @classmethod
    def from_current_env(cls, workspace: WorkspaceBoundary, request_id: str) -> ProcessContext: ...
    def require_cwd(self, cwd: Path) -> Path: ...
    def build_env(self, overrides: Mapping[str, str] | None = None) -> dict[str, str]: ...
```

`build_env()` must set `ADO_AI_REQUEST_ID` and default `GIT_TERMINAL_PROMPT=0`.

- [ ] **Step 5: Run focused tests**

Run:

```bash
.venv/bin/pytest tests/test_workspace.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/ado_ai_pr_review/errors.py src/ado_ai_pr_review/workspace.py tests/test_workspace.py
git commit -m "feat: add workspace boundary service"
```

## Task 4: Per-Request CWD and Env in CliRunner

**Files:**
- Modify: `src/ado_ai_pr_review/cli_runner.py`
- Modify: `tests/test_cli_runner.py`

- [ ] **Step 1: Add failing CliRunner tests**

Append to `tests/test_cli_runner.py`:

```python
from ado_ai_pr_review.workspace import ProcessContext, WorkspaceBoundary


def test_cli_runner_uses_process_context_env_and_cwd(mocker: MockerFixture, tmp_path: Path) -> None:
    completed = subprocess.CompletedProcess(args=["git", "status"], returncode=0, stdout="", stderr="")
    run = mocker.patch("subprocess.run", return_value=completed)
    process = ProcessContext(
        workspace=WorkspaceBoundary(tmp_path),
        request_id="req-99",
        base_env={"PATH": "/bin"},
    )
    runner = CliRunner(policy=CommandPolicy.default(), process_context=process)

    runner.run(["git", "status"], cwd=tmp_path, env={"CUSTOM": "yes"})

    kwargs = run.call_args.kwargs
    assert kwargs["cwd"] == tmp_path.resolve()
    assert kwargs["env"]["PATH"] == "/bin"
    assert kwargs["env"]["CUSTOM"] == "yes"
    assert kwargs["env"]["ADO_AI_REQUEST_ID"] == "req-99"


def test_cli_runner_rejects_cwd_outside_process_workspace(mocker: MockerFixture, tmp_path: Path) -> None:
    run = mocker.patch("subprocess.run")
    process = ProcessContext(workspace=WorkspaceBoundary(tmp_path), request_id="req-99", base_env={})
    runner = CliRunner(policy=CommandPolicy.default(), process_context=process)

    with pytest.raises(CommandExecutionError, match="cwd outside workspace"):
        runner.run(["git", "status"], cwd=tmp_path.parent)

    run.assert_not_called()
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
.venv/bin/pytest tests/test_cli_runner.py::test_cli_runner_uses_process_context_env_and_cwd tests/test_cli_runner.py::test_cli_runner_rejects_cwd_outside_process_workspace -v
```

Expected: FAIL because `CliRunner.__init__()` has no `process_context`.

- [ ] **Step 3: Update CliRunner**

Add constructor parameter:

```python
process_context: ProcessContext | None = None
```

Before `subprocess.run`, compute:

```python
try:
    effective_cwd = self._process_context.require_cwd(cwd) if self._process_context else cwd
    effective_env = self._process_context.build_env(env) if self._process_context else env
except Exception as exc:
    raise CommandExecutionError(self._redactor.redact(str(exc))) from exc
```

Pass `effective_cwd` and `effective_env` to `subprocess.run`.

- [ ] **Step 4: Run CliRunner tests**

Run:

```bash
.venv/bin/pytest tests/test_cli_runner.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ado_ai_pr_review/cli_runner.py tests/test_cli_runner.py
git commit -m "feat: constrain command execution context"
```

## Task 5: Safe Context Reads and Indexing

**Files:**
- Modify: `src/ado_ai_pr_review/context.py`
- Modify: `src/ado_ai_pr_review/indexer.py`
- Modify: `tests/test_context.py`
- Modify: `tests/test_indexer.py`

- [ ] **Step 1: Add failing context and indexer tests**

Append to `tests/test_context.py`:

```python
def test_context_selector_rejects_guidance_traversal(tmp_path: Path) -> None:
    outside = tmp_path.parent / "guidance.md"
    outside.write_text("outside\n", encoding="utf-8")

    selected = ContextSelector(max_files=1).select(
        repo_root=tmp_path,
        guidance_paths=["../guidance.md"],
        entries=[],
    )

    assert selected.always_on_guidance == []
    assert selected.dynamic_files == []


def test_context_selector_skips_symlinked_dynamic_file(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.py"
    outside.write_text("print('secret')\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "outside.py").symlink_to(outside)

    selected = ContextSelector(max_files=1).select(
        repo_root=tmp_path,
        guidance_paths=[],
        entries=[RepoIndexEntry(path="src/outside.py", language="python", description="Symlink.", tags=[], relevance=90)],
    )

    assert selected.dynamic_files == []
```

Append to `tests/test_indexer.py`:

```python
def test_repo_indexer_does_not_follow_symlink_outside_root(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.py"
    outside.write_text("print('secret')\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "outside.py").symlink_to(outside)

    entries = RepoIndexer(exclude=[]).build(tmp_path)

    assert [entry.path for entry in entries] == []
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
.venv/bin/pytest tests/test_context.py tests/test_indexer.py -v
```

Expected: FAIL because unsafe paths are still read.

- [ ] **Step 3: Update ContextSelector**

Use `WorkspaceBoundary(repo_root)` in `select()`. Guidance and dynamic files must be read through `workspace.safe_read_text()`. Catch `WorkspaceBoundaryError` and `FileNotFoundError`, log a structured warning/debug, and skip the file.

- [ ] **Step 4: Update RepoIndexer**

Use:

```python
workspace = WorkspaceBoundary(repo_root)
for relative_path in workspace.iter_relative_files(exclude=self._exclude):
    relative = relative_path.as_posix()
    ...
```

Remove or stop using direct `repo_root.rglob("*")`.

- [ ] **Step 5: Run focused tests**

Run:

```bash
.venv/bin/pytest tests/test_context.py tests/test_indexer.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/ado_ai_pr_review/context.py src/ado_ai_pr_review/indexer.py tests/test_context.py tests/test_indexer.py
git commit -m "feat: harden context file access"
```

## Task 6: Safe Fix Writes

**Files:**
- Modify: `src/ado_ai_pr_review/fixer.py`
- Modify: `src/ado_ai_pr_review/adapters/local.py`
- Modify: `tests/test_fixer.py`
- Modify: `tests/test_local_adapter.py`

- [ ] **Step 1: Add failing fixer traversal tests**

Append to `tests/test_fixer.py`:

```python
def test_fixer_rejects_candidate_path_outside_repo(mocker: MockerFixture, tmp_path: Path) -> None:
    git = mocker.Mock()
    ado = mocker.Mock()
    fixer = MechanicalFixer(git_toolset=git, ado_toolset=ado, repo_root=tmp_path)
    candidates = [
        FixCandidate(
            delivery=FixDelivery.FIX_BRANCH_CANDIDATE,
            title="Format imports",
            explanation="Import cleanup.",
            file_path="../other-repo/app.py",
            replacement="import os\n",
            commit_message="fix: format imports",
        )
    ]

    with pytest.raises(RuntimeError, match="No mechanical candidates"):
        fixer.create_fix_branch(candidates, branch_name="ai-fix/pr-42/1", target_branch="main")

    git.add.assert_not_called()


def test_fixer_rejects_symlink_write_target(mocker: MockerFixture, tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.py"
    outside.write_text("print('outside')\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").symlink_to(outside)
    git = mocker.Mock()
    ado = mocker.Mock()
    fixer = MechanicalFixer(git_toolset=git, ado_toolset=ado, repo_root=tmp_path)
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

    with pytest.raises(RuntimeError, match="No mechanical candidates"):
        fixer.create_fix_branch(candidates, branch_name="ai-fix/pr-42/1", target_branch="main")

    assert outside.read_text(encoding="utf-8") == "print('outside')\n"
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
.venv/bin/pytest tests/test_fixer.py -v
```

Expected: FAIL because writes are direct.

- [ ] **Step 3: Update MechanicalFixer**

Create `self._workspace = WorkspaceBoundary(repo_root) if repo_root is not None else None`. Before every write, require a workspace and call:

```python
self._workspace.safe_write_text(candidate.file_path, candidate.replacement)
```

Catch `WorkspaceBoundaryError`, log `skipping unsafe fix candidate`, and continue. If all candidates are skipped, raise the existing `RuntimeError("No mechanical candidates...")`.

- [ ] **Step 4: Update LocalCliAdapter fix writes**

Use the same `WorkspaceBoundary.safe_write_text()` path in local fix mode. If unsafe candidates are skipped and no commit is created, print `No mechanical fix candidates.` and return `False`.

- [ ] **Step 5: Run focused tests**

Run:

```bash
.venv/bin/pytest tests/test_fixer.py tests/test_local_adapter.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/ado_ai_pr_review/fixer.py src/ado_ai_pr_review/adapters/local.py tests/test_fixer.py tests/test_local_adapter.py
git commit -m "feat: constrain fix writes to workspace"
```

## Task 7: Webhook Request Isolation and Safe Clone Service

**Files:**
- Create: `src/ado_ai_pr_review/git_clone.py`
- Modify: `src/ado_ai_pr_review/adapters/webhook.py`
- Modify: `src/ado_ai_pr_review/webhook_server.py`
- Modify: `src/ado_ai_pr_review/ports.py`
- Modify: `tests/test_webhook_server.py`
- Modify: `tests/test_webhook_adapter.py`
- Modify: `tests/test_ports.py`

- [ ] **Step 1: Add failing request id tests**

Append to `tests/test_ports.py`:

```python
def test_pr_context_carries_request_id() -> None:
    ctx = PRContext(
        pr_id=42,
        source_branch="refs/heads/feature",
        target_branch="refs/heads/main",
        is_fork=False,
        build_id="webhook",
        request_id="req-42",
    )

    assert ctx.request_id == "req-42"
```

Append to `tests/test_webhook_server.py`:

```python
def test_webhook_returns_and_passes_request_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADO_AUTH_TOKEN", "fake-token")
    monkeypatch.setenv("AZURE_OPENAI_BASE_URL", "https://example.com/")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "model")

    with patch("ado_ai_pr_review.webhook_server._process_sync") as process:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/webhook/ado", json=_PR_CREATED_PAYLOAD, headers={"X-Request-ID": "external-req-1"})

    assert response.status_code == 200
    assert response.json() == {"status": "accepted", "request_id": "external-req-1"}
    assert process.call_args.args[2] == "external-req-1"
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
.venv/bin/pytest tests/test_ports.py::test_pr_context_carries_request_id tests/test_webhook_server.py::test_webhook_returns_and_passes_request_id -v
```

Expected: FAIL because request id is not carried.

- [ ] **Step 3: Add request id fields**

Modify `PRContext` by adding final default field:

```python
request_id: str = "unknown"
```

All existing constructor calls must keep working.

- [ ] **Step 4: Implement clone service**

Create `src/ado_ai_pr_review/git_clone.py`:

```python
from __future__ import annotations

from pathlib import Path

from ado_ai_pr_review.cli_runner import CliRunner
from ado_ai_pr_review.errors import WorkspaceBoundaryError


class GitCloneService:
    def __init__(self, runner: CliRunner) -> None:
        self._runner = runner

    def clone_branch(self, remote_url: str, branch: str, destination: Path) -> None:
        destination_parent = destination.parent.resolve()
        destination_resolved = destination.resolve()
        try:
            destination_resolved.relative_to(destination_parent)
        except ValueError as exc:
            raise WorkspaceBoundaryError(f"Clone destination outside temp parent: {destination}") from exc
        if destination.exists() and any(destination.iterdir()):
            raise WorkspaceBoundaryError(f"Clone destination is not empty: {destination}")
        self._runner.run(
            ["git", "clone", "--depth", "50", "--branch", branch, remote_url, str(destination_resolved)],
            cwd=destination_parent,
        )
```

- [ ] **Step 5: Update webhook adapter/server**

`AdoWebhookAdapter.__init__()` accepts `request_id: str`, stores `WorkspaceBoundary(temp_dir)`, passes `ProcessContext` into post-clone `CliRunner`, creates `PRContext(..., request_id=self._request_id)`, and uses `GitCloneService` for clone setup.

`webhook_server.py` must:
- read `X-Request-ID` or `X-Correlation-ID`,
- generate `ado-pr-<pr_id>-<random>` when absent,
- bind log context during accept and processing,
- return `{"status": "accepted", "request_id": request_id}`,
- redact validation error body excerpts with `SecretRedactor`.

- [ ] **Step 6: Update response-shape tests**

Existing webhook tests that assert `{"status": "accepted"}` should assert:

```python
body = response.json()
assert body["status"] == "accepted"
assert body["request_id"]
```

- [ ] **Step 7: Run focused tests**

Run:

```bash
.venv/bin/pytest tests/test_ports.py tests/test_webhook_server.py tests/test_webhook_adapter.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/ado_ai_pr_review/ports.py src/ado_ai_pr_review/git_clone.py src/ado_ai_pr_review/adapters/webhook.py src/ado_ai_pr_review/webhook_server.py tests/test_ports.py tests/test_webhook_server.py tests/test_webhook_adapter.py
git commit -m "feat: isolate webhook request workspaces"
```

## Task 8: Engine and Local Adapter Request Context

**Files:**
- Modify: `src/ado_ai_pr_review/adapters/local.py`
- Modify: `src/ado_ai_pr_review/engine.py`
- Modify: `src/ado_ai_pr_review/cli.py`
- Modify: `tests/test_local_adapter.py`
- Modify: `tests/test_engine.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_local_adapter.py`:

```python
def test_local_adapter_sets_request_id_on_pr_context(tmp_path: Path, mocker: MockerFixture) -> None:
    runner = mocker.Mock()
    runner.run.return_value.stdout = "feature/local\n"
    git = mocker.Mock()
    git.diff.return_value = "diff --git a/src/app.py b/src/app.py\n"
    adapter = LocalCliAdapter(
        repo_root=tmp_path,
        command=ReviewCommand.REVIEW,
        _runner=runner,
        _git=git,
        request_id="local-req-1",
    )

    request = adapter.load_request()

    assert request.pr_context.request_id == "local-req-1"
```

- [ ] **Step 2: Run failing test**

Run:

```bash
.venv/bin/pytest tests/test_local_adapter.py::test_local_adapter_sets_request_id_on_pr_context -v
```

Expected: FAIL because local adapter does not accept request id.

- [ ] **Step 3: Update local adapter and CLI**

`LocalCliAdapter` accepts `request_id: str | None = None`, generates `local-<token>` when absent, creates `WorkspaceBoundary(repo_root)`, builds `ProcessContext`, and passes `request_id` into `PRContext`.

`cli.py` should generate the request id in `local()`:

```python
request_id = f"local-{secrets.token_hex(8)}"
adapter = LocalCliAdapter(repo_root=root, command=command, target_branch=target_branch, request_id=request_id)
```

- [ ] **Step 4: Update engine structured metrics**

Wrap loaded request processing in:

```python
with bind_request_context(request.pr_context.request_id):
    return self._run_loaded_request(request, config)
```

Log review metrics with `logger.info("review metrics", extra={...})` instead of interpolating `metrics.to_payload()` into the message.

- [ ] **Step 5: Run focused tests**

Run:

```bash
.venv/bin/pytest tests/test_engine.py tests/test_local_adapter.py tests/test_cli.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/ado_ai_pr_review/adapters/local.py src/ado_ai_pr_review/engine.py src/ado_ai_pr_review/cli.py tests/test_local_adapter.py tests/test_engine.py tests/test_cli.py
git commit -m "feat: correlate engine logs with request context"
```

## Task 9: Documentation

**Files:**
- Create: `docs/context-isolation-logging.md`
- Modify: `README.md`

- [ ] **Step 1: Write documentation page**

Create `docs/context-isolation-logging.md` explaining:
- request ids in local and webhook modes,
- `X-Request-ID` and `X-Correlation-ID`,
- workspace boundary rejection rules,
- JSON log fields,
- redaction behavior,
- how to filter Container Apps logs by request id.

Include this exact response example:

```json
{"status": "accepted", "request_id": "ado-pr-42-0123456789abcdef"}
```

- [ ] **Step 2: Update README**

Under webhook docs, add that responses include `request_id` and callers may pass `X-Request-ID` or `X-Correlation-ID`.

Under security boundary, add:

```markdown
Repository file reads, context indexing, command cwd values, and mechanical fix writes are constrained to the request workspace. The worker rejects parent traversal, absolute paths outside the workspace, and symlink targets that could escape into another cloned repository. Runtime logs are emitted as JSON and include `request_id`; configured secrets and known token formats are redacted before output.
```

- [ ] **Step 3: Run docs-adjacent check**

Run:

```bash
.venv/bin/pytest tests/test_webhook_server.py::test_webhook_returns_accepted_immediately -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add docs/context-isolation-logging.md README.md
git commit -m "docs: describe context isolation and logging"
```

## Task 10: Full Verification

**Files:**
- Verify all modified source, tests, and docs.

- [ ] **Step 1: Run full tests**

Run:

```bash
.venv/bin/pytest -v
```

Expected: PASS.

- [ ] **Step 2: Run ruff**

Run:

```bash
.venv/bin/ruff check .
```

Expected: PASS.

- [ ] **Step 3: Run mypy**

Run:

```bash
.venv/bin/mypy src tests
```

Expected: PASS.

- [ ] **Step 4: Inspect unsafe direct file access**

Run:

```bash
rg -n "read_text\\(|write_text\\(|rglob\\(|subprocess\\.run\\(" src/ado_ai_pr_review tests
```

Expected production hits are limited to:
- `workspace.py` for safe read/write/iteration,
- `cli_runner.py` for subprocess execution,
- bootstrap/config/template code intentionally managing repo config files,
- tests.

If `context.py`, `indexer.py`, `fixer.py`, `adapters/local.py`, or `adapters/webhook.py` still directly call `read_text()`, `write_text()`, or `rglob()` for repository content, route that call through `WorkspaceBoundary`.

- [ ] **Step 5: Run redaction-focused tests**

Run:

```bash
.venv/bin/pytest tests/test_redaction.py tests/test_logging_config.py tests/test_cli_runner.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit verification fixes only if needed**

```bash
git status --short
git add -A
git commit -m "test: verify context isolation and structured logging"
```

Skip the commit if `git status --short` is empty.

## Self-Review Checklist

- [ ] Context isolation is covered by `WorkspaceBoundary`, `ProcessContext`, `CliRunner`, `ContextSelector`, `RepoIndexer`, `MechanicalFixer`, local adapter, and webhook adapter.
- [ ] Request/workspace boundaries are explicit: per-request `request_id`, per-request process env, validated cwd, safe file reads/writes.
- [ ] Another cloned repo cannot be read through `..`, absolute paths, or symlink traversal.
- [ ] Webhook clone setup is isolated; post-clone operations run inside `WorkspaceBoundary`.
- [ ] Logs are JSON, include `request_id`, and redact configured secrets plus known token patterns.
- [ ] Validation errors and exceptions do not emit raw body secrets.
- [ ] Tests include negative cases for traversal, symlinks, cwd escape, redaction, and request log correlation.
- [ ] Documentation explains operational behavior and correlation.

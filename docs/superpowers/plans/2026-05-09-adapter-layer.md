# Adapter Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the pipeline-only worker into a tri-mode application (pipeline, local CLI, webhook) by introducing `PlatformAdapter`/`LLMPort` ports, extracting `ReviewEngine`, and shipping a FastAPI webhook server for Container Apps deployment.

**Architecture:** A `PlatformAdapter` protocol hides all platform I/O (diff acquisition, command detection, publishing). A `LLMPort` protocol abstracts the AI backend. `ReviewEngine` holds all orchestration and depends only on these two protocols. Three concrete adapters implement `PlatformAdapter`; two implement `LLMPort`.

**Tech Stack:** Python 3.12, Typer, Pydantic v2, FastAPI, Uvicorn, PyYAML, OpenAI Python SDK, azure-identity, pytest, ruff, mypy.

---

> **Spec amendment — `ReviewRequest.local_findings`:** The spec states that `SecurityScanner.scan_diff()` runs in `load_request()` and that `ReviewRequest.diff_text` is already redacted. The engine also needs the local findings list to extend `result.findings` and compute the security summary. `ReviewRequest` therefore gains a `local_findings: tuple[Finding, ...]` field. This is a clarification, not a design change.

---

## File Map

```
src/ado_ai_pr_review/
    ports.py                        NEW — PlatformAdapter, LLMPort, PRContext, ReviewRequest
    engine.py                       NEW — ReviewEngine (orchestration extracted from cli.py)
    adapters/
        __init__.py                 NEW — empty
        pipeline.py                 NEW — AdoPipelineAdapter
        local.py                    NEW — LocalCliAdapter
        webhook.py                  NEW — AdoWebhookPayload + AdoWebhookAdapter
    llm/
        __init__.py                 NEW — empty
        azure_openai.py             NEW — ModelClient (moved from model_client.py)
        github_copilot.py           NEW — GitHubCopilotClient
    webhook_server.py               NEW — FastAPI app + /webhook/ado + /health
    model_client.py                 CHANGED — becomes re-export shim (keeps test_model_client.py working)
    reviewer.py                     CHANGED — type annotation: ModelClient → LLMPort
    cli.py                          CHANGED — adds pipeline/local/serve subcommands, removes run_worker
    tool_policy.py                  CHANGED — adds git rev-parse --abbrev-ref HEAD + gh auth token
    pyproject.toml                  CHANGED — adds fastapi, uvicorn, httpx (test)

tests/
    test_ports.py                   NEW
    test_engine.py                  NEW
    test_local_adapter.py           NEW
    test_webhook_adapter.py         NEW
    test_webhook_server.py          NEW
    test_github_copilot.py          NEW
    test_cli.py                     CHANGED — updates to subcommand structure
    test_model_client.py            UNCHANGED — shim keeps it working
```

---

## Task 1: Ports Module

**Files:**
- Create: `src/ado_ai_pr_review/ports.py`
- Create: `tests/test_ports.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_ports.py
from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from ado_ai_pr_review.models import ReviewCommand
from ado_ai_pr_review.ports import PRContext, ReviewRequest


def test_pr_context_is_frozen() -> None:
    ctx = PRContext(pr_id=1, source_branch="feat", target_branch="main", is_fork=False, build_id="42")
    with pytest.raises(FrozenInstanceError):
        ctx.pr_id = 2  # type: ignore[misc]


def test_pr_context_allows_none_pr_id() -> None:
    ctx = PRContext(pr_id=None, source_branch="feat", target_branch="main", is_fork=False, build_id="local")
    assert ctx.pr_id is None


def test_review_request_is_frozen() -> None:
    ctx = PRContext(pr_id=1, source_branch="feat", target_branch="main", is_fork=False, build_id="42")
    req = ReviewRequest(
        repo_root=Path("/tmp"),
        diff_text="some diff",
        local_findings=(),
        command=ReviewCommand.REVIEW,
        pr_context=ctx,
    )
    with pytest.raises(FrozenInstanceError):
        req.diff_text = "other"  # type: ignore[misc]


def test_review_request_stores_local_findings() -> None:
    from ado_ai_pr_review.models import Finding, FindingSeverity, FindingType
    finding = Finding(
        type=FindingType.SECURITY,
        severity=FindingSeverity.CRITICAL,
        title="Secret",
        body="Remove it.",
    )
    ctx = PRContext(pr_id=1, source_branch="feat", target_branch="main", is_fork=False, build_id="1")
    req = ReviewRequest(
        repo_root=Path("/tmp"),
        diff_text="",
        local_findings=(finding,),
        command=ReviewCommand.SECURITY,
        pr_context=ctx,
    )
    assert len(req.local_findings) == 1
    assert req.local_findings[0].title == "Secret"
```

- [ ] **Step 2: Run to verify failure**

```bash
.venv/bin/pytest tests/test_ports.py -v
```
Expected: `ImportError: cannot import name 'PRContext' from 'ado_ai_pr_review.ports'`

- [ ] **Step 3: Create `ports.py`**

```python
# src/ado_ai_pr_review/ports.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ado_ai_pr_review.models import Finding, FixCandidate, ReviewCommand, ReviewResult


@dataclass(frozen=True)
class PRContext:
    pr_id: int | None
    source_branch: str
    target_branch: str
    is_fork: bool
    build_id: str


@dataclass(frozen=True)
class ReviewRequest:
    repo_root: Path
    diff_text: str                       # already redacted by SecurityScanner
    local_findings: tuple[Finding, ...]  # raw findings from SecurityScanner
    command: ReviewCommand
    pr_context: PRContext


class PlatformAdapter(Protocol):
    def load_request(self) -> ReviewRequest: ...
    def publish_onboarding(self) -> None: ...
    def publish_review(self, result: ReviewResult) -> None: ...
    def publish_error(self, exc: BaseException) -> None: ...
    def create_fix_branch(
        self,
        candidates: list[FixCandidate],
        branch_name: str,
        target_branch: str,
    ) -> bool: ...


class LLMPort(Protocol):
    def review_json(self, system_prompt: str, user_prompt: str) -> ReviewResult: ...
```

- [ ] **Step 4: Run tests to verify passage**

```bash
.venv/bin/pytest tests/test_ports.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Check types and lint**

```bash
.venv/bin/mypy src tests && .venv/bin/ruff check .
```
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add src/ado_ai_pr_review/ports.py tests/test_ports.py
git commit -m "feat: add PlatformAdapter and LLMPort port definitions"
```

---

## Task 2: Move ModelClient to `llm/`

**Files:**
- Create: `src/ado_ai_pr_review/llm/__init__.py`
- Create: `src/ado_ai_pr_review/llm/azure_openai.py`
- Create: `src/ado_ai_pr_review/adapters/__init__.py`
- Modify: `src/ado_ai_pr_review/model_client.py` (re-export shim)
- Modify: `src/ado_ai_pr_review/reviewer.py` (type annotation update)

- [ ] **Step 1: Create `llm/__init__.py` and `adapters/__init__.py`**

Both empty:
```python
# src/ado_ai_pr_review/llm/__init__.py
```
```python
# src/ado_ai_pr_review/adapters/__init__.py
```

- [ ] **Step 2: Create `llm/azure_openai.py`**

Copy the content of `model_client.py` verbatim:

```python
# src/ado_ai_pr_review/llm/azure_openai.py
from __future__ import annotations

import json
import os
from typing import Protocol

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import OpenAI
from pydantic import ValidationError

from ado_ai_pr_review.errors import ModelOutputError
from ado_ai_pr_review.models import ReviewResult


class ResponseObject(Protocol):
    output_text: str


class ResponsesClient(Protocol):
    class ResponsesApi(Protocol):
        def create(self, **kwargs: object) -> ResponseObject: ...

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
    return OpenAI(api_key=token_provider(), base_url=base_url)


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
        output_text = str(response.output_text)
        try:
            return ReviewResult.model_validate(json.loads(output_text))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ModelOutputError(f"Model returned invalid review JSON: {exc}") from exc
```

- [ ] **Step 3: Turn `model_client.py` into a re-export shim**

Replace the entire contents of `src/ado_ai_pr_review/model_client.py`:

```python
# src/ado_ai_pr_review/model_client.py
# Re-export shim — keeps existing imports working.
from ado_ai_pr_review.llm.azure_openai import (
    ModelClient,
    ResponseObject,
    ResponsesClient,
    build_openai_client,
)

__all__ = ["ModelClient", "ResponseObject", "ResponsesClient", "build_openai_client"]
```

- [ ] **Step 4: Update `reviewer.py` type annotation**

In `src/ado_ai_pr_review/reviewer.py`, replace:

```python
from ado_ai_pr_review.model_client import ModelClient
```

with:

```python
from ado_ai_pr_review.ports import LLMPort
```

And change the `__init__` signature:

```python
class ReviewOrchestrator:
    def __init__(self, model_client: LLMPort) -> None:
        self._model_client = model_client
```

- [ ] **Step 5: Verify existing tests still pass**

```bash
.venv/bin/pytest -v && .venv/bin/mypy src tests && .venv/bin/ruff check .
```
Expected: all existing tests pass, no type or lint errors.

- [ ] **Step 6: Commit**

```bash
git add src/ado_ai_pr_review/llm/ src/ado_ai_pr_review/adapters/__init__.py \
    src/ado_ai_pr_review/model_client.py src/ado_ai_pr_review/reviewer.py
git commit -m "refactor: move ModelClient to llm/azure_openai, add re-export shim"
```

---

## Task 3: AdoPipelineAdapter

**Files:**
- Create: `src/ado_ai_pr_review/adapters/pipeline.py`

No new unit tests — the logic is identical to `cli.py:run_worker()`, which is covered by existing `test_cli.py` tests.

- [ ] **Step 1: Create `adapters/pipeline.py`**

```python
# src/ado_ai_pr_review/adapters/pipeline.py
from __future__ import annotations

import contextlib
import logging
from pathlib import Path
from typing import Any, cast

from ado_ai_pr_review.ado_toolset import AdoToolset
from ado_ai_pr_review.cli_runner import CliRunner
from ado_ai_pr_review.commands import CommandRouter
from ado_ai_pr_review.fixer import MechanicalFixer
from ado_ai_pr_review.git_toolset import GitToolset
from ado_ai_pr_review.models import FixCandidate, ReviewCommand, ReviewResult
from ado_ai_pr_review.ports import PRContext, ReviewRequest
from ado_ai_pr_review.publisher import SuggestionPublisher
from ado_ai_pr_review.runtime import RuntimeContext
from ado_ai_pr_review.security import SecurityScanner
from ado_ai_pr_review.tool_policy import CommandPolicy

logger = logging.getLogger(__name__)


class AdoPipelineAdapter:
    def __init__(self, repo_root: Path, dry_run: bool = False) -> None:
        self._dry_run = dry_run
        self._context = RuntimeContext.from_env(repo_root=str(repo_root))
        self._runner = CliRunner(
            policy=CommandPolicy.default(),
            secrets=[self._context.system_access_token or ""],
        )
        self._ado = AdoToolset(runner=self._runner, context=self._context)
        self._git = GitToolset(runner=self._runner, repo_root=repo_root)
        self._publisher = SuggestionPublisher(ado_toolset=self._ado)

    def load_request(self) -> ReviewRequest:
        threads = cast(dict[str, Any], self._ado.list_pr_threads())
        decision = CommandRouter().route(threads)

        if decision.command is ReviewCommand.ONBOARDING:
            return ReviewRequest(
                repo_root=self._context.repo_root,
                diff_text="",
                local_findings=(),
                command=ReviewCommand.ONBOARDING,
                pr_context=self._make_pr_context(),
            )

        self._git.fetch()
        target_ref = self._context.target_branch.removeprefix("refs/heads/")
        refspec = f"origin/{target_ref}...HEAD"
        diff_text = self._git.diff(refspec, unified=0)
        local_findings, redacted_diff = SecurityScanner().scan_diff(diff_text)

        return ReviewRequest(
            repo_root=self._context.repo_root,
            diff_text=redacted_diff,
            local_findings=tuple(local_findings),
            command=decision.command,
            pr_context=self._make_pr_context(),
        )

    def publish_onboarding(self) -> None:
        if self._dry_run:
            return
        self._publisher.publish_onboarding()

    def publish_review(self, result: ReviewResult) -> None:
        if self._dry_run:
            return
        self._publisher.publish_review(result)

    def publish_error(self, exc: BaseException) -> None:
        if self._dry_run:
            return
        with contextlib.suppress(Exception):
            self._ado.create_pr_thread(body={
                "comments": [{
                    "parentCommentId": 0,
                    "content": f"ADO AI review failed: {type(exc).__name__}. Check pipeline logs for details.",
                    "commentType": "text",
                }],
                "status": "active",
                "properties": {"adoAiReview.kind": {"$type": "System.String", "$value": "error"}},
            })

    def create_fix_branch(
        self,
        candidates: list[FixCandidate],
        branch_name: str,
        target_branch: str,
    ) -> bool:
        fixer = MechanicalFixer(
            git_toolset=self._git,
            ado_toolset=self._ado,
            repo_root=self._context.repo_root,
        )
        try:
            fixer.create_fix_branch(candidates, branch_name, target_branch)
            return True
        except RuntimeError as exc:
            logger.warning("fix branch not created: %s", exc)
            return False

    def _make_pr_context(self) -> PRContext:
        return PRContext(
            pr_id=self._context.pull_request_id,
            source_branch=self._context.source_branch,
            target_branch=self._context.target_branch,
            is_fork=self._context.is_fork,
            build_id=self._context.build_id,
        )
```

- [ ] **Step 2: Check types and lint**

```bash
.venv/bin/mypy src && .venv/bin/ruff check .
```
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add src/ado_ai_pr_review/adapters/pipeline.py
git commit -m "feat: add AdoPipelineAdapter"
```

---

## Task 4: ReviewEngine

**Files:**
- Create: `src/ado_ai_pr_review/engine.py`
- Create: `tests/test_engine.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_engine.py
from __future__ import annotations

from pathlib import Path

import pytest

from ado_ai_pr_review.models import (
    Finding,
    FindingSeverity,
    FindingType,
    FixCandidate,
    ReviewCommand,
    ReviewResult,
)
from ado_ai_pr_review.ports import PRContext, ReviewRequest


def _make_pr_context(pr_id: int | None = 42) -> PRContext:
    return PRContext(
        pr_id=pr_id,
        source_branch="refs/heads/feature",
        target_branch="refs/heads/main",
        is_fork=False,
        build_id="1",
    )


def _make_request(command: ReviewCommand = ReviewCommand.REVIEW, repo_root: Path | None = None) -> ReviewRequest:
    return ReviewRequest(
        repo_root=repo_root or Path("/tmp"),
        diff_text="diff text",
        local_findings=(),
        command=command,
        pr_context=_make_pr_context(),
    )


class _MockPlatform:
    def __init__(self, request: ReviewRequest | None = None, load_raises: Exception | None = None) -> None:
        self._request = request
        self._load_raises = load_raises
        self.onboarding_called = False
        self.review_result: ReviewResult | None = None
        self.error: BaseException | None = None
        self.fix_branch_args: tuple | None = None
        self.fix_branch_return = False

    def load_request(self) -> ReviewRequest:
        if self._load_raises is not None:
            raise self._load_raises
        assert self._request is not None
        return self._request

    def publish_onboarding(self) -> None:
        self.onboarding_called = True

    def publish_review(self, result: ReviewResult) -> None:
        self.review_result = result

    def publish_error(self, exc: BaseException) -> None:
        self.error = exc

    def create_fix_branch(self, candidates: list[FixCandidate], branch_name: str, target_branch: str) -> bool:
        self.fix_branch_args = (candidates, branch_name, target_branch)
        return self.fix_branch_return


class _MockLLM:
    def __init__(self, result: ReviewResult | None = None, raises: Exception | None = None) -> None:
        self._result = result
        self._raises = raises
        self.calls: int = 0

    def review_json(self, system_prompt: str, user_prompt: str) -> ReviewResult:
        self.calls += 1
        if self._raises is not None:
            raise self._raises
        assert self._result is not None
        return self._result


def _make_review_result(summary: str = "ok") -> ReviewResult:
    return ReviewResult(summary=summary, findings=[])


def test_engine_bootstraps_and_publishes_onboarding_when_files_created(tmp_path: Path) -> None:
    from ado_ai_pr_review.engine import ReviewEngine

    platform = _MockPlatform()
    engine = ReviewEngine(platform=platform, model=_MockLLM(), repo_root=tmp_path)
    cmd = engine.run()

    assert cmd is ReviewCommand.ONBOARDING
    assert platform.onboarding_called


def test_engine_publishes_onboarding_when_no_actionable_command(tmp_path: Path) -> None:
    from ado_ai_pr_review.engine import ReviewEngine

    _write_config(tmp_path)
    request = _make_request(command=ReviewCommand.ONBOARDING, repo_root=tmp_path)
    platform = _MockPlatform(request=request)
    engine = ReviewEngine(platform=platform, model=_MockLLM(), repo_root=tmp_path)
    cmd = engine.run()

    assert cmd is ReviewCommand.ONBOARDING
    assert platform.onboarding_called


def test_engine_runs_review_and_publishes(tmp_path: Path) -> None:
    from ado_ai_pr_review.engine import ReviewEngine

    _write_config(tmp_path)
    request = _make_request(command=ReviewCommand.REVIEW, repo_root=tmp_path)
    llm = _MockLLM(result=_make_review_result("two issues"))
    platform = _MockPlatform(request=request)
    engine = ReviewEngine(platform=platform, model=llm, repo_root=tmp_path)
    cmd = engine.run()

    assert cmd is ReviewCommand.REVIEW
    assert platform.review_result is not None
    assert platform.review_result.summary == "two issues"
    assert llm.calls == 1


def test_engine_extends_findings_with_local_findings(tmp_path: Path) -> None:
    from ado_ai_pr_review.engine import ReviewEngine

    _write_config(tmp_path)
    local_finding = Finding(
        type=FindingType.SECURITY,
        severity=FindingSeverity.CRITICAL,
        title="Secret",
        body="Remove it.",
    )
    request = ReviewRequest(
        repo_root=tmp_path,
        diff_text="diff",
        local_findings=(local_finding,),
        command=ReviewCommand.REVIEW,
        pr_context=_make_pr_context(),
    )
    llm = _MockLLM(result=_make_review_result())
    platform = _MockPlatform(request=request)
    engine = ReviewEngine(platform=platform, model=llm, repo_root=tmp_path)
    engine.run()

    assert platform.review_result is not None
    assert any(f.title == "Secret" for f in platform.review_result.findings)


def test_engine_calls_publish_error_and_reraises_on_load_failure(tmp_path: Path) -> None:
    from ado_ai_pr_review.engine import ReviewEngine

    _write_config(tmp_path)
    exc = RuntimeError("no diff")
    platform = _MockPlatform(load_raises=exc)
    engine = ReviewEngine(platform=platform, model=_MockLLM(), repo_root=tmp_path)

    with pytest.raises(RuntimeError, match="no diff"):
        engine.run()

    assert platform.error is exc


def test_engine_delegates_fix_branch_to_platform(tmp_path: Path) -> None:
    from ado_ai_pr_review.engine import ReviewEngine

    _write_config(tmp_path)
    request = _make_request(command=ReviewCommand.FIX, repo_root=tmp_path)
    llm = _MockLLM(result=_make_review_result())
    platform = _MockPlatform(request=request)
    engine = ReviewEngine(platform=platform, model=llm, repo_root=tmp_path)
    engine.run()

    assert platform.fix_branch_args is not None


def _write_config(root: Path) -> None:
    (root / ".ado-ai-review.yml").write_text(
        "version: 1\ninstructions:\n  reviewer: r.md\n  security: s.md\n  indexer: i.md\n  fixer: f.md\n",
        encoding="utf-8",
    )
```

- [ ] **Step 2: Run to verify failure**

```bash
.venv/bin/pytest tests/test_engine.py -v
```
Expected: `ImportError: cannot import name 'ReviewEngine' from 'ado_ai_pr_review.engine'`

- [ ] **Step 3: Create `engine.py`**

```python
# src/ado_ai_pr_review/engine.py
from __future__ import annotations

import logging
from pathlib import Path

from ado_ai_pr_review.bootstrap import Bootstrapper
from ado_ai_pr_review.config import ReviewConfig
from ado_ai_pr_review.context import ContextSelector
from ado_ai_pr_review.indexer import RepoIndexer
from ado_ai_pr_review.models import FindingType, FixCandidate, FixDelivery, ReviewCommand
from ado_ai_pr_review.observability import ReviewMetrics
from ado_ai_pr_review.ports import LLMPort, PlatformAdapter
from ado_ai_pr_review.reviewer import ReviewOrchestrator

logger = logging.getLogger(__name__)


class ReviewEngine:
    def __init__(
        self,
        platform: PlatformAdapter,
        model: LLMPort,
        repo_root: Path,
    ) -> None:
        self._platform = platform
        self._model = model
        self._repo_root = repo_root

    def run(self) -> ReviewCommand:
        created = Bootstrapper().create_missing_files(self._repo_root)
        if created:
            self._platform.publish_onboarding()
            return ReviewCommand.ONBOARDING

        config = ReviewConfig.load(self._repo_root)

        try:
            request = self._platform.load_request()
        except Exception as exc:
            logger.error("failed to load review request: %s", exc)
            self._platform.publish_error(exc)
            raise

        if request.command is ReviewCommand.ONBOARDING:
            self._platform.publish_onboarding()
            return ReviewCommand.ONBOARDING

        entries = RepoIndexer(exclude=config.context.index.exclude).build(request.repo_root)
        selector = ContextSelector(max_files=config.context.dynamic_context.max_files)
        prefer_tags = {"security"} if request.command is ReviewCommand.SECURITY else set()
        selected = selector.select(
            repo_root=request.repo_root,
            guidance_paths=[
                config.instructions.security if request.command is ReviewCommand.SECURITY else config.instructions.reviewer,
                *config.guidelines.code_style,
                *config.guidelines.security,
            ],
            entries=entries,
            prefer_tags=prefer_tags,
        )
        local_security_summary = f"Local findings: {len(request.local_findings)}"

        if request.command is ReviewCommand.FIX:
            return self._run_fix(request, config, selected, local_security_summary)

        try:
            result = ReviewOrchestrator(self._model).run(
                command=request.command,
                guidance=selected.always_on_guidance,
                selected_files=selected.dynamic_files,
                diff_text=request.diff_text,
                local_security_summary=local_security_summary,
            )
        except Exception as exc:
            logger.error("review failed: %s", exc)
            self._platform.publish_error(exc)
            raise

        result.findings.extend(request.local_findings)
        self._platform.publish_review(result)

        metrics = ReviewMetrics(
            command=request.command.value,
            pr_id=request.pr_context.pr_id or 0,
            findings_count=len(result.findings),
            inline_suggestions_count=sum(1 for f in result.findings if f.suggested_code),
            fix_pr_created=False,
        )
        logger.info("review metrics: %s", metrics.to_payload())
        return request.command

    def _run_fix(self, request, config, selected, local_security_summary) -> ReviewCommand:  # type: ignore[no-untyped-def]
        try:
            result = ReviewOrchestrator(self._model).run(
                command=request.command,
                guidance=selected.always_on_guidance,
                selected_files=selected.dynamic_files,
                diff_text=request.diff_text,
                local_security_summary=local_security_summary,
            )
            result.findings.extend(request.local_findings)

            fix_candidates = [
                FixCandidate(
                    delivery=FixDelivery.FIX_BRANCH_CANDIDATE,
                    title=f.title,
                    explanation=f.body,
                    file_path=f.file_path,
                    replacement=f.suggested_code,
                    commit_message=f"fix: {f.title.lower()}",
                )
                for f in result.findings
                if f.type is FindingType.MECHANICAL_FIX and f.suggested_code and f.file_path
            ]

            branch_name = config.fix.branch.name_template.format(
                pr_id=request.pr_context.pr_id or "local",
                run_id=request.pr_context.build_id,
            )
            target_branch = request.pr_context.target_branch.removeprefix("refs/heads/")

            fix_pr_created = self._platform.create_fix_branch(
                candidates=fix_candidates,
                branch_name=branch_name,
                target_branch=target_branch,
            )

            metrics = ReviewMetrics(
                command=request.command.value,
                pr_id=request.pr_context.pr_id or 0,
                findings_count=len(result.findings),
                inline_suggestions_count=sum(1 for f in result.findings if f.suggested_code),
                fix_pr_created=fix_pr_created,
            )
            logger.info("review metrics: %s", metrics.to_payload())
            return request.command

        except Exception as exc:
            logger.error("fix failed: %s", exc)
            self._platform.publish_error(exc)
            raise
```

- [ ] **Step 4: Run tests to verify passage**

```bash
.venv/bin/pytest tests/test_engine.py -v
```
Expected: 7 passed.

- [ ] **Step 5: Full suite + types + lint**

```bash
.venv/bin/pytest -v && .venv/bin/mypy src tests && .venv/bin/ruff check .
```
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/ado_ai_pr_review/engine.py tests/test_engine.py
git commit -m "feat: add ReviewEngine with PlatformAdapter/LLMPort ports"
```

---

## Task 5: LocalCliAdapter + CommandPolicy Update

**Files:**
- Create: `src/ado_ai_pr_review/adapters/local.py`
- Modify: `src/ado_ai_pr_review/tool_policy.py`
- Create: `tests/test_local_adapter.py`

- [ ] **Step 1: Add `git rev-parse --abbrev-ref HEAD` to CommandPolicy**

In `src/ado_ai_pr_review/tool_policy.py`, inside `_is_allowed_git`, add after the `_matches_exact(argv, ("git", "rev-parse", "HEAD"))` line:

```python
        if _matches_exact(argv, ("git", "rev-parse", "--abbrev-ref", "HEAD")):
            return True
```

- [ ] **Step 2: Write failing tests**

```python
# tests/test_local_adapter.py
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ado_ai_pr_review.models import ReviewCommand
from ado_ai_pr_review.tool_policy import CommandPolicy


def test_command_policy_allows_rev_parse_abbrev_ref_head() -> None:
    policy = CommandPolicy.default()
    policy.validate(["git", "rev-parse", "--abbrev-ref", "HEAD"])  # must not raise


def test_local_adapter_load_request_returns_review_request(tmp_path: Path) -> None:
    from ado_ai_pr_review.adapters.local import LocalCliAdapter
    from ado_ai_pr_review.cli_runner import CliRunner
    from ado_ai_pr_review.git_toolset import GitToolset

    runner = MagicMock(spec=CliRunner)
    runner.run.return_value = MagicMock(stdout="feature-branch\n", returncode=0, stderr="", argv=[])

    git = MagicMock(spec=GitToolset)
    git.diff.return_value = ""

    adapter = LocalCliAdapter(
        repo_root=tmp_path,
        command=ReviewCommand.REVIEW,
        target_branch="main",
        _runner=runner,
        _git=git,
    )
    request = adapter.load_request()

    assert request.command is ReviewCommand.REVIEW
    assert request.pr_context.pr_id is None
    assert request.pr_context.source_branch == "feature-branch"
    assert request.pr_context.target_branch == "main"
    assert request.pr_context.build_id == "local"
    assert request.diff_text == ""
    assert request.local_findings == ()


def test_local_adapter_publish_review_writes_to_stdout(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from ado_ai_pr_review.adapters.local import LocalCliAdapter
    from ado_ai_pr_review.models import ReviewResult

    adapter = LocalCliAdapter(repo_root=tmp_path, command=ReviewCommand.REVIEW)
    result = ReviewResult(summary="All good.", findings=[])
    adapter.publish_review(result)

    out = capsys.readouterr().out
    assert "All good." in out


def test_local_adapter_publish_error_writes_to_stderr(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from ado_ai_pr_review.adapters.local import LocalCliAdapter

    adapter = LocalCliAdapter(repo_root=tmp_path, command=ReviewCommand.REVIEW)
    adapter.publish_error(RuntimeError("boom"))

    err = capsys.readouterr().err
    assert "boom" in err


def test_local_adapter_create_fix_branch_commits_and_returns_false(tmp_path: Path) -> None:
    from ado_ai_pr_review.adapters.local import LocalCliAdapter
    from ado_ai_pr_review.cli_runner import CliRunner
    from ado_ai_pr_review.git_toolset import GitToolset
    from ado_ai_pr_review.models import FixCandidate, FixDelivery

    runner = MagicMock(spec=CliRunner)
    runner.run.return_value = MagicMock(stdout="abc1234\n", returncode=0, stderr="", argv=[])

    git = MagicMock(spec=GitToolset)
    git.commit.return_value = "abc1234"

    candidate_file = tmp_path / "file.py"
    candidate_file.write_text("original", encoding="utf-8")

    adapter = LocalCliAdapter(
        repo_root=tmp_path,
        command=ReviewCommand.FIX,
        _runner=runner,
        _git=git,
    )
    candidates = [
        FixCandidate(
            delivery=FixDelivery.FIX_BRANCH_CANDIDATE,
            title="Fix import",
            explanation="Remove unused import.",
            file_path="file.py",
            replacement="fixed",
            commit_message="fix: remove unused import",
        )
    ]
    result = adapter.create_fix_branch(candidates, "ai-fix/pr-1/run-1", "main")

    assert result is False
    git.checkout_new_branch.assert_called_once_with("ai-fix/pr-1/run-1")
    git.add.assert_called_once_with(["file.py"])
    git.commit.assert_called_once_with("fix: remove unused import")
    assert candidate_file.read_text() == "fixed"
```

- [ ] **Step 3: Run to verify failure**

```bash
.venv/bin/pytest tests/test_local_adapter.py -v
```
Expected: failures on missing `LocalCliAdapter`.

- [ ] **Step 4: Create `adapters/local.py`**

```python
# src/ado_ai_pr_review/adapters/local.py
from __future__ import annotations

import logging
from pathlib import Path

import typer

from ado_ai_pr_review.cli_runner import CliRunner
from ado_ai_pr_review.fixer import MechanicalFixer
from ado_ai_pr_review.git_toolset import GitToolset
from ado_ai_pr_review.models import FixCandidate, FixDelivery, ReviewCommand, ReviewResult
from ado_ai_pr_review.ports import PRContext, ReviewRequest
from ado_ai_pr_review.security import SecurityScanner
from ado_ai_pr_review.tool_policy import CommandPolicy

logger = logging.getLogger(__name__)


class LocalCliAdapter:
    def __init__(
        self,
        repo_root: Path,
        command: ReviewCommand,
        target_branch: str = "main",
        *,
        _runner: CliRunner | None = None,
        _git: GitToolset | None = None,
    ) -> None:
        self._repo_root = repo_root
        self._command = command
        self._target_branch = target_branch
        self._runner = _runner or CliRunner(policy=CommandPolicy.default())
        self._git = _git or GitToolset(runner=self._runner, repo_root=repo_root)

    def load_request(self) -> ReviewRequest:
        source_branch = self._runner.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=self._repo_root,
        ).stdout.strip()

        refspec = f"origin/{self._target_branch}...HEAD"
        diff_text = self._git.diff(refspec, unified=0)
        local_findings, redacted_diff = SecurityScanner().scan_diff(diff_text)

        return ReviewRequest(
            repo_root=self._repo_root,
            diff_text=redacted_diff,
            local_findings=tuple(local_findings),
            command=self._command,
            pr_context=PRContext(
                pr_id=None,
                source_branch=source_branch,
                target_branch=self._target_branch,
                is_fork=False,
                build_id="local",
            ),
        )

    def publish_onboarding(self) -> None:
        typer.echo("ADO AI review is available. Run with --command review|security|fix.")

    def publish_review(self, result: ReviewResult) -> None:
        typer.echo(f"\n=== AI Review Summary ===\n{result.summary}")
        for finding in result.findings:
            location = f"{finding.file_path}:{finding.line_start}" if finding.file_path else "general"
            typer.echo(f"\n[{finding.severity.value.upper()}] {finding.title} ({location})")
            typer.echo(finding.body)
            if finding.suggested_code:
                typer.echo(f"Suggestion:\n{finding.suggested_code}")

    def publish_error(self, exc: BaseException) -> None:
        typer.echo(f"Error: {exc}", err=True)

    def create_fix_branch(
        self,
        candidates: list[FixCandidate],
        branch_name: str,
        target_branch: str,
    ) -> bool:
        fixer = MechanicalFixer(git_toolset=None, ado_toolset=None, repo_root=self._repo_root)
        allowed = [
            c for c in candidates
            if c.delivery is FixDelivery.FIX_BRANCH_CANDIDATE
            and fixer.is_allowed(c)
            and c.file_path
            and c.replacement is not None
            and c.commit_message
        ]
        if not allowed:
            typer.echo("No mechanical fix candidates.")
            return False
        self._git.checkout_new_branch(branch_name)
        for candidate in allowed:
            path = self._repo_root / candidate.file_path  # type: ignore[arg-type]
            path.write_text(candidate.replacement, encoding="utf-8")
            self._git.add([candidate.file_path])  # type: ignore[list-item]
            sha = self._git.commit(candidate.commit_message)  # type: ignore[arg-type]
            typer.echo(f"  {sha[:8]} {candidate.commit_message}")
        typer.echo(f"Fix branch '{branch_name}' created locally (not pushed).")
        return False
```

- [ ] **Step 5: Run tests to verify passage**

```bash
.venv/bin/pytest tests/test_local_adapter.py -v
```
Expected: 5 passed.

- [ ] **Step 6: Full suite + types + lint**

```bash
.venv/bin/pytest -v && .venv/bin/mypy src tests && .venv/bin/ruff check .
```

- [ ] **Step 7: Commit**

```bash
git add src/ado_ai_pr_review/adapters/local.py src/ado_ai_pr_review/tool_policy.py \
    tests/test_local_adapter.py
git commit -m "feat: add LocalCliAdapter and git rev-parse --abbrev-ref HEAD policy"
```

---

## Task 6: CLI Refactor

**Files:**
- Modify: `src/ado_ai_pr_review/cli.py`
- Modify: `tests/test_cli.py`

The current `run` command and `run_worker()` function are replaced by three subcommands: `pipeline`, `local`, `serve`. `run_worker()` logic is now in `ReviewEngine`.

- [ ] **Step 1: Rewrite `cli.py`**

```python
# src/ado_ai_pr_review/cli.py
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Annotated

import typer

from ado_ai_pr_review.adapters.local import LocalCliAdapter
from ado_ai_pr_review.adapters.pipeline import AdoPipelineAdapter
from ado_ai_pr_review.engine import ReviewEngine
from ado_ai_pr_review.llm.azure_openai import ModelClient, ResponsesClient, build_openai_client
from ado_ai_pr_review.logging_config import configure_logging
from ado_ai_pr_review.models import ReviewCommand

logger = logging.getLogger(__name__)

app = typer.Typer(no_args_is_help=True)


@app.command()
def pipeline(
    repo_root: Annotated[str, typer.Option("--repo-root")] = ".",
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    verbose: Annotated[bool, typer.Option("--verbose")] = False,
) -> None:
    """Run the ADO AI PR review worker in Azure DevOps pipeline mode."""
    configure_logging(verbose=verbose)
    root = Path(repo_root).resolve()
    adapter = AdoPipelineAdapter(repo_root=root, dry_run=dry_run)
    model = ModelClient(
        openai_client=build_openai_client(),  # type: ignore[arg-type]
        deployment=os.environ["AZURE_OPENAI_DEPLOYMENT"],
    )
    engine = ReviewEngine(platform=adapter, model=model, repo_root=root)
    try:
        decision = engine.run()
    except Exception as exc:
        logger.error("pipeline run failed: %s", exc)
        raise typer.Exit(code=1) from exc
    typer.echo(f"ado-ai-pr-review completed command={decision.value}")


@app.command()
def local(
    command: Annotated[ReviewCommand, typer.Option("--command")] = ReviewCommand.REVIEW,
    target_branch: Annotated[str, typer.Option("--target-branch")] = "main",
    repo_root: Annotated[str, typer.Option("--repo-root")] = ".",
    llm: Annotated[str, typer.Option("--llm")] = "azure",
    verbose: Annotated[bool, typer.Option("--verbose")] = False,
) -> None:
    """Run a local review against the current branch diff."""
    configure_logging(verbose=verbose)
    root = Path(repo_root).resolve()
    adapter = LocalCliAdapter(repo_root=root, command=command, target_branch=target_branch)
    model = _build_model(llm)
    engine = ReviewEngine(platform=adapter, model=model, repo_root=root)
    try:
        engine.run()
    except Exception as exc:
        logger.error("local review failed: %s", exc)
        raise typer.Exit(code=1) from exc


@app.command()
def serve(
    host: Annotated[str, typer.Option("--host")] = "0.0.0.0",
    port: Annotated[int, typer.Option("--port")] = 8080,
    verbose: Annotated[bool, typer.Option("--verbose")] = False,
) -> None:
    """Start the webhook server for Azure Container Apps deployment."""
    configure_logging(verbose=verbose)
    import uvicorn
    from ado_ai_pr_review.webhook_server import app as webhook_app
    uvicorn.run(webhook_app, host=host, port=port)


def _build_model(llm: str) -> ModelClient:
    if llm == "copilot":
        from ado_ai_pr_review.llm.github_copilot import GitHubCopilotClient
        from ado_ai_pr_review.cli_runner import CliRunner
        from ado_ai_pr_review.tool_policy import CommandPolicy
        runner = CliRunner(policy=CommandPolicy.default())
        return GitHubCopilotClient(runner=runner)  # type: ignore[return-value]
    return ModelClient(
        openai_client=build_openai_client(),  # type: ignore[arg-type]
        deployment=os.environ["AZURE_OPENAI_DEPLOYMENT"],
    )
```

- [ ] **Step 2: Update `tests/test_cli.py`**

Replace the entire file:

```python
# tests/test_cli.py
from __future__ import annotations

import os
from pathlib import Path

import pytest
from pytest_mock import MockerFixture
from typer.testing import CliRunner

from ado_ai_pr_review.cli import app
from ado_ai_pr_review.errors import ConfigurationError
from ado_ai_pr_review.models import ReviewCommand
from ado_ai_pr_review.runtime import RuntimeContext


# ── pipeline subcommand ────────────────────────────────────────────────────────

def test_pipeline_help_renders() -> None:
    result = CliRunner().invoke(app, ["pipeline", "--help"])
    assert result.exit_code == 0
    assert "repo-root" in result.output


def test_pipeline_runs_engine(mocker: MockerFixture, tmp_path: Path) -> None:
    mocker.patch.dict(os.environ, {
        "SYSTEM_TEAMFOUNDATIONCOLLECTIONURI": "https://dev.azure.com/acme/",
        "SYSTEM_TEAMPROJECT": "P",
        "BUILD_REPOSITORY_ID": "r",
        "SYSTEM_PULLREQUEST_PULLREQUESTID": "1",
        "AZURE_OPENAI_BASE_URL": "https://example.com/",
        "AZURE_OPENAI_DEPLOYMENT": "model",
    })
    mocker.patch("ado_ai_pr_review.cli.AdoPipelineAdapter")
    mocker.patch("ado_ai_pr_review.cli.build_openai_client")
    engine_mock = mocker.patch("ado_ai_pr_review.cli.ReviewEngine")
    engine_mock.return_value.run.return_value = ReviewCommand.ONBOARDING

    result = CliRunner().invoke(app, ["pipeline", "--repo-root", str(tmp_path), "--dry-run"])

    assert result.exit_code == 0
    assert "completed" in result.output
    engine_mock.return_value.run.assert_called_once()


def test_pipeline_exits_1_on_engine_error(mocker: MockerFixture, tmp_path: Path) -> None:
    mocker.patch.dict(os.environ, {
        "SYSTEM_TEAMFOUNDATIONCOLLECTIONURI": "https://dev.azure.com/acme/",
        "SYSTEM_TEAMPROJECT": "P",
        "BUILD_REPOSITORY_ID": "r",
        "SYSTEM_PULLREQUEST_PULLREQUESTID": "1",
        "AZURE_OPENAI_BASE_URL": "https://example.com/",
        "AZURE_OPENAI_DEPLOYMENT": "model",
    })
    mocker.patch("ado_ai_pr_review.cli.AdoPipelineAdapter")
    mocker.patch("ado_ai_pr_review.cli.build_openai_client")
    engine_mock = mocker.patch("ado_ai_pr_review.cli.ReviewEngine")
    engine_mock.return_value.run.side_effect = RuntimeError("model unavailable")

    result = CliRunner().invoke(app, ["pipeline", "--repo-root", str(tmp_path)])

    assert result.exit_code == 1


# ── local subcommand ───────────────────────────────────────────────────────────

def test_local_help_renders() -> None:
    result = CliRunner().invoke(app, ["local", "--help"])
    assert result.exit_code == 0
    assert "command" in result.output


def test_local_runs_engine(mocker: MockerFixture, tmp_path: Path) -> None:
    mocker.patch.dict(os.environ, {
        "AZURE_OPENAI_BASE_URL": "https://example.com/",
        "AZURE_OPENAI_DEPLOYMENT": "model",
    })
    mocker.patch("ado_ai_pr_review.cli.LocalCliAdapter")
    mocker.patch("ado_ai_pr_review.cli.build_openai_client")
    engine_mock = mocker.patch("ado_ai_pr_review.cli.ReviewEngine")
    engine_mock.return_value.run.return_value = ReviewCommand.REVIEW

    result = CliRunner().invoke(app, ["local", "--command", "review", "--repo-root", str(tmp_path)])

    assert result.exit_code == 0


# ── RuntimeContext (unchanged, still in test_cli.py) ─────────────────────────

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
    assert context.pull_request_id == 42
    assert context.is_fork is False
    assert context.system_access_token == "token-value"


def test_runtime_context_requires_pr_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SYSTEM_PULLREQUEST_PULLREQUESTID", raising=False)
    with pytest.raises(ConfigurationError, match="SYSTEM_PULLREQUEST_PULLREQUESTID"):
        RuntimeContext.from_env(repo_root=".")


def test_runtime_context_accepts_true_is_fork_with_whitespace(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SYSTEM_TEAMFOUNDATIONCOLLECTIONURI", "https://dev.azure.com/acme/")
    monkeypatch.setenv("SYSTEM_TEAMPROJECT", "Payments")
    monkeypatch.setenv("BUILD_REPOSITORY_ID", "repo-123")
    monkeypatch.setenv("SYSTEM_PULLREQUEST_PULLREQUESTID", "42")
    monkeypatch.setenv("SYSTEM_PULLREQUEST_ISFORK", "true ")

    context = RuntimeContext.from_env(repo_root=".")

    assert context.is_fork is True


def test_runtime_context_rejects_unknown_is_fork_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SYSTEM_TEAMFOUNDATIONCOLLECTIONURI", "https://dev.azure.com/acme/")
    monkeypatch.setenv("SYSTEM_TEAMPROJECT", "Payments")
    monkeypatch.setenv("BUILD_REPOSITORY_ID", "repo-123")
    monkeypatch.setenv("SYSTEM_PULLREQUEST_PULLREQUESTID", "42")
    monkeypatch.setenv("SYSTEM_PULLREQUEST_ISFORK", "maybe")

    with pytest.raises(ConfigurationError, match="SYSTEM_PULLREQUEST_ISFORK"):
        RuntimeContext.from_env(repo_root=".")
```

- [ ] **Step 3: Run tests to verify passage**

```bash
.venv/bin/pytest tests/test_cli.py -v
```
Expected: all pass.

- [ ] **Step 4: Full suite + types + lint**

```bash
.venv/bin/pytest -v && .venv/bin/mypy src tests && .venv/bin/ruff check .
```

- [ ] **Step 5: Commit**

```bash
git add src/ado_ai_pr_review/cli.py tests/test_cli.py
git commit -m "refactor: replace run_worker with pipeline/local/serve subcommands"
```

---

## Task 7: AdoWebhookAdapter

**Files:**
- Create: `src/ado_ai_pr_review/adapters/webhook.py`
- Create: `tests/test_webhook_adapter.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_webhook_adapter.py
from __future__ import annotations

import pytest

from ado_ai_pr_review.adapters.webhook import AdoWebhookPayload


_PR_CREATED_PAYLOAD = {
    "eventType": "git.pullrequest.created",
    "resource": {
        "pullRequestId": 42,
        "sourceRefName": "refs/heads/feature/my-branch",
        "targetRefName": "refs/heads/main",
        "repository": {
            "id": "repo-guid",
            "name": "MyRepo",
            "remoteUrl": "https://dev.azure.com/org/project/_git/MyRepo",
            "project": {"name": "MyProject"},
        },
    },
    "resourceContainers": {"collection": {"baseUrl": "https://dev.azure.com/org/"}},
}

_COMMENT_PAYLOAD = {
    "eventType": "ms.vss-code.git-pullrequest-comment-event",
    "resource": {
        "pullRequest": {
            "pullRequestId": 42,
            "sourceRefName": "refs/heads/feature/my-branch",
            "targetRefName": "refs/heads/main",
            "repository": {
                "id": "repo-guid",
                "name": "MyRepo",
                "remoteUrl": "https://dev.azure.com/org/project/_git/MyRepo",
                "project": {"name": "MyProject"},
            },
        },
        "comment": {"content": "/ai review"},
    },
    "resourceContainers": {"collection": {"baseUrl": "https://dev.azure.com/org/"}},
}


def test_parse_pr_created_payload() -> None:
    payload = AdoWebhookPayload.model_validate(_PR_CREATED_PAYLOAD)

    assert payload.event_type == "git.pullrequest.created"
    assert payload.pull_request_id == 42
    assert payload.source_ref_name == "refs/heads/feature/my-branch"
    assert payload.target_ref_name == "refs/heads/main"
    assert payload.repository_name == "MyRepo"
    assert payload.remote_url == "https://dev.azure.com/org/project/_git/MyRepo"
    assert payload.project_name == "MyProject"
    assert payload.organization_url == "https://dev.azure.com/org/"
    assert payload.inline_command is None


def test_parse_comment_payload() -> None:
    payload = AdoWebhookPayload.model_validate(_COMMENT_PAYLOAD)

    assert payload.event_type == "ms.vss-code.git-pullrequest-comment-event"
    assert payload.pull_request_id == 42
    assert payload.inline_command == "/ai review"


def test_payload_rejects_missing_pull_request_id() -> None:
    from pydantic import ValidationError
    broken = {**_PR_CREATED_PAYLOAD, "resource": {"repository": _PR_CREATED_PAYLOAD["resource"]["repository"]}}
    with pytest.raises(ValidationError):
        AdoWebhookPayload.model_validate(broken)
```

- [ ] **Step 2: Run to verify failure**

```bash
.venv/bin/pytest tests/test_webhook_adapter.py -v
```
Expected: `ImportError: cannot import name 'AdoWebhookPayload'`

- [ ] **Step 3: Create `adapters/webhook.py`**

```python
# src/ado_ai_pr_review/adapters/webhook.py
from __future__ import annotations

import contextlib
import logging
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ado_ai_pr_review.ado_toolset import AdoToolset
from ado_ai_pr_review.cli_runner import CliRunner
from ado_ai_pr_review.commands import CommandRouter
from ado_ai_pr_review.fixer import MechanicalFixer
from ado_ai_pr_review.git_toolset import GitToolset
from ado_ai_pr_review.models import FixCandidate, ReviewCommand, ReviewResult
from ado_ai_pr_review.ports import PRContext, ReviewRequest
from ado_ai_pr_review.publisher import SuggestionPublisher
from ado_ai_pr_review.runtime import RuntimeContext
from ado_ai_pr_review.security import SecurityScanner
from ado_ai_pr_review.tool_policy import CommandPolicy

logger = logging.getLogger(__name__)


class _RepoProject(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str


class _Repository(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    name: str
    remote_url: str = Field(alias="remoteUrl")
    project: _RepoProject


class _PullRequestResource(BaseModel):
    model_config = ConfigDict(extra="allow")
    pull_request_id: int = Field(alias="pullRequestId")
    source_ref_name: str = Field(alias="sourceRefName")
    target_ref_name: str = Field(alias="targetRefName")
    repository: _Repository


class _Comment(BaseModel):
    model_config = ConfigDict(extra="allow")
    content: str = ""


class _Resource(BaseModel):
    model_config = ConfigDict(extra="allow")
    # Direct PR events (created, updated)
    pull_request_id: int | None = Field(default=None, alias="pullRequestId")
    source_ref_name: str | None = Field(default=None, alias="sourceRefName")
    target_ref_name: str | None = Field(default=None, alias="targetRefName")
    repository: _Repository | None = None
    # Comment events
    pull_request: _PullRequestResource | None = Field(default=None, alias="pullRequest")
    comment: _Comment | None = None


class _Collection(BaseModel):
    model_config = ConfigDict(extra="allow")
    base_url: str = Field(alias="baseUrl")


class _ResourceContainers(BaseModel):
    model_config = ConfigDict(extra="allow")
    collection: _Collection


class AdoWebhookPayload(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    event_type: str = Field(alias="eventType")
    resource: _Resource
    resource_containers: _ResourceContainers = Field(alias="resourceContainers")

    @model_validator(mode="after")
    def validate_pr_resolvable(self) -> AdoWebhookPayload:
        try:
            _ = self.pull_request_id
        except ValueError as exc:
            raise ValueError("Cannot resolve pull request from payload") from exc
        return self

    @property
    def pull_request_id(self) -> int:
        if self.resource.pull_request is not None:
            return self.resource.pull_request.pull_request_id
        if self.resource.pull_request_id is not None:
            return self.resource.pull_request_id
        raise ValueError("pull_request_id not found in payload")

    @property
    def source_ref_name(self) -> str:
        if self.resource.pull_request is not None:
            return self.resource.pull_request.source_ref_name
        return self.resource.source_ref_name or ""

    @property
    def target_ref_name(self) -> str:
        if self.resource.pull_request is not None:
            return self.resource.pull_request.target_ref_name
        return self.resource.target_ref_name or ""

    @property
    def repository_name(self) -> str:
        repo = self.resource.pull_request.repository if self.resource.pull_request else self.resource.repository
        return repo.name if repo else ""

    @property
    def remote_url(self) -> str:
        repo = self.resource.pull_request.repository if self.resource.pull_request else self.resource.repository
        return repo.remote_url if repo else ""

    @property
    def project_name(self) -> str:
        repo = self.resource.pull_request.repository if self.resource.pull_request else self.resource.repository
        return repo.project.name if repo else ""

    @property
    def organization_url(self) -> str:
        return self.resource_containers.collection.base_url

    @property
    def inline_command(self) -> str | None:
        if self.resource.comment and self.resource.comment.content:
            return self.resource.comment.content
        return None


class AdoWebhookAdapter:
    def __init__(
        self,
        payload: AdoWebhookPayload,
        auth_token: str,
        temp_dir: Path,
    ) -> None:
        self._payload = payload
        self._auth_token = auth_token
        self._temp_dir = temp_dir

        # Clone the repo branch into temp_dir
        authenticated_url = self._authenticated_clone_url()
        source_branch = payload.source_ref_name.removeprefix("refs/heads/")
        bootstrap_runner = CliRunner(policy=CommandPolicy.default(), secrets=[auth_token])
        bootstrap_runner.run(
            ["git", "clone", "--depth", "50", "--branch", source_branch, authenticated_url, str(temp_dir)],
            cwd=temp_dir.parent,
        )

        # Build RuntimeContext from payload (not env vars)
        self._context = RuntimeContext(
            repo_root=temp_dir,
            organization_url=payload.organization_url,
            project=payload.project_name,
            repository_id="",  # not needed for REST calls via az
            repository_name=payload.repository_name,
            pull_request_id=payload.pull_request_id,
            source_branch=payload.source_ref_name,
            target_branch=payload.target_ref_name,
            is_fork=False,
            build_id="webhook",
            system_access_token=auth_token,
        )
        self._runner = CliRunner(policy=CommandPolicy.default(), secrets=[auth_token])
        self._ado = AdoToolset(runner=self._runner, context=self._context)
        self._git = GitToolset(runner=self._runner, repo_root=temp_dir)
        self._publisher = SuggestionPublisher(ado_toolset=self._ado)

    def load_request(self) -> ReviewRequest:
        if self._payload.inline_command is not None:
            command = CommandRouter()._detect(self._payload.inline_command)  # noqa: SLF001
            if command is None:
                command = ReviewCommand.ONBOARDING
        else:
            threads = cast(dict[str, Any], self._ado.list_pr_threads())
            decision = CommandRouter().route(threads)
            command = decision.command

        if command is ReviewCommand.ONBOARDING:
            return ReviewRequest(
                repo_root=self._temp_dir,
                diff_text="",
                local_findings=(),
                command=ReviewCommand.ONBOARDING,
                pr_context=self._make_pr_context(),
            )

        target_ref = self._payload.target_ref_name.removeprefix("refs/heads/")
        diff_text = self._git.diff(f"origin/{target_ref}...HEAD", unified=0)
        local_findings, redacted_diff = SecurityScanner().scan_diff(diff_text)

        return ReviewRequest(
            repo_root=self._temp_dir,
            diff_text=redacted_diff,
            local_findings=tuple(local_findings),
            command=command,
            pr_context=self._make_pr_context(),
        )

    def publish_onboarding(self) -> None:
        self._publisher.publish_onboarding()

    def publish_review(self, result: ReviewResult) -> None:
        self._publisher.publish_review(result)

    def publish_error(self, exc: BaseException) -> None:
        with contextlib.suppress(Exception):
            self._ado.create_pr_thread(body={
                "comments": [{
                    "parentCommentId": 0,
                    "content": f"ADO AI review failed: {type(exc).__name__}. Check webhook logs for details.",
                    "commentType": "text",
                }],
                "status": "active",
                "properties": {"adoAiReview.kind": {"$type": "System.String", "$value": "error"}},
            })

    def create_fix_branch(
        self,
        candidates: list[FixCandidate],
        branch_name: str,
        target_branch: str,
    ) -> bool:
        fixer = MechanicalFixer(
            git_toolset=self._git,
            ado_toolset=self._ado,
            repo_root=self._temp_dir,
        )
        try:
            fixer.create_fix_branch(candidates, branch_name, target_branch)
            return True
        except RuntimeError as exc:
            logger.warning("fix branch not created: %s", exc)
            return False

    def _make_pr_context(self) -> PRContext:
        return PRContext(
            pr_id=self._payload.pull_request_id,
            source_branch=self._payload.source_ref_name,
            target_branch=self._payload.target_ref_name,
            is_fork=False,
            build_id="webhook",
        )

    def _authenticated_clone_url(self) -> str:
        url = self._payload.remote_url
        if url.startswith("https://"):
            return url.replace("https://", f"https://:{self._auth_token}@", 1)
        return url
```

Note: `CommandPolicy` does not currently allow `git clone`. Add it to `tool_policy.py` `_is_allowed_git`:

```python
        if (
            len(argv) >= 6
            and _matches_shape(argv, ("git", "clone", "--depth"))
            and argv[3].isdigit()
            and argv[4] == "--branch"
            and _is_safe_branch(argv[5])
        ):
            return True
```

- [ ] **Step 4: Run tests to verify passage**

```bash
.venv/bin/pytest tests/test_webhook_adapter.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Full suite + types + lint**

```bash
.venv/bin/pytest -v && .venv/bin/mypy src tests && .venv/bin/ruff check .
```

- [ ] **Step 6: Commit**

```bash
git add src/ado_ai_pr_review/adapters/webhook.py src/ado_ai_pr_review/tool_policy.py \
    tests/test_webhook_adapter.py
git commit -m "feat: add AdoWebhookPayload and AdoWebhookAdapter"
```

---

## Task 8: Webhook Server

**Files:**
- Create: `src/ado_ai_pr_review/webhook_server.py`
- Create: `tests/test_webhook_server.py`
- Modify: `pyproject.toml` (add fastapi, uvicorn, httpx)

- [ ] **Step 1: Add dependencies to `pyproject.toml`**

In the `[project]` `dependencies` list, add:

```toml
  "fastapi>=0.115.0",
  "uvicorn[standard]>=0.30.0",
```

In `[project.optional-dependencies]` `dev` list, add:

```toml
  "httpx>=0.27.0",
```

Install them:

```bash
.venv/bin/pip install ".[dev]"
```

- [ ] **Step 2: Write failing tests**

```python
# tests/test_webhook_server.py
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from ado_ai_pr_review.webhook_server import app

_PR_CREATED_PAYLOAD = {
    "eventType": "git.pullrequest.created",
    "resource": {
        "pullRequestId": 42,
        "sourceRefName": "refs/heads/feature/x",
        "targetRefName": "refs/heads/main",
        "repository": {
            "id": "repo-guid",
            "name": "MyRepo",
            "remoteUrl": "https://dev.azure.com/org/proj/_git/MyRepo",
            "project": {"name": "Proj"},
        },
    },
    "resourceContainers": {"collection": {"baseUrl": "https://dev.azure.com/org/"}},
}


def test_health_returns_ok() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_webhook_returns_accepted_immediately(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADO_AUTH_TOKEN", "fake-token")
    monkeypatch.setenv("AZURE_OPENAI_BASE_URL", "https://example.com/")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "model")

    with patch("ado_ai_pr_review.webhook_server._process_sync") as mock_process:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/webhook/ado", json=_PR_CREATED_PAYLOAD)

    assert response.status_code == 200
    assert response.json() == {"status": "accepted"}


def test_webhook_returns_400_on_invalid_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADO_AUTH_TOKEN", "fake-token")
    client = TestClient(app)
    response = client.post("/webhook/ado", json={"eventType": "unknown", "resource": {}, "resourceContainers": {"collection": {"baseUrl": "https://example.com/"}}})
    assert response.status_code == 422


def test_webhook_returns_401_without_auth_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ADO_AUTH_TOKEN", raising=False)
    client = TestClient(app)
    response = client.post("/webhook/ado", json=_PR_CREATED_PAYLOAD)
    assert response.status_code == 401
```

- [ ] **Step 3: Run to verify failure**

```bash
.venv/bin/pytest tests/test_webhook_server.py -v
```
Expected: `ImportError: cannot import name 'app' from 'ado_ai_pr_review.webhook_server'`

- [ ] **Step 4: Create `webhook_server.py`**

```python
# src/ado_ai_pr_review/webhook_server.py
from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException

from ado_ai_pr_review.adapters.webhook import AdoWebhookAdapter, AdoWebhookPayload
from ado_ai_pr_review.engine import ReviewEngine
from ado_ai_pr_review.llm.azure_openai import ModelClient, build_openai_client

logger = logging.getLogger(__name__)

app = FastAPI(title="ADO AI PR Review Webhook")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/webhook/ado")
async def handle_ado_webhook(payload: AdoWebhookPayload) -> dict[str, str]:
    auth_token = os.getenv("ADO_AUTH_TOKEN")
    if not auth_token:
        raise HTTPException(status_code=401, detail="ADO_AUTH_TOKEN not configured")
    asyncio.create_task(asyncio.to_thread(_process_sync, payload, auth_token))
    return {"status": "accepted"}


def _process_sync(payload: AdoWebhookPayload, auth_token: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        temp_dir = Path(tmp)
        try:
            adapter = AdoWebhookAdapter(payload=payload, auth_token=auth_token, temp_dir=temp_dir)
            model = ModelClient(
                openai_client=build_openai_client(),  # type: ignore[arg-type]
                deployment=os.environ["AZURE_OPENAI_DEPLOYMENT"],
            )
            engine = ReviewEngine(platform=adapter, model=model, repo_root=temp_dir)
            engine.run()
        except Exception:
            logger.exception("webhook processing failed for PR %s", payload.pull_request_id)
```

- [ ] **Step 5: Run tests to verify passage**

```bash
.venv/bin/pytest tests/test_webhook_server.py -v
```
Expected: 4 passed.

- [ ] **Step 6: Full suite + types + lint**

```bash
.venv/bin/pytest -v && .venv/bin/mypy src tests && .venv/bin/ruff check .
```

- [ ] **Step 7: Commit**

```bash
git add src/ado_ai_pr_review/webhook_server.py tests/test_webhook_server.py pyproject.toml
git commit -m "feat: add FastAPI webhook server with /webhook/ado and /health"
```

---

## Task 9: GitHubCopilotClient (optional LLM adapter)

**Files:**
- Create: `src/ado_ai_pr_review/llm/github_copilot.py`
- Modify: `src/ado_ai_pr_review/tool_policy.py` (add `gh auth token`)
- Create: `tests/test_github_copilot.py`

- [ ] **Step 1: Add `gh auth token` to CommandPolicy**

In `tool_policy.py`, add `"gh"` to the binary allowlist check:

```python
        if argv[0] not in {"git", "az", "gh"}:
            raise CommandRejectedError("Binary is not allowlisted")
```

Add a new branch in `validate`:

```python
        if argv[0] == "gh" and self._is_allowed_gh(argv):
            return
```

Add the method:

```python
    def _is_allowed_gh(self, argv: list[str]) -> bool:
        return _matches_exact(argv, ("gh", "auth", "token"))
```

- [ ] **Step 2: Write failing tests**

```python
# tests/test_github_copilot.py
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ado_ai_pr_review.tool_policy import CommandPolicy


def test_command_policy_allows_gh_auth_token() -> None:
    policy = CommandPolicy.default()
    policy.validate(["gh", "auth", "token"])  # must not raise


def test_command_policy_rejects_other_gh_commands() -> None:
    from ado_ai_pr_review.errors import CommandRejectedError
    policy = CommandPolicy.default()
    with pytest.raises(CommandRejectedError):
        policy.validate(["gh", "repo", "clone", "owner/repo"])


def test_github_copilot_client_fetches_token_and_calls_openai(mocker) -> None:  # type: ignore[no-untyped-def]
    from ado_ai_pr_review.cli_runner import CliRunner, CommandResult
    from ado_ai_pr_review.llm.github_copilot import GitHubCopilotClient
    from ado_ai_pr_review.models import ReviewResult

    runner = MagicMock(spec=CliRunner)
    runner.run.return_value = CommandResult(
        argv=["gh", "auth", "token"],
        returncode=0,
        stdout="ghu_test_token_12345\n",
        stderr="",
    )

    openai_mock = mocker.patch("ado_ai_pr_review.llm.github_copilot.OpenAI")
    openai_mock.return_value.responses.create.return_value.output_text = '{"summary":"ok","findings":[]}'

    client = GitHubCopilotClient(runner=runner)
    result = client.review_json(system_prompt="system", user_prompt="user")

    assert result.summary == "ok"
    openai_mock.assert_called_once()
    call_kwargs = openai_mock.call_args
    assert call_kwargs.kwargs["api_key"] == "ghu_test_token_12345"
```

- [ ] **Step 3: Run to verify failure**

```bash
.venv/bin/pytest tests/test_github_copilot.py -v
```
Expected: failures on missing module / policy.

- [ ] **Step 4: Create `llm/github_copilot.py`**

```python
# src/ado_ai_pr_review/llm/github_copilot.py
from __future__ import annotations

import json

from openai import OpenAI
from pydantic import ValidationError

from ado_ai_pr_review.cli_runner import CliRunner
from ado_ai_pr_review.errors import ModelOutputError
from ado_ai_pr_review.models import ReviewResult

_BASE_URL = "https://api.githubcopilot.com"
_DEPLOYMENT = "gpt-4o"


class GitHubCopilotClient:
    def __init__(self, runner: CliRunner) -> None:
        result = runner.run(["gh", "auth", "token"], cwd=runner._policy.__class__.__module__  # type: ignore[attr-defined]
                            and __import__("pathlib").Path("."), check=True)
        token = result.stdout.strip()
        self._client = OpenAI(api_key=token, base_url=_BASE_URL)

    def review_json(self, system_prompt: str, user_prompt: str) -> ReviewResult:
        response = self._client.responses.create(
            model=_DEPLOYMENT,
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
        output_text = str(response.output_text)
        try:
            return ReviewResult.model_validate(json.loads(output_text))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ModelOutputError(f"Model returned invalid review JSON: {exc}") from exc
```

Note: the `runner.run` call needs a `cwd` path. Simplify by always using `Path(".")`:

```python
    def __init__(self, runner: CliRunner) -> None:
        from pathlib import Path
        result = runner.run(["gh", "auth", "token"], cwd=Path("."))
        token = result.stdout.strip()
        self._client = OpenAI(api_key=token, base_url=_BASE_URL)
```

- [ ] **Step 5: Run tests to verify passage**

```bash
.venv/bin/pytest tests/test_github_copilot.py -v
```
Expected: 3 passed.

- [ ] **Step 6: Full suite + types + lint**

```bash
.venv/bin/pytest -v && .venv/bin/mypy src tests && .venv/bin/ruff check .
```

- [ ] **Step 7: Commit**

```bash
git add src/ado_ai_pr_review/llm/github_copilot.py src/ado_ai_pr_review/tool_policy.py \
    tests/test_github_copilot.py
git commit -m "feat: add GitHubCopilotClient LLM adapter and gh auth token policy"
```

---

## Task 10: Dockerfile and Pipeline YAML

**Files:**
- Modify: `Dockerfile`
- Modify: `azure-pipelines.ado-ai-review.yml`

- [ ] **Step 1: Update `Dockerfile`**

Add `CMD ["pipeline"]` after ENTRYPOINT so `docker run image --repo-root /repo` still works (Docker appends CMD to ENTRYPOINT when no command is given at `docker run` time):

```dockerfile
FROM mcr.microsoft.com/azure-cli:2.79.0

WORKDIR /app

RUN tdnf install -y git bash python3-pip && \
    az extension add --name azure-devops

COPY pyproject.toml ruff.toml mypy.ini README.md ./
COPY src ./src

RUN python3 -m pip install --root-user-action=ignore ".[dev]" || \
    python3 -m pip install --root-user-action=ignore .

EXPOSE 8080

ENTRYPOINT ["ado-ai-pr-review"]
CMD ["pipeline"]
```

Wait — the pipeline runs `docker run ... --repo-root /repo`. With `ENTRYPOINT ["ado-ai-pr-review"]` and `CMD ["pipeline"]`, running `docker run image --repo-root /repo` produces `ado-ai-pr-review --repo-root /repo` (CMD is overridden by the extra args). This is wrong.

The pipeline YAML must be updated to pass `pipeline` explicitly:

```yaml
docker run ... ghcr.io/... pipeline --repo-root /repo
```

Update `azure-pipelines.ado-ai-review.yml` step:

```yaml
  - script: |
      docker run --rm \
        -v "$(Build.SourcesDirectory):/repo" \
        -w /repo \
        -e SYSTEM_ACCESSTOKEN \
        -e SYSTEM_TEAMFOUNDATIONCOLLECTIONURI \
        -e SYSTEM_TEAMPROJECT \
        -e BUILD_REPOSITORY_ID \
        -e BUILD_REPOSITORY_NAME \
        -e SYSTEM_PULLREQUEST_PULLREQUESTID \
        -e SYSTEM_PULLREQUEST_SOURCEBRANCH \
        -e SYSTEM_PULLREQUEST_TARGETBRANCH \
        -e SYSTEM_PULLREQUEST_ISFORK \
        -e BUILD_BUILDID \
        -e AZURE_OPENAI_BASE_URL \
        -e AZURE_OPENAI_DEPLOYMENT \
        -e AZURE_OPENAI_API_KEY \
        ghcr.io/kamilpieronczyk/ado-pr-agent:$(imageVersion) \
        pipeline --repo-root /repo
    displayName: Run ADO AI PR review
    env:
      SYSTEM_ACCESSTOKEN: $(System.AccessToken)
      AZURE_OPENAI_BASE_URL: $(AZURE_OPENAI_BASE_URL)
      AZURE_OPENAI_DEPLOYMENT: $(AZURE_OPENAI_DEPLOYMENT)
      AZURE_OPENAI_API_KEY: $(AZURE_OPENAI_API_KEY)
```

And the Dockerfile just keeps `ENTRYPOINT ["ado-ai-pr-review"]` without CMD, so `docker run image serve` launches the webhook server.

Final `Dockerfile`:

```dockerfile
FROM mcr.microsoft.com/azure-cli:2.79.0

WORKDIR /app

RUN tdnf install -y git bash python3-pip && \
    az extension add --name azure-devops

COPY pyproject.toml ruff.toml mypy.ini README.md ./
COPY src ./src

RUN python3 -m pip install --root-user-action=ignore .

EXPOSE 8080

ENTRYPOINT ["ado-ai-pr-review"]
```

- [ ] **Step 2: Run full suite one final time**

```bash
.venv/bin/pytest -v && .venv/bin/mypy src tests && .venv/bin/ruff check .
```
Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add Dockerfile azure-pipelines.ado-ai-review.yml
git commit -m "feat: expose port 8080 and update pipeline to use pipeline subcommand"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|---|---|
| `ports.py` with PRContext, ReviewRequest, PlatformAdapter, LLMPort | Task 1 |
| `ReviewRequest.local_findings` (spec amendment) | Task 1 |
| `llm/azure_openai.py` + re-export shim | Task 2 |
| `reviewer.py` type annotation update | Task 2 |
| `AdoPipelineAdapter` | Task 3 |
| `ReviewEngine` | Task 4 |
| `LocalCliAdapter` + `git rev-parse --abbrev-ref HEAD` policy | Task 5 |
| CLI subcommands: `pipeline`, `local`, `serve` | Task 6 |
| `AdoWebhookPayload` + `AdoWebhookAdapter` + `git clone` policy | Task 7 |
| FastAPI `/webhook/ado` + `/health` + `asyncio.to_thread` | Task 8 |
| `ADO_AUTH_TOKEN` env var for webhook auth | Task 8 |
| `GitHubCopilotClient` + `gh auth token` policy | Task 9 |
| `--llm copilot` flag in `local` subcommand | Task 6 |
| Dockerfile EXPOSE 8080 | Task 10 |
| Pipeline YAML `pipeline --repo-root /repo` | Task 10 |
| Auth token not logged (CliRunner secrets param) | Task 3, 7 |

**Type consistency check:**

- `PlatformAdapter.create_fix_branch(candidates: list[FixCandidate], branch_name: str, target_branch: str) -> bool` — used consistently in Tasks 3, 4, 5, 7.
- `ReviewRequest.local_findings: tuple[Finding, ...]` — defined Task 1, used Task 3, 4, 5, 7.
- `LLMPort.review_json(system_prompt: str, user_prompt: str) -> ReviewResult` — matches `ModelClient` and `GitHubCopilotClient` signatures.
- `ReviewOrchestrator.__init__(model_client: LLMPort)` — updated Task 2, used Task 4.
- `AdoPipelineAdapter(repo_root: Path, dry_run: bool = False)` — defined Task 3, constructed Task 6.
- `LocalCliAdapter(repo_root, command, target_branch, *, _runner, _git)` — defined Task 5, constructed Task 6.
- `AdoWebhookAdapter(payload, auth_token, temp_dir)` — defined Task 7, constructed Task 8.

# Architecture Refactoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all Critical and Important architectural issues identified in the code review: dead code, OCP violations in the engine, leaking concrete types through ports, duplicate logic across adapters, and god-file webhook.py.

**Architecture:** Incremental refactoring — each task leaves all tests green. Start with non-breaking deletions and mutations, progress through port completion and adapter cleanup, finish with OCP fix in the engine's command dispatch.

**Tech Stack:** Python 3.13, Pydantic v2, pytest + pytest-mock, FastAPI, Typer.

---

## File Map

| Task | Files Modified / Created |
|------|--------------------------|
| 1 | Delete `model_client.py`, `git_clone.py`, `test_git_clone.py`; update `test_model_client.py` |
| 2 | `models.py`, `engine.py` |
| 3 | `ports.py`, `fixer.py` (type hints only) |
| 4 | `fixer.py` (full rewrite), `adapters/local.py`, `adapters/webhook.py`, `tests/test_fixer.py`, `tests/test_local_adapter.py` |
| 5 | Create `adapters/webhook_payload.py`, update `adapters/webhook.py`, `tests/test_webhook_adapter.py` |
| 6 | `adapters/webhook.py`, `tests/test_webhook_adapter.py` |
| 7 | Create `llm/factory.py`, update `cli.py`, `webhook_server.py` |
| 8 | `engine.py`, `adapters/local.py`, `tests/test_engine.py`, `tests/test_local_adapter.py` |
| 9 | Create `handlers/` package (5 files), update `engine.py`, `tests/test_engine.py` |

---

## Task 1: Delete Dead Code

**Files:**
- Delete: `src/ado_ai_pr_review/model_client.py`
- Delete: `src/ado_ai_pr_review/git_clone.py`
- Delete: `tests/test_git_clone.py`
- Modify: `tests/test_model_client.py`

- [ ] **Step 1: Update test_model_client.py — change the import**

  Change line 5 from:
  ```python
  from ado_ai_pr_review.model_client import ModelClient
  ```
  to:
  ```python
  from ado_ai_pr_review.llm.azure_openai import ModelClient
  ```

- [ ] **Step 2: Run the test to confirm it passes with the new import**

  ```bash
  cd /Users/kamilpieronczyk/Documents/private-work/ado-ai-pr-review
  uv run pytest tests/test_model_client.py -v
  ```
  Expected: all 5 tests pass.

- [ ] **Step 3: Delete the dead files**

  ```bash
  rm src/ado_ai_pr_review/model_client.py
  rm src/ado_ai_pr_review/git_clone.py
  rm tests/test_git_clone.py
  ```

- [ ] **Step 4: Verify no remaining imports of the deleted modules**

  ```bash
  grep -r "model_client\|git_clone\|GitCloneService" src/ tests/ --include="*.py"
  ```
  Expected: no output.

- [ ] **Step 5: Run the full test suite**

  ```bash
  uv run pytest -x -q
  ```
  Expected: all tests pass.

- [ ] **Step 6: Commit**

  ```bash
  git add -u
  git commit -m "chore: delete dead model_client shim and unused GitCloneService"
  ```

---

## Task 2: Freeze ReviewResult and Fix In-Place Mutation

**Files:**
- Modify: `src/ado_ai_pr_review/models.py`
- Modify: `src/ado_ai_pr_review/engine.py`

Background: `engine.py` calls `result.findings.extend(request.local_findings)` in two places, mutating a `ReviewResult` object after construction. `ReviewResult` should be treated as a value object; merge must produce a new instance.

- [ ] **Step 1: Write a failing test for the immutability contract**

  Add to `tests/test_engine.py` (before the `_write_config` helper):
  ```python
  def test_review_result_is_value_object() -> None:
      from ado_ai_pr_review.models import Finding, FindingSeverity, FindingType, ReviewResult

      r = ReviewResult(summary="ok", findings=[])
      with pytest.raises(Exception):
          r.findings = []  # frozen model must reject attribute assignment
  ```

- [ ] **Step 2: Run the test to confirm it fails**

  ```bash
  uv run pytest tests/test_engine.py::test_review_result_is_value_object -v
  ```
  Expected: FAIL (no exception raised yet).

- [ ] **Step 3: Add `frozen=True` to ReviewResult in models.py**

  In `src/ado_ai_pr_review/models.py`, change:
  ```python
  class ReviewResult(BaseModel):
      model_config = ConfigDict(extra="forbid")
  ```
  to:
  ```python
  class ReviewResult(BaseModel):
      model_config = ConfigDict(extra="forbid", frozen=True)
  ```

- [ ] **Step 4: Run the new test to confirm it passes**

  ```bash
  uv run pytest tests/test_engine.py::test_review_result_is_value_object -v
  ```
  Expected: PASS.

- [ ] **Step 5: Fix the two `.extend()` mutations in engine.py**

  In `src/ado_ai_pr_review/engine.py`, change line 98:
  ```python
  result.findings.extend(request.local_findings)
  self._platform.publish_review(result)
  ```
  to:
  ```python
  merged = ReviewResult(
      summary=result.summary,
      findings=[*result.findings, *request.local_findings],
  )
  self._platform.publish_review(merged)
  ```
  Add the `ReviewResult` import to the `from ado_ai_pr_review.models import ...` block at the top of engine.py (it's already there — just confirm).

  Also change line 120:
  ```python
  result.findings.extend(request.local_findings)
  ```
  to:
  ```python
  result = ReviewResult(
      summary=result.summary,
      findings=[*result.findings, *request.local_findings],
  )
  ```

- [ ] **Step 6: Run full test suite**

  ```bash
  uv run pytest -x -q
  ```
  Expected: all tests pass.

- [ ] **Step 7: Commit**

  ```bash
  git add src/ado_ai_pr_review/models.py src/ado_ai_pr_review/engine.py tests/test_engine.py
  git commit -m "refactor: freeze ReviewResult and eliminate in-place findings mutation"
  ```

---

## Task 3: Add GitPort and AdoApiPort to ports.py

**Files:**
- Modify: `src/ado_ai_pr_review/ports.py`
- Modify: `src/ado_ai_pr_review/fixer.py` (type hint update only)

Background: `MechanicalFixer` currently accepts the concrete `GitToolset | None` and `AdoToolset | None`. We define minimal Protocols so the fixer depends on abstractions, not concretions. Since Python uses structural typing for Protocols, `GitToolset` and `AdoToolset` already satisfy them without any changes to those classes.

- [ ] **Step 1: Write a test confirming GitToolset satisfies GitPort**

  Add to `tests/test_ports.py` at the end:
  ```python
  def test_git_toolset_satisfies_git_port() -> None:
      from ado_ai_pr_review.git_toolset import GitToolset
      from ado_ai_pr_review.ports import GitPort
      from unittest.mock import MagicMock
      from pathlib import Path

      # Runtime structural subtype check via Protocol
      assert isinstance(GitToolset(runner=MagicMock(), repo_root=Path(".")), GitPort)


  def test_ado_toolset_satisfies_ado_api_port() -> None:
      from ado_ai_pr_review.ado_toolset import AdoToolset
      from ado_ai_pr_review.ports import AdoApiPort
      from unittest.mock import MagicMock

      assert isinstance(AdoToolset(rest_client=MagicMock(), context=MagicMock()), AdoApiPort)
  ```

- [ ] **Step 2: Run the tests to confirm they fail**

  ```bash
  uv run pytest tests/test_ports.py::test_git_toolset_satisfies_git_port tests/test_ports.py::test_ado_toolset_satisfies_ado_api_port -v
  ```
  Expected: FAIL (`GitPort` and `AdoApiPort` not yet defined).

- [ ] **Step 3: Add GitPort and AdoApiPort to ports.py**

  Append to `src/ado_ai_pr_review/ports.py` after the existing `LLMPort` class:
  ```python
  from collections.abc import Sequence


  class GitPort(Protocol):
      def checkout_new_branch(self, branch: str) -> object: ...
      def add(self, paths: Sequence[str]) -> object: ...
      def commit(self, message: str) -> str: ...
      def push(self, remote: str, branch: str) -> object: ...


  class AdoApiPort(Protocol):
      def create_pr(
          self,
          source_branch: str,
          target_branch: str,
          title: str,
          description: str,
      ) -> object: ...
  ```

  Also add `from collections.abc import Sequence` at the top of ports.py (if not already present — it isn't, so add it after `from typing import Protocol`).

- [ ] **Step 4: Run the new tests to confirm they pass**

  ```bash
  uv run pytest tests/test_ports.py -v
  ```
  Expected: all pass.

- [ ] **Step 5: Update MechanicalFixer type hints in fixer.py**

  In `src/ado_ai_pr_review/fixer.py`, change the import block from:
  ```python
  from ado_ai_pr_review.ado_toolset import AdoToolset
  from ado_ai_pr_review.git_toolset import GitToolset
  ```
  to:
  ```python
  from ado_ai_pr_review.ports import AdoApiPort, GitPort
  ```

  Change the `__init__` signature:
  ```python
  def __init__(self, git_toolset: GitToolset | None, ado_toolset: AdoToolset | None, repo_root: Path | None = None) -> None:
  ```
  Keep the body the same for now (it will be fully rewritten in Task 4). This is just a type-annotation pass. Change to:
  ```python
  def __init__(self, git_toolset: GitPort | None, ado_toolset: AdoApiPort | None, repo_root: Path | None = None) -> None:
  ```

- [ ] **Step 6: Run full test suite**

  ```bash
  uv run pytest -x -q
  ```
  Expected: all tests pass.

- [ ] **Step 7: Commit**

  ```bash
  git add src/ado_ai_pr_review/ports.py src/ado_ai_pr_review/fixer.py tests/test_ports.py
  git commit -m "refactor: add GitPort and AdoApiPort protocols; update MechanicalFixer type hints"
  ```

---

## Task 4: Refactor MechanicalFixer — Eliminate None Dependencies and Duplication

**Files:**
- Modify: `src/ado_ai_pr_review/fixer.py`
- Modify: `src/ado_ai_pr_review/adapters/local.py`
- Modify: `src/ado_ai_pr_review/adapters/webhook.py`
- Modify: `tests/test_fixer.py`
- Modify: `tests/test_local_adapter.py`

Background: Currently `MechanicalFixer` accepts `None` for all deps so that `LocalCliAdapter` can call `is_allowed()` without a git/ado connection. Additionally, `LocalCliAdapter.create_fix_branch()` duplicates the checkout-write-commit loop from `MechanicalFixer.create_fix_branch()`. The fix:
1. Extract `MechanicalFixPolicy` (only `is_allowed`, no deps).
2. Rewrite `MechanicalFixer` to require `git: GitPort` and `repo_root: Path`, no `ado_toolset`. It exposes `apply_commits(candidates, branch_name, policy) -> list[str]` — checkout + write + commit, returns SHA list. No push, no PR creation.
3. Move push + PR creation into `AdoWebhookAdapter.create_fix_branch()`.
4. Rewrite `LocalCliAdapter.create_fix_branch()` to use the shared `apply_commits()`.

- [ ] **Step 1: Write tests for the new MechanicalFixPolicy and MechanicalFixer.apply_commits**

  Replace the entire content of `tests/test_fixer.py` with:
  ```python
  from pathlib import Path
  from typing import cast

  import pytest
  from pytest_mock import MockerFixture

  from ado_ai_pr_review.fixer import MechanicalFixPolicy, MechanicalFixer
  from ado_ai_pr_review.models import FixCandidate, FixDelivery


  def _candidate(
      title: str = "Format imports",
      explanation: str = "Import cleanup.",
      file_path: str = "src/app.py",
      replacement: str = "import os\n",
      commit_message: str = "fix: format imports",
      delivery: FixDelivery = FixDelivery.FIX_BRANCH_CANDIDATE,
  ) -> FixCandidate:
      return FixCandidate(
          delivery=delivery,
          title=title,
          explanation=explanation,
          file_path=file_path,
          replacement=replacement,
          commit_message=commit_message,
      )


  # --- MechanicalFixPolicy ---

  def test_policy_rejects_business_logic_candidate() -> None:
      policy = MechanicalFixPolicy()
      assert policy.is_allowed(_candidate(title="Rewrite pricing logic", explanation="Change discount behavior.")) is False


  def test_policy_allows_mechanical_candidate() -> None:
      policy = MechanicalFixPolicy()
      assert policy.is_allowed(_candidate(title="Format imports", explanation="Import cleanup.")) is True


  # --- MechanicalFixer.apply_commits ---

  def test_fixer_creates_one_commit_per_branch_candidate(mocker: MockerFixture, tmp_path: Path) -> None:
      git = mocker.Mock()
      git.commit.return_value = "abc1234"
      (tmp_path / "src").mkdir()

      fixer = MechanicalFixer(git=git, repo_root=tmp_path)
      policy = MechanicalFixPolicy()
      shas = fixer.apply_commits(
          candidates=[_candidate()],
          branch_name="ai-fix/pr-42/9001",
          policy=policy,
      )

      assert shas == ["abc1234"]
      git.checkout_new_branch.assert_called_once_with("ai-fix/pr-42/9001")
      git.commit.assert_called_once_with("fix: format imports")


  def test_fixer_raises_when_no_commits_produced(mocker: MockerFixture, tmp_path: Path) -> None:
      git = mocker.Mock()
      fixer = MechanicalFixer(git=git, repo_root=tmp_path)
      policy = MechanicalFixPolicy()
      # A candidate that fails is_allowed (business logic)
      candidates = [_candidate(title="Rewrite pricing logic", explanation="Change discount behavior.")]

      with pytest.raises(RuntimeError, match="No mechanical candidates"):
          fixer.apply_commits(candidates, branch_name="ai-fix/pr-42/9001", policy=policy)


  def test_fixer_rejects_candidate_path_outside_repo(mocker: MockerFixture, tmp_path: Path) -> None:
      git = mocker.Mock()
      fixer = MechanicalFixer(git=git, repo_root=tmp_path)
      policy = MechanicalFixPolicy()
      candidates = [_candidate(file_path="../other-repo/app.py")]

      with pytest.raises(RuntimeError, match="No mechanical candidates"):
          fixer.apply_commits(candidates, branch_name="ai-fix/pr-42/1", policy=policy)

      git.add.assert_not_called()


  def test_fixer_rejects_symlink_write_target(mocker: MockerFixture, tmp_path: Path) -> None:
      outside = tmp_path.parent / "outside.py"
      outside.write_text("print('outside')\n", encoding="utf-8")
      (tmp_path / "src").mkdir()
      (tmp_path / "src" / "app.py").symlink_to(outside)
      git = mocker.Mock()
      fixer = MechanicalFixer(git=git, repo_root=tmp_path)
      policy = MechanicalFixPolicy()
      candidates = [_candidate(file_path="src/app.py")]

      with pytest.raises(RuntimeError, match="No mechanical candidates"):
          fixer.apply_commits(candidates, branch_name="ai-fix/pr-42/1", policy=policy)

      assert outside.read_text(encoding="utf-8") == "print('outside')\n"
  ```

- [ ] **Step 2: Run the tests to confirm they fail**

  ```bash
  uv run pytest tests/test_fixer.py -v
  ```
  Expected: FAIL (`MechanicalFixPolicy` not defined, `apply_commits` not found).

- [ ] **Step 3: Rewrite fixer.py with the new design**

  Replace the entire content of `src/ado_ai_pr_review/fixer.py`:
  ```python
  from __future__ import annotations

  import logging
  from pathlib import Path

  from ado_ai_pr_review.errors import WorkspaceBoundaryError
  from ado_ai_pr_review.models import FixCandidate, FixDelivery
  from ado_ai_pr_review.ports import GitPort
  from ado_ai_pr_review.workspace import WorkspaceBoundary

  logger = logging.getLogger(__name__)

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


  class MechanicalFixPolicy:
      """Stateless allow/deny policy for fix candidates. No I/O, no dependencies."""

      def is_allowed(self, candidate: FixCandidate) -> bool:
          text = f"{candidate.title} {candidate.explanation} {candidate.commit_message or ''}".lower()
          if any(word in text for word in ["business", "pricing", "discount", "authorization behavior"]):
              return False
          return any(word in text for word in MECHANICAL_WORDS)


  class MechanicalFixer:
      """Applies mechanical fix candidates: checkout branch, write files, commit.

      Does NOT push or create a PR — that responsibility belongs to the adapter.
      """

      def __init__(self, git: GitPort, repo_root: Path) -> None:
          self._git = git
          self._repo_root = repo_root

      def apply_commits(
          self,
          candidates: list[FixCandidate],
          branch_name: str,
          policy: MechanicalFixPolicy,
      ) -> list[str]:
          """Checkout branch, apply allowed candidates, return list of commit SHAs.

          Raises RuntimeError if no candidates produce a commit.
          """
          workspace = WorkspaceBoundary(self._repo_root)
          self._git.checkout_new_branch(branch_name)
          commit_shas: list[str] = []
          for candidate in candidates:
              if candidate.delivery is not FixDelivery.FIX_BRANCH_CANDIDATE:
                  continue
              if not policy.is_allowed(candidate):
                  continue
              if not candidate.file_path or candidate.replacement is None or not candidate.commit_message:
                  continue
              try:
                  workspace.safe_write_text(candidate.file_path, candidate.replacement)
              except WorkspaceBoundaryError:
                  logger.warning("skipping unsafe fix candidate: %s", candidate.file_path)
                  continue
              self._git.add([candidate.file_path])
              commit_shas.append(self._git.commit(candidate.commit_message))
          if not commit_shas:
              raise RuntimeError("No mechanical candidates produced commits; fix branch aborted")
          return commit_shas
  ```

- [ ] **Step 4: Run fixer tests**

  ```bash
  uv run pytest tests/test_fixer.py -v
  ```
  Expected: all pass.

- [ ] **Step 5: Update AdoWebhookAdapter.create_fix_branch in adapters/webhook.py**

  Change the `create_fix_branch` method (lines 299-315) to:
  ```python
  def create_fix_branch(
      self,
      candidates: list[FixCandidate],
      branch_name: str,
      target_branch: str,
  ) -> bool:
      from ado_ai_pr_review.fixer import MechanicalFixer, MechanicalFixPolicy

      policy = MechanicalFixPolicy()
      fixer = MechanicalFixer(git=self._git, repo_root=self._temp_dir)
      try:
          shas = fixer.apply_commits(candidates, branch_name, policy)
      except RuntimeError as exc:
          logger.warning("fix branch not created: %s", exc)
          return False
      self._git.push("origin", branch_name)
      description = "Mechanical AI fix branch.\n\nCherry-pick commits:\n" + "\n".join(
          f"- `git cherry-pick {sha}`" for sha in shas
      )
      self._ado.create_pr(
          source_branch=branch_name,
          target_branch=target_branch,
          title="AI mechanical fixes",
          description=description,
      )
      return True
  ```

  Also remove the `MechanicalFixer` import from the top of webhook.py (line `from ado_ai_pr_review.fixer import MechanicalFixer`). The inline import in the method is sufficient.

- [ ] **Step 6: Update LocalCliAdapter.create_fix_branch in adapters/local.py**

  Replace the `create_fix_branch` method (lines 81-119):
  ```python
  def create_fix_branch(
      self,
      candidates: list[FixCandidate],
      branch_name: str,
      target_branch: str,  # not used in local mode — no remote push
  ) -> bool:
      from ado_ai_pr_review.fixer import MechanicalFixer, MechanicalFixPolicy

      policy = MechanicalFixPolicy()
      fixer = MechanicalFixer(git=self._git, repo_root=self._repo_root)
      try:
          shas = fixer.apply_commits(candidates, branch_name, policy)
      except RuntimeError:
          typer.echo("No mechanical fix candidates.")
          return False
      for sha in shas:
          typer.echo(f"  {sha[:8]}")
      typer.echo(f"Fix branch '{branch_name}' created locally (not pushed).")
      return False
  ```

  Also remove the now-unused imports from the top of local.py:
  - Remove: `from ado_ai_pr_review.errors import WorkspaceBoundaryError`
  - Remove: `from ado_ai_pr_review.fixer import MechanicalFixer`
  - Remove: `from ado_ai_pr_review.workspace import WorkspaceBoundary`
  - Keep: `from ado_ai_pr_review.models import FixCandidate, FixDelivery, ReviewCommand, ReviewResult`
  - Remove `FixDelivery` from that import (no longer needed directly in local.py)

- [ ] **Step 7: Update test_local_adapter.py — fix the create_fix_branch test**

  The test `test_local_adapter_create_fix_branch_commits_and_returns_false` checks that `git.checkout_new_branch`, `git.add`, and `git.commit` are called. It should still pass because the logic now goes through `MechanicalFixer.apply_commits`. Run it:

  ```bash
  uv run pytest tests/test_local_adapter.py -v
  ```
  Expected: all pass. If any fail, they're due to import errors — fix the import list accordingly.

- [ ] **Step 8: Run full test suite**

  ```bash
  uv run pytest -x -q
  ```
  Expected: all tests pass.

- [ ] **Step 9: Commit**

  ```bash
  git add src/ado_ai_pr_review/fixer.py src/ado_ai_pr_review/adapters/local.py src/ado_ai_pr_review/adapters/webhook.py tests/test_fixer.py tests/test_local_adapter.py
  git commit -m "refactor: extract MechanicalFixPolicy; fixer.apply_commits eliminates LocalCliAdapter duplication"
  ```

---

## Task 5: Extract Webhook Payload Models to webhook_payload.py

**Files:**
- Create: `src/ado_ai_pr_review/adapters/webhook_payload.py`
- Modify: `src/ado_ai_pr_review/adapters/webhook.py`
- Modify: `tests/test_webhook_adapter.py`

Background: `adapters/webhook.py` is 326 lines and mixes 7 Pydantic payload models with adapter behaviour. The models have no dependency on the adapter — move them to their own file.

- [ ] **Step 1: Create adapters/webhook_payload.py**

  Create `src/ado_ai_pr_review/adapters/webhook_payload.py` with all payload model code (cut from webhook.py lines 1-183):
  ```python
  from __future__ import annotations

  import re
  from typing import Any

  from pydantic import BaseModel, ConfigDict, Field, model_validator


  class _RepoProject(BaseModel):
      model_config = ConfigDict(extra="allow")
      name: str = ""


  class _Repository(BaseModel):
      model_config = ConfigDict(extra="allow")
      id: str = ""
      name: str = ""
      remote_url: str = Field(default="", alias="remoteUrl")
      project: _RepoProject = Field(default_factory=_RepoProject)


  class _PullRequestResource(BaseModel):
      model_config = ConfigDict(extra="allow")
      pull_request_id: int = Field(alias="pullRequestId")
      source_ref_name: str = Field(default="", alias="sourceRefName")
      target_ref_name: str = Field(default="", alias="targetRefName")
      repository: _Repository = Field(default_factory=_Repository)


  class _Comment(BaseModel):
      model_config = ConfigDict(extra="allow")
      content: str = ""


  class _SelfLink(BaseModel):
      model_config = ConfigDict(extra="allow")
      href: str = ""


  class _ResourceLinks(BaseModel):
      """Captures _links from flat-comment event payloads."""

      model_config = ConfigDict(extra="allow")
      pull_requests: _SelfLink = Field(default_factory=_SelfLink, alias="pullRequests")
      repository: _SelfLink = Field(default_factory=_SelfLink)

      def pr_id(self) -> int | None:
          m = re.search(r"/pullRequests/(\d+)", self.pull_requests.href)
          return int(m.group(1)) if m else None

      def repo_id(self) -> str:
          m = re.search(r"/repositories/([a-f0-9\-]+)", self.repository.href)
          return m.group(1) if m else ""


  class _Resource(BaseModel):
      model_config = ConfigDict(extra="allow")
      pull_request_id: int | None = Field(default=None, alias="pullRequestId")
      source_ref_name: str | None = Field(default=None, alias="sourceRefName")
      target_ref_name: str | None = Field(default=None, alias="targetRefName")
      repository: _Repository | None = None
      pull_request: _PullRequestResource | None = Field(default=None, alias="pullRequest")
      comment: _Comment | None = None
      content: str | None = None
      links: _ResourceLinks = Field(default_factory=_ResourceLinks, alias="_links")


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
          pr_id = self.resource.links.pr_id()
          if pr_id is not None:
              return pr_id
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
      def repository_id(self) -> str:
          repo = self.resource.pull_request.repository if self.resource.pull_request else self.resource.repository
          if repo and repo.id:
              return repo.id
          return self.resource.links.repo_id()

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
          if self.resource.content:
              return self.resource.content
          return None

      @property
      def is_flat_comment_event(self) -> bool:
          """True when the payload is a flat-comment event (resource = the comment itself)."""
          return (
              self.resource.pull_request is None
              and self.resource.pull_request_id is None
              and self.resource.links.pr_id() is not None
          )
  ```

- [ ] **Step 2: Rewrite webhook.py to import from webhook_payload and keep only AdoWebhookAdapter**

  Replace the Pydantic model block (lines 1-183) in `src/ado_ai_pr_review/adapters/webhook.py` with a single import:
  ```python
  from ado_ai_pr_review.adapters.webhook_payload import AdoWebhookPayload
  ```

  Remove these imports that were only used by the payload models:
  - `import re`
  - `from pydantic import BaseModel, ConfigDict, Field, model_validator`

  Keep `from typing import Any, cast` and all other imports.

  The full new header of webhook.py should be:
  ```python
  from __future__ import annotations

  import contextlib
  import logging
  from pathlib import Path
  from typing import Any, cast

  from ado_ai_pr_review.ado_context import AdoContext
  from ado_ai_pr_review.ado_rest import AdoRestClient
  from ado_ai_pr_review.ado_toolset import AdoToolset
  from ado_ai_pr_review.adapters.webhook_payload import AdoWebhookPayload
  from ado_ai_pr_review.auth import AdoAuthStrategy
  from ado_ai_pr_review.cli_runner import CliRunner
  from ado_ai_pr_review.commands import CommandRouter
  from ado_ai_pr_review.git_toolset import GitToolset
  from ado_ai_pr_review.models import FixCandidate, ReviewCommand, ReviewResult
  from ado_ai_pr_review.ports import PRContext, ReviewRequest
  from ado_ai_pr_review.publisher import SuggestionPublisher
  from ado_ai_pr_review.security import SecurityScanner
  from ado_ai_pr_review.tool_policy import CommandPolicy

  logger = logging.getLogger(__name__)
  ```

- [ ] **Step 3: Update test_webhook_adapter.py imports**

  In `tests/test_webhook_adapter.py`, change line 9:
  ```python
  from ado_ai_pr_review.adapters.webhook import AdoWebhookAdapter, AdoWebhookPayload
  ```
  to:
  ```python
  from ado_ai_pr_review.adapters.webhook import AdoWebhookAdapter
  from ado_ai_pr_review.adapters.webhook_payload import AdoWebhookPayload
  ```

- [ ] **Step 4: Also update webhook_server.py import**

  In `src/ado_ai_pr_review/webhook_server.py`, change line 16:
  ```python
  from ado_ai_pr_review.adapters.webhook import AdoWebhookAdapter, AdoWebhookPayload
  ```
  to:
  ```python
  from ado_ai_pr_review.adapters.webhook import AdoWebhookAdapter
  from ado_ai_pr_review.adapters.webhook_payload import AdoWebhookPayload
  ```

- [ ] **Step 5: Run full test suite**

  ```bash
  uv run pytest -x -q
  ```
  Expected: all tests pass.

- [ ] **Step 6: Commit**

  ```bash
  git add src/ado_ai_pr_review/adapters/webhook_payload.py src/ado_ai_pr_review/adapters/webhook.py src/ado_ai_pr_review/webhook_server.py tests/test_webhook_adapter.py
  git commit -m "refactor: extract AdoWebhookPayload models to webhook_payload.py"
  ```

---

## Task 6: Move AdoWebhookAdapter I/O from Constructor to load_request()

**Files:**
- Modify: `src/ado_ai_pr_review/adapters/webhook.py`
- Modify: `tests/test_webhook_adapter.py`

Background: `AdoWebhookAdapter.__init__` currently makes an HTTP REST call and shells out `git clone`. This means the adapter is untestable without 4 mocked patches and can raise from a constructor. The fix: `__init__` stores inputs and creates cheap CliRunner + AdoRestClient. All I/O moves into `load_request()`.

- [ ] **Step 1: Rewrite AdoWebhookAdapter in webhook.py**

  Replace the entire `AdoWebhookAdapter` class with:
  ```python
  class AdoWebhookAdapter:
      def __init__(
          self,
          payload: AdoWebhookPayload,
          auth_strategy: AdoAuthStrategy,
          temp_dir: Path,
          request_id: str = "unknown",
      ) -> None:
          self._payload = payload
          self._auth_strategy = auth_strategy
          self._temp_dir = temp_dir
          self._request_id = request_id
          # These two are cheap (no I/O).
          self._runner = CliRunner(policy=CommandPolicy.default(), secrets=list(auth_strategy.secret_values()))
          self._rest_client = AdoRestClient(auth=auth_strategy)
          # Set after load_request() is called.
          self._git: GitToolset | None = None
          self._ado: AdoToolset | None = None
          self._publisher: SuggestionPublisher | None = None
          self._source_ref: str = ""
          self._target_ref: str = ""

      def load_request(self) -> ReviewRequest:
          payload = self._payload

          # For flat-comment events, fetch PR details to get repo/branch info.
          if payload.is_flat_comment_event:
              org = payload.organization_url.rstrip("/")
              if payload.repository_id:
                  url = f"{org}/_apis/git/repositories/{payload.repository_id}/pullRequests/{payload.pull_request_id}?api-version=7.0"
              else:
                  url = f"{org}/_apis/git/pullRequests/{payload.pull_request_id}?api-version=7.0"
              try:
                  pr_details = cast(dict[str, Any], self._rest_client.request_json(method="GET", url=url))
              except Exception as exc:
                  logger.error("Failed to fetch PR details: %s", exc, exc_info=True)
                  pr_details = {}
          else:
              pr_details = {}

          self._source_ref = payload.source_ref_name or pr_details.get("sourceRefName", "")
          self._target_ref = payload.target_ref_name or pr_details.get("targetRefName", "")
          repo_info: dict[str, Any] = pr_details.get("repository", {})
          remote_url = payload.remote_url or repo_info.get("remoteUrl", "")
          repo_name = payload.repository_name or repo_info.get("name", "")
          repo_id = payload.repository_id or repo_info.get("id", "")
          project_name = payload.project_name or repo_info.get("project", {}).get("name", "")

          # Clone the source branch.
          source_branch = self._source_ref.removeprefix("refs/heads/")
          self._git = GitToolset(runner=self._runner, repo_root=self._temp_dir)
          self._git.clone(
              remote_url=remote_url,
              branch=source_branch,
              destination=self._temp_dir,
              auth_strategy=self._auth_strategy,
          )

          # Wire up ADO toolset and publisher.
          context = AdoContext(
              repo_root=self._temp_dir,
              organization_url=payload.organization_url,
              project=project_name,
              repository_id=repo_id,
              repository_name=repo_name,
              pull_request_id=payload.pull_request_id,
              source_branch=self._source_ref,
              target_branch=self._target_ref,
              is_fork=False,
              run_id="webhook",
          )
          self._ado = AdoToolset(rest_client=self._rest_client, context=context)
          self._publisher = SuggestionPublisher(ado_toolset=self._ado)

          # Detect command from inline comment or PR threads.
          if payload.inline_command is not None:
              command = CommandRouter.detect_command(payload.inline_command)
              if command is None:
                  command = ReviewCommand.SKIP
          else:
              threads = cast(dict[str, Any], self._ado.list_pr_threads())
              decision = CommandRouter().route(threads)
              command = decision.command

          if command in (ReviewCommand.ONBOARDING, ReviewCommand.SKIP):
              return ReviewRequest(
                  repo_root=self._temp_dir,
                  diff_text="",
                  local_findings=(),
                  command=command,
                  pr_context=self._make_pr_context(),
              )

          target_ref = self._target_ref.removeprefix("refs/heads/")
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
          if self._publisher is not None:
              self._publisher.publish_onboarding()

      def publish_review(self, result: ReviewResult) -> None:
          if self._publisher is not None:
              self._publisher.publish_review(result)

      def publish_error(self, exc: BaseException) -> None:
          logger.error("webhook review failed: %s", exc, exc_info=True)
          if self._ado is not None:
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
          if self._git is None or self._ado is None:
              logger.warning("create_fix_branch called before load_request(); skipping")
              return False
          from ado_ai_pr_review.fixer import MechanicalFixer, MechanicalFixPolicy

          policy = MechanicalFixPolicy()
          fixer = MechanicalFixer(git=self._git, repo_root=self._temp_dir)
          try:
              shas = fixer.apply_commits(candidates, branch_name, policy)
          except RuntimeError as exc:
              logger.warning("fix branch not created: %s", exc)
              return False
          self._git.push("origin", branch_name)
          description = "Mechanical AI fix branch.\n\nCherry-pick commits:\n" + "\n".join(
              f"- `git cherry-pick {sha}`" for sha in shas
          )
          self._ado.create_pr(
              source_branch=branch_name,
              target_branch=target_branch,
              title="AI mechanical fixes",
              description=description,
          )
          return True

      def _make_pr_context(self) -> PRContext:
          return PRContext(
              pr_id=self._payload.pull_request_id,
              source_branch=self._source_ref,
              target_branch=self._target_ref,
              is_fork=False,
              run_id="webhook",
              request_id=self._request_id,
          )
  ```

- [ ] **Step 2: Update test_webhook_adapter.py — adapter test must call load_request()**

  The test `test_webhook_adapter_clones_with_auth_strategy_not_url_token` currently constructs the adapter and asserts `clone` was called. After this refactor, clone happens in `load_request()`. Rewrite the test:

  Replace the test `test_webhook_adapter_clones_with_auth_strategy_not_url_token` (lines 93-108) with:
  ```python
  def test_webhook_adapter_load_request_clones_with_auth_strategy(mocker: MockerFixture, tmp_path: Path) -> None:
      payload = AdoWebhookPayload.model_validate(_PR_CREATED_PAYLOAD)
      runner_cls = mocker.patch("ado_ai_pr_review.adapters.webhook.CliRunner")
      git_cls = mocker.patch("ado_ai_pr_review.adapters.webhook.GitToolset")
      mocker.patch("ado_ai_pr_review.adapters.webhook.AdoToolset")
      mocker.patch("ado_ai_pr_review.adapters.webhook.AdoRestClient")
      mocker.patch("ado_ai_pr_review.adapters.webhook.SuggestionPublisher")
      mock_threads = {"value": []}
      git_cls.return_value.diff.return_value = ""
      ado_instance = mocker.patch("ado_ai_pr_review.adapters.webhook.AdoToolset").return_value
      ado_instance.list_pr_threads.return_value = mock_threads

      adapter = AdoWebhookAdapter(payload=payload, auth_strategy=FakeAuth(), temp_dir=tmp_path)

      # Constructor must be cheap — no clone yet.
      git_cls.return_value.clone.assert_not_called()

      adapter.load_request()

      runner_cls.assert_called_once()
      assert runner_cls.call_args.kwargs["secrets"] == ["entra-token"]
      git_cls.return_value.clone.assert_called_once()
      clone_kwargs = git_cls.return_value.clone.call_args.kwargs
      assert clone_kwargs["remote_url"] == "https://dev.azure.com/org/project/_git/MyRepo"
      assert "entra-token" not in clone_kwargs["remote_url"]
  ```

- [ ] **Step 3: Run full test suite**

  ```bash
  uv run pytest -x -q
  ```
  Expected: all tests pass.

- [ ] **Step 4: Commit**

  ```bash
  git add src/ado_ai_pr_review/adapters/webhook.py tests/test_webhook_adapter.py
  git commit -m "refactor: move AdoWebhookAdapter I/O from constructor to load_request()"
  ```

---

## Task 7: Extract build_llm Factory

**Files:**
- Create: `src/ado_ai_pr_review/llm/factory.py`
- Modify: `src/ado_ai_pr_review/cli.py`
- Modify: `src/ado_ai_pr_review/webhook_server.py`

Background: Both `cli.py` and `webhook_server.py` contain nearly identical `_build_model()` functions. Extract to a single `build_llm()` in `llm/factory.py`.

- [ ] **Step 1: Write a test for build_llm**

  Create `tests/test_llm_factory.py`:
  ```python
  import os
  import pytest
  from unittest.mock import patch, MagicMock


  def test_build_llm_returns_azure_openai_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
      monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
      monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/")

      with patch("ado_ai_pr_review.llm.factory.build_openai_client", return_value=MagicMock()):
          from ado_ai_pr_review.llm.factory import build_llm
          from ado_ai_pr_review.llm.azure_openai import ModelClient
          result = build_llm(None)

      assert isinstance(result, ModelClient)


  def test_build_llm_returns_copilot_client(monkeypatch: pytest.MonkeyPatch) -> None:
      with (
          patch("ado_ai_pr_review.llm.factory.CliRunner", return_value=MagicMock()),
          patch("ado_ai_pr_review.llm.factory.GitHubCopilotClient", return_value=MagicMock()) as mock_cls,
      ):
          from ado_ai_pr_review.llm.factory import build_llm
          result = build_llm("copilot")

      mock_cls.assert_called_once()
  ```

- [ ] **Step 2: Run the test to confirm it fails**

  ```bash
  uv run pytest tests/test_llm_factory.py -v
  ```
  Expected: FAIL (`build_llm` not yet defined).

- [ ] **Step 3: Create llm/factory.py**

  Create `src/ado_ai_pr_review/llm/factory.py`:
  ```python
  from __future__ import annotations

  import os

  from ado_ai_pr_review.llm.azure_openai import ModelClient, build_openai_client
  from ado_ai_pr_review.ports import LLMPort


  def build_llm(provider: str | None) -> LLMPort:
      """Construct the configured LLM client.

      Pass provider="copilot" for GitHub Copilot; None or "azure" for Azure OpenAI.
      """
      if provider == "copilot":
          from ado_ai_pr_review.cli_runner import CliRunner
          from ado_ai_pr_review.llm.github_copilot import GitHubCopilotClient
          from ado_ai_pr_review.tool_policy import CommandPolicy

          runner = CliRunner(policy=CommandPolicy.default())
          return GitHubCopilotClient(runner=runner)
      return ModelClient(
          openai_client=build_openai_client(),  # type: ignore[arg-type]
          deployment=os.environ["AZURE_OPENAI_DEPLOYMENT"],
      )
  ```

- [ ] **Step 4: Run the test**

  ```bash
  uv run pytest tests/test_llm_factory.py -v
  ```
  Expected: both tests pass.

- [ ] **Step 5: Update cli.py to use build_llm**

  In `src/ado_ai_pr_review/cli.py`:

  Replace the import:
  ```python
  from ado_ai_pr_review.llm.azure_openai import ModelClient, build_openai_client
  ```
  with:
  ```python
  from ado_ai_pr_review.llm.factory import build_llm
  ```

  In the `local()` command function, change:
  ```python
  model = _build_model(llm)
  ```
  to:
  ```python
  model = build_llm(llm)
  ```

  Delete the entire `_build_model` function (lines 59-72).

- [ ] **Step 6: Update webhook_server.py to use build_llm**

  In `src/ado_ai_pr_review/webhook_server.py`:

  Replace:
  ```python
  from ado_ai_pr_review.llm.azure_openai import ModelClient, build_openai_client
  ```
  with:
  ```python
  from ado_ai_pr_review.llm.factory import build_llm
  ```

  Remove the `LLMPort` import (it was only used by `_build_model`'s return type).

  Delete the `_build_model()` function (lines 28-39).

  In `_process_sync()`, change:
  ```python
  model = _build_model()
  ```
  to:
  ```python
  model = build_llm(os.getenv("LLM_PROVIDER"))
  ```

- [ ] **Step 7: Run full test suite**

  ```bash
  uv run pytest -x -q
  ```
  Expected: all tests pass.

- [ ] **Step 8: Commit**

  ```bash
  git add src/ado_ai_pr_review/llm/factory.py src/ado_ai_pr_review/cli.py src/ado_ai_pr_review/webhook_server.py tests/test_llm_factory.py
  git commit -m "refactor: extract build_llm factory to llm/factory.py; remove duplicate _build_model"
  ```

---

## Task 8: Move Bootstrap Check from Engine to LocalCliAdapter

**Files:**
- Modify: `src/ado_ai_pr_review/engine.py`
- Modify: `src/ado_ai_pr_review/adapters/local.py`
- Modify: `tests/test_engine.py`
- Modify: `tests/test_local_adapter.py`

Background: `ReviewEngine.run()` calls `Bootstrapper().create_missing_files()` before every request. This wastes I/O in webhook mode (temp_dir is discarded after) and couples the engine core to a local onboarding concern. Bootstrap belongs in `LocalCliAdapter.load_request()` — it can short-circuit to `ONBOARDING` if files are missing, before any diff is computed.

- [ ] **Step 1: Write a test for local adapter bootstrap detection**

  Add to `tests/test_local_adapter.py`:
  ```python
  def test_local_adapter_load_request_returns_onboarding_when_files_missing(tmp_path: Path) -> None:
      from ado_ai_pr_review.adapters.local import LocalCliAdapter
      from ado_ai_pr_review.models import ReviewCommand

      # tmp_path is empty — bootstrap files don't exist
      adapter = LocalCliAdapter(repo_root=tmp_path, command=ReviewCommand.REVIEW)
      request = adapter.load_request()

      assert request.command is ReviewCommand.ONBOARDING
      # Bootstrap files should have been created
      assert (tmp_path / ".ado-ai-review.yml").exists()
  ```

- [ ] **Step 2: Run the test to confirm it fails**

  ```bash
  uv run pytest tests/test_local_adapter.py::test_local_adapter_load_request_returns_onboarding_when_files_missing -v
  ```
  Expected: FAIL (bootstrap currently happens in engine, not adapter).

- [ ] **Step 3: Update LocalCliAdapter.load_request() to check bootstrap first**

  In `src/ado_ai_pr_review/adapters/local.py`, modify `load_request()`:
  ```python
  def load_request(self) -> ReviewRequest:
      from ado_ai_pr_review.bootstrap import Bootstrapper

      created = Bootstrapper().create_missing_files(self._repo_root)
      if created:
          return ReviewRequest(
              repo_root=self._repo_root,
              diff_text="",
              local_findings=(),
              command=ReviewCommand.ONBOARDING,
              pr_context=PRContext(
                  pr_id=None,
                  source_branch="unknown",
                  target_branch=self._target_branch,
                  is_fork=False,
                  run_id="local",
                  request_id=self._request_id,
              ),
          )

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
              run_id="local",
              request_id=self._request_id,
          ),
      )
  ```

- [ ] **Step 4: Run the new test**

  ```bash
  uv run pytest tests/test_local_adapter.py::test_local_adapter_load_request_returns_onboarding_when_files_missing -v
  ```
  Expected: PASS.

- [ ] **Step 5: Remove bootstrap from engine.run()**

  In `src/ado_ai_pr_review/engine.py`, remove lines 37-40:
  ```python
  created = Bootstrapper().create_missing_files(self._repo_root)
  if created:
      self._platform.publish_onboarding()
      return ReviewCommand.ONBOARDING
  ```

  Also remove the `Bootstrapper` import:
  ```python
  from ado_ai_pr_review.bootstrap import Bootstrapper
  ```

  The engine now trusts `load_request()` to return `ReviewCommand.ONBOARDING` when needed.

- [ ] **Step 6: Update test_engine.py — bootstrap-from-engine test must change**

  The test `test_engine_bootstraps_and_publishes_onboarding_when_files_created` passes an empty `tmp_path` and expects the engine to bootstrap. After this change, the engine doesn't do that — the adapter does. Update that test:

  ```python
  def test_engine_publishes_onboarding_for_onboarding_command(tmp_path: Path) -> None:
      """Engine should call publish_onboarding when load_request returns ONBOARDING command."""
      from ado_ai_pr_review.engine import ReviewEngine

      _write_config(tmp_path)
      request = _make_request(command=ReviewCommand.ONBOARDING, repo_root=tmp_path)
      platform = _MockPlatform(request=request)
      engine = ReviewEngine(platform=platform, model=_MockLLM(), repo_root=tmp_path)
      cmd = engine.run()

      assert cmd is ReviewCommand.ONBOARDING
      assert platform.onboarding_called
  ```

  Remove the old `test_engine_bootstraps_and_publishes_onboarding_when_files_created` test entirely (it tested engine bootstrapping, which no longer happens).

- [ ] **Step 7: Run full test suite**

  ```bash
  uv run pytest -x -q
  ```
  Expected: all tests pass.

- [ ] **Step 8: Commit**

  ```bash
  git add src/ado_ai_pr_review/engine.py src/ado_ai_pr_review/adapters/local.py tests/test_engine.py tests/test_local_adapter.py
  git commit -m "refactor: move bootstrap check from engine to LocalCliAdapter.load_request()"
  ```

---

## Task 9: Command Handler Dispatch — OCP Fix in Engine

**Files:**
- Create: `src/ado_ai_pr_review/handlers/__init__.py`
- Create: `src/ado_ai_pr_review/handlers/base.py`
- Create: `src/ado_ai_pr_review/handlers/review.py`
- Create: `src/ado_ai_pr_review/handlers/fix.py`
- Create: `src/ado_ai_pr_review/handlers/onboarding.py`
- Create: `src/ado_ai_pr_review/handlers/skip.py`
- Modify: `src/ado_ai_pr_review/engine.py`
- Modify: `tests/test_engine.py`

Background: `ReviewEngine.run()` has a 5-way `if request.command is ...` dispatch table and a separate `_run_fix()` method. Adding a new review mode requires modifying the engine. Instead, each command gets a handler class; the engine looks up the handler by command.

- [ ] **Step 1: Create handlers/base.py with the Protocol and shared context helper**

  Create `src/ado_ai_pr_review/handlers/__init__.py` (empty):
  ```python
  ```

  Create `src/ado_ai_pr_review/handlers/base.py`:
  ```python
  from __future__ import annotations

  from pathlib import Path
  from typing import Protocol

  from ado_ai_pr_review.config import ReviewConfig
  from ado_ai_pr_review.context import ContextSelector
  from ado_ai_pr_review.indexer import RepoIndexer
  from ado_ai_pr_review.models import ReviewCommand, SelectedContext
  from ado_ai_pr_review.ports import LLMPort, PlatformAdapter, ReviewRequest


  class CommandHandler(Protocol):
      def handle(
          self,
          request: ReviewRequest,
          platform: PlatformAdapter,
          model: LLMPort,
          config: ReviewConfig,
      ) -> None: ...


  def select_context(
      request: ReviewRequest,
      config: ReviewConfig,
      primary_instruction: Path,
      prefer_tags: frozenset[str] = frozenset(),
  ) -> SelectedContext:
      entries = RepoIndexer(exclude=config.context.index.exclude).build(request.repo_root)
      selector = ContextSelector(max_files=config.context.dynamic_context.max_files)
      return selector.select(
          repo_root=request.repo_root,
          guidance_paths=[
              primary_instruction,
              *config.guidelines.code_style,
              *config.guidelines.security,
          ],
          entries=entries,
          prefer_tags=prefer_tags,
      )
  ```

- [ ] **Step 2: Create handlers/onboarding.py and handlers/skip.py**

  Create `src/ado_ai_pr_review/handlers/onboarding.py`:
  ```python
  from __future__ import annotations

  from ado_ai_pr_review.config import ReviewConfig
  from ado_ai_pr_review.ports import LLMPort, PlatformAdapter, ReviewRequest


  class OnboardingHandler:
      def handle(
          self,
          request: ReviewRequest,
          platform: PlatformAdapter,
          model: LLMPort,
          config: ReviewConfig,
      ) -> None:
          platform.publish_onboarding()
  ```

  Create `src/ado_ai_pr_review/handlers/skip.py`:
  ```python
  from __future__ import annotations

  import logging

  from ado_ai_pr_review.config import ReviewConfig
  from ado_ai_pr_review.ports import LLMPort, PlatformAdapter, ReviewRequest

  logger = logging.getLogger(__name__)


  class SkipHandler:
      def handle(
          self,
          request: ReviewRequest,
          platform: PlatformAdapter,
          model: LLMPort,
          config: ReviewConfig,
      ) -> None:
          logger.debug("skipping event: unrecognised inline comment, no action taken")
  ```

- [ ] **Step 3: Create handlers/review.py for REVIEW and SECURITY commands**

  Create `src/ado_ai_pr_review/handlers/review.py`:
  ```python
  from __future__ import annotations

  import logging

  from ado_ai_pr_review.config import ReviewConfig
  from ado_ai_pr_review.handlers.base import select_context
  from ado_ai_pr_review.models import ReviewCommand, ReviewResult
  from ado_ai_pr_review.observability import ReviewMetrics
  from ado_ai_pr_review.ports import LLMPort, PlatformAdapter, ReviewRequest
  from ado_ai_pr_review.reviewer import ReviewOrchestrator

  logger = logging.getLogger(__name__)


  def _run(
      command: ReviewCommand,
      request: ReviewRequest,
      platform: PlatformAdapter,
      model: LLMPort,
      config: ReviewConfig,
  ) -> None:
      prefer_tags: frozenset[str] = frozenset({"security"}) if command is ReviewCommand.SECURITY else frozenset()
      primary_instruction = (
          config.instructions.security if command is ReviewCommand.SECURITY else config.instructions.reviewer
      )
      selected = select_context(request, config, primary_instruction, prefer_tags)
      local_security_summary = f"Local findings: {len(request.local_findings)}"

      try:
          result = ReviewOrchestrator(model).run(
              command=command,
              guidance=selected.always_on_guidance,
              selected_files=selected.dynamic_files,
              diff_text=request.diff_text,
              local_security_summary=local_security_summary,
          )
      except Exception as exc:
          logger.error("review failed: %s", exc)
          platform.publish_error(exc)
          raise

      merged = ReviewResult(
          summary=result.summary,
          findings=[*result.findings, *request.local_findings],
      )
      platform.publish_review(merged)

      metrics = ReviewMetrics(
          command=command.value,
          pr_id=request.pr_context.pr_id or 0,
          findings_count=len(merged.findings),
          inline_suggestions_count=sum(1 for f in merged.findings if f.suggested_code),
          fix_pr_created=False,
      )
      logger.info("review metrics", extra=metrics.to_payload())


  class ReviewHandler:
      def handle(self, request: ReviewRequest, platform: PlatformAdapter, model: LLMPort, config: ReviewConfig) -> None:
          _run(ReviewCommand.REVIEW, request, platform, model, config)


  class SecurityHandler:
      def handle(self, request: ReviewRequest, platform: PlatformAdapter, model: LLMPort, config: ReviewConfig) -> None:
          _run(ReviewCommand.SECURITY, request, platform, model, config)
  ```

- [ ] **Step 4: Create handlers/fix.py**

  Create `src/ado_ai_pr_review/handlers/fix.py`:
  ```python
  from __future__ import annotations

  import logging

  from ado_ai_pr_review.config import ReviewConfig
  from ado_ai_pr_review.handlers.base import select_context
  from ado_ai_pr_review.models import FindingType, FixCandidate, FixDelivery, ReviewCommand, ReviewResult
  from ado_ai_pr_review.observability import ReviewMetrics
  from ado_ai_pr_review.ports import LLMPort, PlatformAdapter, ReviewRequest
  from ado_ai_pr_review.reviewer import ReviewOrchestrator

  logger = logging.getLogger(__name__)


  class FixHandler:
      def handle(
          self,
          request: ReviewRequest,
          platform: PlatformAdapter,
          model: LLMPort,
          config: ReviewConfig,
      ) -> None:
          selected = select_context(request, config, config.instructions.fixer)
          local_security_summary = f"Local findings: {len(request.local_findings)}"

          try:
              result = ReviewOrchestrator(model).run(
                  command=ReviewCommand.FIX,
                  guidance=selected.always_on_guidance,
                  selected_files=selected.dynamic_files,
                  diff_text=request.diff_text,
                  local_security_summary=local_security_summary,
              )
          except Exception as exc:
              logger.error("fix failed: %s", exc)
              platform.publish_error(exc)
              raise

          merged_findings = [*result.findings, *request.local_findings]
          fix_candidates = [
              FixCandidate(
                  delivery=FixDelivery.FIX_BRANCH_CANDIDATE,
                  title=f.title,
                  explanation=f.body,
                  file_path=f.file_path,
                  replacement=f.suggested_code,
                  commit_message=f"fix: {f.title.lower()}",
              )
              for f in merged_findings
              if f.type is FindingType.MECHANICAL_FIX and f.suggested_code and f.file_path
          ]

          branch_name = config.fix.branch.name_template.format(
              pr_id=request.pr_context.pr_id or "local",
              run_id=request.pr_context.run_id,
          )
          target_branch = request.pr_context.target_branch.removeprefix("refs/heads/")

          fix_pr_created = platform.create_fix_branch(
              candidates=fix_candidates,
              branch_name=branch_name,
              target_branch=target_branch,
          )

          metrics = ReviewMetrics(
              command=ReviewCommand.FIX.value,
              pr_id=request.pr_context.pr_id or 0,
              findings_count=len(merged_findings),
              inline_suggestions_count=sum(1 for f in merged_findings if f.suggested_code),
              fix_pr_created=fix_pr_created,
          )
          logger.info("review metrics", extra=metrics.to_payload())
  ```

- [ ] **Step 5: Update handlers/__init__.py with the handler registry**

  Overwrite `src/ado_ai_pr_review/handlers/__init__.py`:
  ```python
  from __future__ import annotations

  from ado_ai_pr_review.handlers.base import CommandHandler
  from ado_ai_pr_review.handlers.fix import FixHandler
  from ado_ai_pr_review.handlers.onboarding import OnboardingHandler
  from ado_ai_pr_review.handlers.review import ReviewHandler, SecurityHandler
  from ado_ai_pr_review.handlers.skip import SkipHandler
  from ado_ai_pr_review.models import ReviewCommand

  HANDLERS: dict[ReviewCommand, CommandHandler] = {
      ReviewCommand.REVIEW: ReviewHandler(),
      ReviewCommand.SECURITY: SecurityHandler(),
      ReviewCommand.FIX: FixHandler(),
      ReviewCommand.ONBOARDING: OnboardingHandler(),
      ReviewCommand.SKIP: SkipHandler(),
  }

  __all__ = ["HANDLERS", "CommandHandler"]
  ```

- [ ] **Step 6: Rewrite engine.py to use HANDLERS**

  Replace the full content of `src/ado_ai_pr_review/engine.py`:
  ```python
  from __future__ import annotations

  import logging
  from pathlib import Path

  from ado_ai_pr_review.config import ReviewConfig
  from ado_ai_pr_review.handlers import HANDLERS
  from ado_ai_pr_review.log_context import bind_request_context
  from ado_ai_pr_review.models import ReviewCommand
  from ado_ai_pr_review.ports import LLMPort, PlatformAdapter

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
          config = ReviewConfig.load(self._repo_root)

          try:
              request = self._platform.load_request()
          except Exception as exc:
              logger.error("failed to load review request: %s", exc)
              self._platform.publish_error(exc)
              raise

          with bind_request_context(request.pr_context.request_id):
              handler = HANDLERS[request.command]
              handler.handle(request, self._platform, self._model, config)
              return request.command
  ```

- [ ] **Step 7: Run the test suite to find failures, then fix them**

  ```bash
  uv run pytest tests/test_engine.py -v
  ```

  The existing engine tests call `_write_config()` to create a valid config, then exercise the engine. They should still pass because:
  - `_MockPlatform.load_request()` returns the request with the correct command
  - The handler looks up by command and delegates
  - `_MockLLM.review_json()` is called by `ReviewOrchestrator`

  If tests fail because `ReviewEngine` no longer has a `_run_fix` method referenced in tests, remove those references.

  Also check: `test_engine_calls_publish_error_and_reraises_on_load_failure` — this exercises the `load_request` error path in engine, which is still present. Should pass.

- [ ] **Step 8: Run full test suite**

  ```bash
  uv run pytest -x -q
  ```
  Expected: all tests pass. If any fail due to import changes (e.g., `from ado_ai_pr_review.engine import ...`), trace and fix.

- [ ] **Step 9: Commit**

  ```bash
  git add src/ado_ai_pr_review/handlers/ src/ado_ai_pr_review/engine.py tests/test_engine.py
  git commit -m "refactor: command handler dispatch in engine — OCP fix, each command owns its handler"
  ```

---

## Self-Review Checklist

- [x] **Critical #1** (engine OCP): Addressed in Task 9 — handlers/ package, engine is ~20 lines.
- [x] **Critical #2** (constructor I/O): Addressed in Task 6 — `__init__` is cheap, all I/O in `load_request()`.
- [x] **Critical #3** (incomplete ports): Addressed in Task 3 — `GitPort` and `AdoApiPort` in ports.py; Task 4 — `MechanicalFixer` uses `GitPort`.
- [x] **Important #1** (duplicate _build_model): Addressed in Task 7.
- [x] **Important #2** (LocalCliAdapter duplication): Addressed in Task 4 — `apply_commits()` is the single implementation.
- [x] **Important #3** (MechanicalFixer None deps): Addressed in Task 4 — `MechanicalFixPolicy` + `MechanicalFixer(git, repo_root)`, no Nones.
- [x] **Important #4** (webhook.py god file): Addressed in Task 5 — payload models extracted to webhook_payload.py.
- [x] **Important #5** (ReviewResult mutation): Addressed in Task 2 — `frozen=True` + new instance construction.
- [x] **Important #6** (model_client.py shim): Addressed in Task 1.
- [x] **Important #7** (git_clone.py dead code): Addressed in Task 1.
- [x] **Important #8** (bootstrap in engine on every webhook call): Addressed in Task 8.
- [ ] **Important #9** (CommandRouter duplication): Out of scope — `CommandRouter` still has two static methods wrapping the same logic; acceptable as Minor cleanup in a follow-up.

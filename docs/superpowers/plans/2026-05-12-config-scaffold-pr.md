# Config Scaffold PR Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a review command succeeds on a repo that has no `.ado-ai-review.yml`, automatically create a PR to add the full configuration scaffold.

**Architecture:** `AdoWebhookAdapter.create_config_pr()` uses the existing `Bootstrapper` to write default files to the cloned temp dir, then creates a branch, commits, pushes, and opens an ADO PR. `_process_sync` in `webhook_server.py` calls it after `engine.run()` returns — only when a real review command was processed and the config file is absent from the temp dir. No changes to `engine.py`, `PlatformAdapter`, or `ReviewConfig`.

**Tech Stack:** `Bootstrapper` (existing), `GitToolset` (existing), `AdoToolset` (existing), `CommandPolicy` (already allows the required git operations), `pytest-mock`

---

## File Map

| File | Change |
|------|--------|
| `src/ado_ai_pr_review/adapters/webhook.py` | Add `create_config_pr()` method |
| `src/ado_ai_pr_review/webhook_server.py` | Import `ReviewCommand`; call `create_config_pr()` after engine run when config absent |
| `tests/test_webhook_adapter.py` | Four new tests for `create_config_pr()` |
| `tests/test_webhook_server.py` | Three new tests for scaffold trigger logic in `_process_sync` |

---

## Task 1: `AdoWebhookAdapter.create_config_pr()`

**Files:**
- Modify: `src/ado_ai_pr_review/adapters/webhook.py`
- Test: `tests/test_webhook_adapter.py`

### Background

`Bootstrapper().create_missing_files(repo_root)` already writes all template files and returns the list of paths it created (empty list if everything exists). `GitToolset` already supports `checkout_new_branch`, `add`, `commit`, `push`. `AdoToolset.create_pr` already exists. `CommandPolicy` already allows `git add <relative-path>` and `git push origin <branch>` — the new paths (`.ado-ai-review.yml`, `.ado-ai-review/instructions/reviewer.md`, etc.) are relative, non-traversing strings and pass `_is_safe_relative_path`.

- [ ] **Step 1: Add imports at the top of `tests/test_webhook_adapter.py`**

The file already has `FakeAuth` and `_PR_CREATED_PAYLOAD`. Add:

```python
from unittest.mock import MagicMock, patch
```

- [ ] **Step 2: Write the four failing tests**

Append to `tests/test_webhook_adapter.py`:

```python
def test_create_config_pr_creates_branch_commits_and_opens_pr(tmp_path: Path) -> None:
    payload = AdoWebhookPayload.model_validate(_PR_CREATED_PAYLOAD)
    adapter = AdoWebhookAdapter(payload=payload, auth_strategy=FakeAuth(), temp_dir=tmp_path)
    git_mock = MagicMock()
    ado_mock = MagicMock()
    adapter._git = git_mock
    adapter._ado = ado_mock
    adapter._target_ref = "refs/heads/main"

    with patch("ado_ai_pr_review.adapters.webhook.Bootstrapper") as bootstrap_cls:
        bootstrap_cls.return_value.create_missing_files.return_value = [
            ".ado-ai-review.yml",
            ".ado-ai-review/instructions/reviewer.md",
        ]
        result = adapter.create_config_pr()

    assert result is True
    git_mock.checkout_new_branch.assert_called_once_with("ai-config/setup")
    git_mock.add.assert_called_once_with([
        ".ado-ai-review.yml",
        ".ado-ai-review/instructions/reviewer.md",
    ])
    git_mock.commit.assert_called_once()
    git_mock.push.assert_called_once_with("origin", "ai-config/setup")
    pr_call = ado_mock.create_pr.call_args.kwargs
    assert pr_call["source_branch"] == "ai-config/setup"
    assert pr_call["target_branch"] == "main"


def test_create_config_pr_returns_false_before_load_request(tmp_path: Path) -> None:
    payload = AdoWebhookPayload.model_validate(_PR_CREATED_PAYLOAD)
    adapter = AdoWebhookAdapter(payload=payload, auth_strategy=FakeAuth(), temp_dir=tmp_path)

    result = adapter.create_config_pr()

    assert result is False


def test_create_config_pr_returns_false_when_no_files_created(tmp_path: Path) -> None:
    payload = AdoWebhookPayload.model_validate(_PR_CREATED_PAYLOAD)
    adapter = AdoWebhookAdapter(payload=payload, auth_strategy=FakeAuth(), temp_dir=tmp_path)
    adapter._git = MagicMock()
    adapter._ado = MagicMock()
    adapter._target_ref = "refs/heads/main"

    with patch("ado_ai_pr_review.adapters.webhook.Bootstrapper") as bootstrap_cls:
        bootstrap_cls.return_value.create_missing_files.return_value = []
        result = adapter.create_config_pr()

    assert result is False
    adapter._git.checkout_new_branch.assert_not_called()


def test_create_config_pr_returns_true_when_ado_pr_creation_fails(tmp_path: Path) -> None:
    payload = AdoWebhookPayload.model_validate(_PR_CREATED_PAYLOAD)
    adapter = AdoWebhookAdapter(payload=payload, auth_strategy=FakeAuth(), temp_dir=tmp_path)
    git_mock = MagicMock()
    ado_mock = MagicMock()
    ado_mock.create_pr.side_effect = RuntimeError("TF401349: PR already exists")
    adapter._git = git_mock
    adapter._ado = ado_mock
    adapter._target_ref = "refs/heads/main"

    with patch("ado_ai_pr_review.adapters.webhook.Bootstrapper") as bootstrap_cls:
        bootstrap_cls.return_value.create_missing_files.return_value = [".ado-ai-review.yml"]
        result = adapter.create_config_pr()

    assert result is True
    git_mock.push.assert_called_once()
    ado_mock.create_pr.assert_called_once()
```

- [ ] **Step 3: Run the tests — confirm they fail**

```bash
uv run pytest tests/test_webhook_adapter.py::test_create_config_pr_creates_branch_commits_and_opens_pr -v
```

Expected output: `FAILED — AttributeError: 'AdoWebhookAdapter' object has no attribute 'create_config_pr'`

- [ ] **Step 4: Implement `create_config_pr()` in `webhook.py`**

Add this method to `AdoWebhookAdapter`, after `create_fix_branch` (around line 186, before `_make_pr_context`):

```python
def create_config_pr(self) -> bool:
    if self._git is None or self._ado is None:
        logger.warning("create_config_pr called before load_request(); skipping")
        return False
    from ado_ai_pr_review.bootstrap import Bootstrapper

    created = Bootstrapper().create_missing_files(self._temp_dir)
    if not created:
        return False

    branch_name = "ai-config/setup"
    target_branch = self._target_ref.removeprefix("refs/heads/")
    self._git.checkout_new_branch(branch_name)
    self._git.add(created)
    self._git.commit("chore: add ADO AI review configuration")
    self._git.push("origin", branch_name)
    description = (
        "This PR adds the ADO AI review configuration (`.ado-ai-review.yml`) "
        "and default instruction and guideline files.\n\n"
        "Generated automatically: an `/ai review` command was received "
        "but no configuration was found in the repository.\n\n"
        "Review and customise the settings before merging."
    )
    try:
        self._ado.create_pr(
            source_branch=branch_name,
            target_branch=target_branch,
            title="chore: add ADO AI review configuration",
            description=description,
        )
    except Exception as exc:
        logger.warning("config branch pushed but PR creation failed: %s", exc)
    return True
```

- [ ] **Step 5: Run all four new tests — confirm they pass**

```bash
uv run pytest tests/test_webhook_adapter.py -v
```

Expected: all tests green.

- [ ] **Step 6: Commit**

```bash
git add src/ado_ai_pr_review/adapters/webhook.py tests/test_webhook_adapter.py
git commit -m "feat: add create_config_pr() to AdoWebhookAdapter"
```

---

## Task 2: Wire scaffold trigger into `_process_sync`

**Files:**
- Modify: `src/ado_ai_pr_review/webhook_server.py`
- Test: `tests/test_webhook_server.py`

### Background

`_process_sync` currently does `engine.run()` with no capture. The return value is `ReviewCommand`. After a successful run, if `(temp_dir / ".ado-ai-review.yml").exists()` is `False`, the adapter should scaffold the config. The check must happen inside the existing `try` block so that scaffold failures are caught by the same exception handler. `ReviewCommand` is not yet imported in `webhook_server.py`.

- [ ] **Step 7: Write the three failing tests**

Add these to `tests/test_webhook_server.py`. Add to the existing imports at the top:

```python
from pathlib import Path
from unittest.mock import MagicMock, patch

from ado_ai_pr_review.adapters.webhook_payload import AdoWebhookPayload
from ado_ai_pr_review.models import ReviewCommand
from ado_ai_pr_review.webhook_server import _process_sync
```

Then append these test functions:

```python
_PARSED_PAYLOAD = AdoWebhookPayload.model_validate(_PR_CREATED_PAYLOAD)


def _make_process_sync_mocks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, command: ReviewCommand
) -> MagicMock:
    """Patches all external dependencies of _process_sync; returns the adapter mock."""
    monkeypatch.setenv("AZURE_OPENAI_BASE_URL", "https://example.com/")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "model")

    adapter_mock = MagicMock()
    engine_mock = MagicMock()
    engine_mock.run.return_value = command

    patch("ado_ai_pr_review.webhook_server.AdoWebhookAdapter", return_value=adapter_mock).start()
    patch("ado_ai_pr_review.webhook_server.ReviewEngine", return_value=engine_mock).start()
    patch("ado_ai_pr_review.webhook_server.build_ado_auth_strategy").start()
    patch("ado_ai_pr_review.webhook_server.build_llm").start()
    tmp_ctx = patch("ado_ai_pr_review.webhook_server.tempfile.TemporaryDirectory").start()
    tmp_ctx.return_value.__enter__.return_value = str(tmp_path)
    tmp_ctx.return_value.__exit__.return_value = False

    return adapter_mock


def test_process_sync_creates_config_pr_when_config_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    adapter_mock = _make_process_sync_mocks(monkeypatch, tmp_path, ReviewCommand.REVIEW)

    _process_sync(_PARSED_PAYLOAD, "req-1")

    adapter_mock.create_config_pr.assert_called_once()


def test_process_sync_skips_config_scaffold_when_config_present(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / ".ado-ai-review.yml").write_text("version: 1\n", encoding="utf-8")
    adapter_mock = _make_process_sync_mocks(monkeypatch, tmp_path, ReviewCommand.REVIEW)

    _process_sync(_PARSED_PAYLOAD, "req-1")

    adapter_mock.create_config_pr.assert_not_called()


def test_process_sync_skips_config_scaffold_for_onboarding(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    adapter_mock = _make_process_sync_mocks(monkeypatch, tmp_path, ReviewCommand.ONBOARDING)

    _process_sync(_PARSED_PAYLOAD, "req-1")

    adapter_mock.create_config_pr.assert_not_called()
```

> **Note on `patch().start()`:** The patches started with `.start()` are automatically stopped when `monkeypatch` is torn down by pytest's fixture machinery — no explicit `stopall()` needed because `unittest.mock.patch.start()` registers with `monkeypatch` via pytest's integration.
>
> If your pytest version does NOT auto-stop these, replace each `patch(...).start()` with an `with patch(...)` context manager inside a helper function, or use `monkeypatch.setattr` instead.

- [ ] **Step 8: Run the three tests — confirm they fail**

```bash
uv run pytest tests/test_webhook_server.py::test_process_sync_creates_config_pr_when_config_missing -v
```

Expected: `FAILED` — `AssertionError: Expected call not found` (because `_process_sync` doesn't call `create_config_pr` yet).

- [ ] **Step 9: Update `_process_sync` in `webhook_server.py`**

Add `ReviewCommand` to the imports at the top of the file:

```python
from ado_ai_pr_review.models import ReviewCommand
```

Then change `_process_sync` from:

```python
def _process_sync(payload: AdoWebhookPayload, request_id: str) -> None:
    with bind_request_context(request_id), tempfile.TemporaryDirectory() as tmp:
        temp_dir = Path(tmp)
        try:
            auth_strategy = build_ado_auth_strategy()
            adapter = AdoWebhookAdapter(
                payload=payload, auth_strategy=auth_strategy, temp_dir=temp_dir, request_id=request_id
            )
            model = build_llm(os.getenv("LLM_PROVIDER"))
            engine = ReviewEngine(platform=adapter, model=model, repo_root=temp_dir)
            engine.run()
        except Exception:
            logger.exception("webhook processing failed for PR %s", payload.pull_request_id)
```

To:

```python
def _process_sync(payload: AdoWebhookPayload, request_id: str) -> None:
    with bind_request_context(request_id), tempfile.TemporaryDirectory() as tmp:
        temp_dir = Path(tmp)
        try:
            auth_strategy = build_ado_auth_strategy()
            adapter = AdoWebhookAdapter(
                payload=payload, auth_strategy=auth_strategy, temp_dir=temp_dir, request_id=request_id
            )
            model = build_llm(os.getenv("LLM_PROVIDER"))
            engine = ReviewEngine(platform=adapter, model=model, repo_root=temp_dir)
            command = engine.run()
            if command not in (ReviewCommand.ONBOARDING, ReviewCommand.SKIP):
                if not (temp_dir / ".ado-ai-review.yml").exists():
                    adapter.create_config_pr()
        except Exception:
            logger.exception("webhook processing failed for PR %s", payload.pull_request_id)
```

- [ ] **Step 10: Run all webhook server tests — confirm they pass**

```bash
uv run pytest tests/test_webhook_server.py -v
```

Expected: all tests green, including the three new ones.

- [ ] **Step 11: Run the full test suite**

```bash
uv run pytest -q
```

Expected: all tests pass (219 + 7 new = 226).

- [ ] **Step 12: Commit**

```bash
git add src/ado_ai_pr_review/webhook_server.py tests/test_webhook_server.py
git commit -m "feat: trigger config scaffold PR when .ado-ai-review.yml is absent after review"
```

---

## Self-Review

**Spec coverage:**
- ✅ When config missing, review runs with defaults (done in previous session: `load_or_default`)
- ✅ Scaffold written locally to cloned repo (done by `Bootstrapper().create_missing_files(self._temp_dir)`)
- ✅ Scaffold PR opened in ADO (`create_config_pr` → `GitToolset` + `AdoToolset.create_pr`)
- ✅ Triggered only for real review commands, not ONBOARDING/SKIP
- ✅ Doesn't create scaffold if config already exists (`not (temp_dir / ".ado-ai-review.yml").exists()`)
- ✅ PR creation failure is non-fatal (warning log, returns True)

**Placeholder scan:** None found.

**Type consistency:**
- `create_config_pr() -> bool` — defined in Task 1, called in Task 2 ✓
- `Bootstrapper().create_missing_files(path) -> list[str]` — matches existing `bootstrap.py` ✓
- `self._git.add(created)` where `created: list[str]` — matches `GitToolset.add(paths: Sequence[str])` ✓
- `engine.run() -> ReviewCommand` — matches current `engine.py` return type ✓

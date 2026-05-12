# ADO Auth And Pipeline Removal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Zastąpić obecny tokenowy/PAT-owy dostęp do Azure DevOps warstwą strategii autoryzacji opartą domyślnie o Microsoft Entra ID oraz całkowicie usunąć tryb pipeline z kodu, testów, dokumentacji i infrastruktury.

**Architecture:** Azure DevOps auth będzie osobną warstwą (`auth/ado.py`) używaną przez REST API i Git clone; webhook będzie dostawał gotową strategię zamiast przekazywać surowy token. ADO REST przejdzie z `az devops invoke` na mały klient HTTP z `Authorization: Bearer ...` albo jawnie wybraną strategią PAT; Git clone użyje `http.extraheader` przez env `GIT_CONFIG_*`, bez tokenów w URL. Pipeline mode zostaje usunięty, a obsługiwane tryby to `local` i `serve`.

**Tech Stack:** Python 3.12, Typer, FastAPI, Pydantic, azure-identity `DefaultAzureCredential`, urllib stdlib, pytest, ruff, mypy, ARM Template / CreateUiDefinition.

---

## Założenia Z Dokumentacji Microsoft

- Microsoft Entra tokens są preferowane dla Azure Repos Git i Azure DevOps REST; PAT jest opcją alternatywną dla prostych skryptów/testów.
- Service principal albo managed identity musi zostać jawnie dodana do organizacji Azure DevOps jako user/service principal, dostać access level oraz dostęp do projektu.
- Uprawnienia Azure DevOps są niezależne od Azure RBAC i Microsoft Entra application permissions.
- REST API Azure DevOps używa nagłówka `Authorization: Bearer <token>` dla tokenów Entra.
- Pierwszy onboarding identity wymaga Project Collection Administrator albo już uprawnionej identity.

## File Structure

- Create: `src/ado_ai_pr_review/auth/__init__.py`
- Create: `src/ado_ai_pr_review/auth/ado.py`
- Create: `src/ado_ai_pr_review/ado_context.py`
- Create: `src/ado_ai_pr_review/ado_rest.py`
- Delete: `src/ado_ai_pr_review/runtime.py`
- Delete: `src/ado_ai_pr_review/adapters/pipeline.py`
- Delete: `azure-pipelines.ado-ai-review.yml`
- Delete: `templates/pipeline.yml`
- Modify: `src/ado_ai_pr_review/ports.py`
- Modify: `src/ado_ai_pr_review/engine.py`
- Modify: `src/ado_ai_pr_review/ado_toolset.py`
- Modify: `src/ado_ai_pr_review/git_toolset.py`
- Modify: `src/ado_ai_pr_review/adapters/webhook.py`
- Modify: `src/ado_ai_pr_review/webhook_server.py`
- Modify: `src/ado_ai_pr_review/adapters/local.py`
- Modify: `src/ado_ai_pr_review/cli.py`
- Modify: `src/ado_ai_pr_review/tool_policy.py`
- Modify: `infra/mainTemplate.json`
- Modify: `infra/createUiDefinition.json`
- Modify: `README.md`, `docs/operations/ado-ai-review.md`, `docs/marketplace-testing.md`, `docs/marketplace-publishing.md`, `docs/follow-ups/webhook-auth.md`
- Create/modify tests: `tests/test_ado_auth.py`, `tests/test_ado_rest.py`, `tests/test_ado_toolset.py`, `tests/test_git_toolset.py`, `tests/test_webhook_adapter.py`, `tests/test_webhook_server.py`, `tests/test_cli.py`, `tests/test_ports.py`, `tests/test_publisher.py`, `tests/test_engine.py`, `tests/test_local_adapter.py`, `tests/test_infra_auth.py`, `tests/test_docs_pipeline_removed.py`.

## Task 1: Neutral ADO Context and `run_id`

**Files:**
- Create: `src/ado_ai_pr_review/ado_context.py`
- Modify: `src/ado_ai_pr_review/ports.py`
- Modify: `src/ado_ai_pr_review/engine.py`
- Modify: `src/ado_ai_pr_review/adapters/local.py`
- Modify: `src/ado_ai_pr_review/adapters/webhook.py`
- Modify: `tests/test_ports.py`, `tests/test_engine.py`, `tests/test_local_adapter.py`, `tests/test_publisher.py`

- [ ] **Step 1: Write failing tests for `run_id` and neutral ADO context**

Create `tests/test_ado_context.py`:

```python
from pathlib import Path

from ado_ai_pr_review.ado_context import AdoContext


def test_ado_context_has_no_pipeline_token_field(tmp_path: Path) -> None:
    context = AdoContext(
        repo_root=tmp_path,
        organization_url="https://dev.azure.com/acme/",
        project="Payments",
        repository_id="repo-guid",
        repository_name="payments-api",
        pull_request_id=42,
        source_branch="refs/heads/feature/auth",
        target_branch="refs/heads/main",
        is_fork=False,
        run_id="webhook",
    )

    assert context.run_id == "webhook"
    assert not hasattr(context, "system_access_token")
```

Append to `tests/test_ports.py`:

```python
def test_pr_context_uses_run_id_not_build_id() -> None:
    ctx = PRContext(pr_id=1, source_branch="feat", target_branch="main", is_fork=False, run_id="webhook")

    assert ctx.run_id == "webhook"
    assert not hasattr(ctx, "build_id")
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
.venv/bin/pytest tests/test_ports.py::test_pr_context_uses_run_id_not_build_id tests/test_ado_context.py -v
```

Expected: FAIL because `PRContext` still has `build_id` and `ado_context.py` does not exist.

- [ ] **Step 3: Implement `AdoContext` and rename `build_id` to `run_id`**

Create `src/ado_ai_pr_review/ado_context.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AdoContext:
    repo_root: Path
    organization_url: str
    project: str
    repository_id: str
    repository_name: str
    pull_request_id: int
    source_branch: str
    target_branch: str
    is_fork: bool
    run_id: str
```

Modify `src/ado_ai_pr_review/ports.py`:

```python
@dataclass(frozen=True)
class PRContext:
    pr_id: int | None
    source_branch: str
    target_branch: str
    is_fork: bool
    run_id: str
```

Update `engine.py`:

```python
branch_name = config.fix.branch.name_template.format(
    pr_id=request.pr_context.pr_id or "local",
    run_id=request.pr_context.run_id,
)
```

Update local and webhook adapter `PRContext(...)` constructors to pass `run_id="local"` or `run_id="webhook"`.

- [ ] **Step 4: Update old tests**

Replace all `PRContext(..., build_id="...")` with `PRContext(..., run_id="...")`.

- [ ] **Step 5: Run context tests**

Run:

```bash
.venv/bin/pytest tests/test_ports.py tests/test_engine.py tests/test_local_adapter.py tests/test_ado_context.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/ado_ai_pr_review/ado_context.py src/ado_ai_pr_review/ports.py src/ado_ai_pr_review/engine.py src/ado_ai_pr_review/adapters/local.py src/ado_ai_pr_review/adapters/webhook.py tests
git commit -m "refactor: replace pipeline build context with generic run context"
```

## Task 2: ADO Auth Strategies

**Files:**
- Create: `src/ado_ai_pr_review/auth/__init__.py`
- Create: `src/ado_ai_pr_review/auth/ado.py`
- Create: `tests/test_ado_auth.py`

- [ ] **Step 1: Write failing auth tests**

Create `tests/test_ado_auth.py`:

```python
from __future__ import annotations

import pytest

from ado_ai_pr_review.auth.ado import EntraAdoAuthStrategy, PatAdoAuthStrategy, build_ado_auth_strategy
from ado_ai_pr_review.errors import ConfigurationError


class FakeCredential:
    def get_token(self, scope: str):
        assert scope == "499b84ac-1321-427f-aa17-267ca6975798/.default"

        class Token:
            token = "entra-token"

        return Token()


def test_default_auth_strategy_is_entra() -> None:
    strategy = build_ado_auth_strategy(env={}, credential=FakeCredential())

    assert isinstance(strategy, EntraAdoAuthStrategy)
    assert strategy.authorization_header() == ("Authorization", "Bearer entra-token")
    assert strategy.git_env()["GIT_CONFIG_VALUE_0"] == "AUTHORIZATION: bearer entra-token"


def test_pat_requires_explicit_mode() -> None:
    strategy = build_ado_auth_strategy(env={"ADO_AUTH_MODE": "pat", "ADO_PAT": "pat-token"}, credential=FakeCredential())

    assert isinstance(strategy, PatAdoAuthStrategy)
    assert strategy.authorization_header()[1].startswith("Basic ")
    assert strategy.secret_values() == ("pat-token",)


def test_pat_token_is_ignored_without_explicit_mode() -> None:
    strategy = build_ado_auth_strategy(env={"ADO_PAT": "pat-token"}, credential=FakeCredential())

    assert isinstance(strategy, EntraAdoAuthStrategy)


def test_explicit_pat_mode_requires_token() -> None:
    with pytest.raises(ConfigurationError, match="ADO_PAT"):
        build_ado_auth_strategy(env={"ADO_AUTH_MODE": "pat"}, credential=FakeCredential())


def test_unknown_auth_mode_is_rejected() -> None:
    with pytest.raises(ConfigurationError, match="ADO_AUTH_MODE"):
        build_ado_auth_strategy(env={"ADO_AUTH_MODE": "password"}, credential=FakeCredential())
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
.venv/bin/pytest tests/test_ado_auth.py -v
```

Expected: FAIL because `ado_ai_pr_review.auth.ado` does not exist.

- [ ] **Step 3: Implement auth strategies**

Create `src/ado_ai_pr_review/auth/ado.py` with:

```python
from __future__ import annotations

import base64
import os
from collections.abc import Mapping
from typing import Protocol

from azure.core.credentials import TokenCredential
from azure.identity import DefaultAzureCredential

from ado_ai_pr_review.errors import ConfigurationError

AZURE_DEVOPS_SCOPE = "499b84ac-1321-427f-aa17-267ca6975798/.default"


class AdoAuthStrategy(Protocol):
    def authorization_header(self) -> tuple[str, str]: ...
    def git_env(self) -> dict[str, str]: ...
    def secret_values(self) -> tuple[str, ...]: ...


class EntraAdoAuthStrategy:
    def __init__(self, credential: TokenCredential | None = None) -> None:
        self._credential = credential or DefaultAzureCredential()

    def _token(self) -> str:
        return self._credential.get_token(AZURE_DEVOPS_SCOPE).token

    def authorization_header(self) -> tuple[str, str]:
        return ("Authorization", f"Bearer {self._token()}")

    def git_env(self) -> dict[str, str]:
        return {
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "http.extraheader",
            "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: bearer {self._token()}",
        }

    def secret_values(self) -> tuple[str, ...]:
        return (self._token(),)


class PatAdoAuthStrategy:
    def __init__(self, token: str) -> None:
        if not token.strip():
            raise ConfigurationError("ADO_PAT must be set when ADO_AUTH_MODE=pat")
        self._token = token.strip()

    def authorization_header(self) -> tuple[str, str]:
        encoded = base64.b64encode(f":{self._token}".encode("utf-8")).decode("ascii")
        return ("Authorization", f"Basic {encoded}")

    def git_env(self) -> dict[str, str]:
        encoded = self.authorization_header()[1].removeprefix("Basic ")
        return {
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "http.extraheader",
            "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {encoded}",
        }

    def secret_values(self) -> tuple[str, ...]:
        return (self._token,)


def build_ado_auth_strategy(env: Mapping[str, str] | None = None, credential: TokenCredential | None = None) -> AdoAuthStrategy:
    source = env if env is not None else os.environ
    mode = source.get("ADO_AUTH_MODE", "entra").strip().lower()
    if mode == "entra":
        return EntraAdoAuthStrategy(credential=credential)
    if mode == "pat":
        return PatAdoAuthStrategy(source.get("ADO_PAT", ""))
    raise ConfigurationError("ADO_AUTH_MODE must be one of: entra, pat")
```

Create `src/ado_ai_pr_review/auth/__init__.py` exporting all public auth classes and factory.

- [ ] **Step 4: Run auth tests**

Run:

```bash
.venv/bin/pytest tests/test_ado_auth.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ado_ai_pr_review/auth tests/test_ado_auth.py
git commit -m "feat: add Azure DevOps auth strategies"
```

## Task 3: ADO REST Client and Toolset Through Auth Strategy

**Files:**
- Create: `src/ado_ai_pr_review/ado_rest.py`
- Modify: `src/ado_ai_pr_review/ado_toolset.py`
- Create: `tests/test_ado_rest.py`
- Create: `tests/test_ado_toolset.py`
- Modify: `tests/test_publisher.py`

- [ ] **Step 1: Write failing REST/toolset tests**

Create `tests/test_ado_rest.py` with a fake auth strategy and fake `urllib.request.urlopen` assertion that:
- `Authorization` header is set to `Bearer entra-token`,
- method is `POST`,
- JSON body is encoded.

Create `tests/test_ado_toolset.py`:

```python
from pathlib import Path

from ado_ai_pr_review.ado_context import AdoContext
from ado_ai_pr_review.ado_toolset import AdoToolset


class FakeRest:
    def __init__(self) -> None:
        self.calls = []

    def request_json(self, *, method: str, url: str, body=None):
        self.calls.append((method, url, body))
        return {"ok": True}


def _context(tmp_path: Path) -> AdoContext:
    return AdoContext(
        repo_root=tmp_path,
        organization_url="https://dev.azure.com/acme/",
        project="Payments",
        repository_id="repo-guid",
        repository_name="payments-api",
        pull_request_id=42,
        source_branch="refs/heads/feature",
        target_branch="refs/heads/main",
        is_fork=False,
        run_id="webhook",
    )


def test_ado_toolset_lists_threads_with_rest(tmp_path: Path) -> None:
    rest = FakeRest()
    toolset = AdoToolset(rest_client=rest, context=_context(tmp_path))

    assert toolset.list_pr_threads() == {"ok": True}
    method, url, body = rest.calls[0]
    assert method == "GET"
    assert body is None
    assert url == "https://dev.azure.com/acme/Payments/_apis/git/repositories/repo-guid/pullRequests/42/threads?api-version=7.1"
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
.venv/bin/pytest tests/test_ado_rest.py tests/test_ado_toolset.py -v
```

Expected: FAIL because `AdoRestClient` does not exist and `AdoToolset` expects CLI.

- [ ] **Step 3: Implement `AdoRestClient`**

Create `src/ado_ai_pr_review/ado_rest.py`:

```python
from __future__ import annotations

import json
import urllib.request
from collections.abc import Mapping
from typing import Any, cast

from ado_ai_pr_review.auth import AdoAuthStrategy


class AdoRestClient:
    def __init__(self, auth: AdoAuthStrategy, timeout_seconds: int = 15) -> None:
        self._auth = auth
        self._timeout_seconds = timeout_seconds

    def request_json(self, *, method: str, url: str, body: Mapping[str, object] | None = None) -> object:
        auth_name, auth_value = self._auth.authorization_header()
        headers = {"Accept": "application/json", auth_name: auth_value}
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
            return cast(Any, json.loads(response.read().decode("utf-8")))
```

- [ ] **Step 4: Replace `AdoToolset` internals**

Replace CLI-based `az devops invoke` calls in `src/ado_ai_pr_review/ado_toolset.py` with REST URL builders for:
- `show_pr()`
- `create_pr()`
- `list_pr_threads()`
- `list_iterations()`
- `list_iteration_changes()`
- `create_pr_thread()`

Use `urllib.parse.quote` for project/repository path parts and `urlencode` for query strings. Every URL must use `api-version=7.1`.

- [ ] **Step 5: Update publisher/toolset tests**

Remove tests that assert `az devops invoke` argv. Replace them with REST URL/body assertions.

- [ ] **Step 6: Run focused tests**

Run:

```bash
.venv/bin/pytest tests/test_ado_rest.py tests/test_ado_toolset.py tests/test_publisher.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/ado_ai_pr_review/ado_rest.py src/ado_ai_pr_review/ado_toolset.py tests/test_ado_rest.py tests/test_ado_toolset.py tests/test_publisher.py
git commit -m "refactor: use auth strategies for Azure DevOps REST"
```

## Task 4: Git Clone Without Tokens in URLs

**Files:**
- Modify: `src/ado_ai_pr_review/git_toolset.py`
- Modify: `src/ado_ai_pr_review/tool_policy.py`
- Create: `tests/test_git_toolset.py`
- Modify: `tests/test_tool_policy.py`

- [ ] **Step 1: Write failing clone tests**

Create `tests/test_git_toolset.py`:

```python
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from ado_ai_pr_review.git_toolset import GitToolset


class FakeAuth:
    def authorization_header(self) -> tuple[str, str]:
        return ("Authorization", "Bearer entra-token")

    def git_env(self) -> dict[str, str]:
        return {
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "http.extraheader",
            "GIT_CONFIG_VALUE_0": "AUTHORIZATION: bearer entra-token",
        }

    def secret_values(self) -> tuple[str, ...]:
        return ("entra-token",)


def test_clone_uses_git_extraheader_env_not_token_url(tmp_path: Path) -> None:
    runner = MagicMock()
    toolset = GitToolset(runner=runner, repo_root=tmp_path)
    destination = tmp_path / "work"

    toolset.clone(
        remote_url="https://dev.azure.com/acme/Payments/_git/payments-api",
        branch="feature/auth",
        destination=destination,
        auth_strategy=FakeAuth(),
    )

    argv = runner.run.call_args.args[0]
    env = runner.run.call_args.kwargs["env"]
    assert "entra-token" not in " ".join(argv)
    assert env["GIT_CONFIG_KEY_0"] == "http.extraheader"
    assert env["GIT_CONFIG_VALUE_0"] == "AUTHORIZATION: bearer entra-token"
```

- [ ] **Step 2: Run failing test**

Run:

```bash
.venv/bin/pytest tests/test_git_toolset.py::test_clone_uses_git_extraheader_env_not_token_url -v
```

Expected: FAIL because `GitToolset.clone` does not exist.

- [ ] **Step 3: Implement `GitToolset.clone`**

Add:

```python
def clone(
    self,
    *,
    remote_url: str,
    branch: str,
    destination: Path,
    auth_strategy: AdoAuthStrategy,
    depth: int = 50,
) -> CommandResult:
    env = {**os.environ, **auth_strategy.git_env()}
    return self._runner.run(
        ["git", "clone", "--depth", str(depth), "--branch", branch, remote_url, str(destination)],
        cwd=destination.parent,
        env=env,
    )
```

- [ ] **Step 4: Harden clone command policy**

Add tests:

```python
def test_command_policy_allows_plain_https_git_clone() -> None:
    CommandPolicy.default().validate([
        "git",
        "clone",
        "--depth",
        "50",
        "--branch",
        "feature/auth",
        "https://dev.azure.com/acme/Payments/_git/payments-api",
        "/tmp/work",
    ])


def test_command_policy_rejects_credential_embedded_clone_url() -> None:
    with pytest.raises(CommandRejectedError):
        CommandPolicy.default().validate([
            "git",
            "clone",
            "--depth",
            "50",
            "--branch",
            "feature/auth",
            "https://:secret@dev.azure.com/acme/Payments/_git/payments-api",
            "/tmp/work",
        ])
```

Policy requirements:
- exact clone shape only,
- branch passes `_is_safe_branch`,
- URL starts with `https://dev.azure.com/`,
- URL contains no `@`,
- destination is a safe local path.

- [ ] **Step 5: Run focused tests**

Run:

```bash
.venv/bin/pytest tests/test_git_toolset.py tests/test_tool_policy.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/ado_ai_pr_review/git_toolset.py src/ado_ai_pr_review/tool_policy.py tests/test_git_toolset.py tests/test_tool_policy.py
git commit -m "feat: clone Azure Repos with auth headers"
```

## Task 5: Webhook Adapter and Server Through Auth Providers

**Files:**
- Modify: `src/ado_ai_pr_review/adapters/webhook.py`
- Modify: `src/ado_ai_pr_review/webhook_server.py`
- Modify: `tests/test_webhook_adapter.py`
- Modify: `tests/test_webhook_server.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_webhook_server.py`:

```python
def test_webhook_no_longer_requires_ado_auth_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ADO_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("ADO_AUTH_MODE", raising=False)
    monkeypatch.setenv("AZURE_OPENAI_BASE_URL", "https://example.com/")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "model")

    with patch("ado_ai_pr_review.webhook_server._process_sync"):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/webhook/ado", json=_PR_CREATED_PAYLOAD)

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
```

Add to `tests/test_webhook_adapter.py`:

```python
def test_webhook_adapter_clones_with_auth_strategy_not_url_token(mocker: MockerFixture, tmp_path: Path) -> None:
    payload = AdoWebhookPayload.model_validate(_PR_CREATED_PAYLOAD)
    runner_cls = mocker.patch("ado_ai_pr_review.adapters.webhook.CliRunner")
    git_cls = mocker.patch("ado_ai_pr_review.adapters.webhook.GitToolset")
    mocker.patch("ado_ai_pr_review.adapters.webhook.AdoToolset")
    mocker.patch("ado_ai_pr_review.adapters.webhook.AdoRestClient")
    mocker.patch("ado_ai_pr_review.adapters.webhook.SuggestionPublisher")

    AdoWebhookAdapter(payload=payload, auth_strategy=FakeAuth(), temp_dir=tmp_path)

    runner_cls.assert_called_once()
    assert runner_cls.call_args.kwargs["secrets"] == ["entra-token"]
    git_cls.return_value.clone.assert_called_once()
    clone_kwargs = git_cls.return_value.clone.call_args.kwargs
    assert clone_kwargs["remote_url"] == "https://dev.azure.com/org/project/_git/MyRepo"
    assert "entra-token" not in clone_kwargs["remote_url"]
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
.venv/bin/pytest tests/test_webhook_server.py::test_webhook_no_longer_requires_ado_auth_token tests/test_webhook_adapter.py::test_webhook_adapter_clones_with_auth_strategy_not_url_token -v
```

Expected: FAIL because webhook still requires `ADO_AUTH_TOKEN` and adapter accepts `auth_token`.

- [ ] **Step 3: Refactor `AdoWebhookAdapter`**

Constructor signature:

```python
def __init__(self, payload: AdoWebhookPayload, auth_strategy: AdoAuthStrategy, temp_dir: Path) -> None:
```

Implementation requirements:
- create `CliRunner(policy=CommandPolicy.default(), secrets=list(auth_strategy.secret_values()))`,
- create `AdoRestClient(auth=auth_strategy)`,
- fetch flat-comment PR details via REST client,
- call `GitToolset.clone(remote_url=self._remote_url, branch=source_branch, destination=temp_dir, auth_strategy=auth_strategy)`,
- create `AdoContext`, `AdoToolset(rest_client=rest_client, context=self._context)`, `GitToolset`, and `SuggestionPublisher`,
- delete `_make_authenticated_url`.

- [ ] **Step 4: Refactor webhook server**

Use:

```python
from ado_ai_pr_review.auth import build_ado_auth_strategy
```

`handle_ado_webhook()` no longer checks `ADO_AUTH_TOKEN`. `_process_sync()` builds `auth_strategy = build_ado_auth_strategy()` and passes it into `AdoWebhookAdapter`.

- [ ] **Step 5: Run webhook tests**

Run:

```bash
.venv/bin/pytest tests/test_webhook_adapter.py tests/test_webhook_server.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/ado_ai_pr_review/adapters/webhook.py src/ado_ai_pr_review/webhook_server.py tests/test_webhook_adapter.py tests/test_webhook_server.py
git commit -m "refactor: wire webhook through Azure DevOps auth strategies"
```

## Task 6: Remove Pipeline Mode From Code and Tests

**Files:**
- Delete: `src/ado_ai_pr_review/adapters/pipeline.py`
- Delete: `src/ado_ai_pr_review/runtime.py`
- Delete: `azure-pipelines.ado-ai-review.yml`
- Delete: `templates/pipeline.yml`
- Modify: `src/ado_ai_pr_review/cli.py`
- Modify: `tests/test_cli.py`
- Modify: `src/ado_ai_pr_review/tool_policy.py`
- Modify: `tests/test_tool_policy.py`

- [ ] **Step 1: Write failing command-removal tests**

Replace pipeline CLI tests with:

```python
def test_pipeline_command_is_not_registered() -> None:
    result = CliRunner().invoke(app, ["pipeline", "--help"])

    assert result.exit_code != 0
    assert "pipeline" in result.output.lower()


def test_local_help_still_renders() -> None:
    result = CliRunner().invoke(app, ["local", "--help"])

    assert result.exit_code == 0
    assert "command" in result.output


def test_serve_help_still_renders() -> None:
    result = CliRunner().invoke(app, ["serve", "--help"])

    assert result.exit_code == 0
    assert "host" in result.output
```

Remove all `RuntimeContext.from_env` tests.

- [ ] **Step 2: Run failing command test**

Run:

```bash
.venv/bin/pytest tests/test_cli.py::test_pipeline_command_is_not_registered -v
```

Expected: FAIL while `pipeline` still exists.

- [ ] **Step 3: Remove pipeline command and files**

In `cli.py`, delete the `AdoPipelineAdapter` import and the entire `pipeline(...)` command.

During implementation run:

```bash
rm src/ado_ai_pr_review/adapters/pipeline.py
rm src/ado_ai_pr_review/runtime.py
rm azure-pipelines.ado-ai-review.yml
rm templates/pipeline.yml
```

- [ ] **Step 4: Remove unused `az devops` policy**

After `AdoToolset` no longer uses `az`, remove `az` from the binary allowlist unless another production module still needs it. Add:

```python
def test_command_policy_rejects_az_devops_invoke_after_rest_refactor() -> None:
    with pytest.raises(CommandRejectedError):
        CommandPolicy.default().validate(["az", "devops", "invoke"])
```

- [ ] **Step 5: Run CLI and policy tests**

Run:

```bash
.venv/bin/pytest tests/test_cli.py tests/test_tool_policy.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add -A src/ado_ai_pr_review/cli.py src/ado_ai_pr_review/adapters src/ado_ai_pr_review/runtime.py azure-pipelines.ado-ai-review.yml templates/pipeline.yml tests/test_cli.py src/ado_ai_pr_review/tool_policy.py tests/test_tool_policy.py
git commit -m "refactor: remove Azure DevOps pipeline mode"
```

## Task 7: Local Mode and Azure OpenAI Auth

**Files:**
- Modify: `src/ado_ai_pr_review/llm/azure_openai.py`
- Create: `tests/test_azure_openai_auth.py`
- Modify: `README.md`

- [ ] **Step 1: Add tests proving local Azure auth**

Create `tests/test_azure_openai_auth.py`:

```python
from __future__ import annotations

from ado_ai_pr_review.llm import azure_openai


def test_build_openai_client_uses_api_key_when_present(monkeypatch, mocker) -> None:
    monkeypatch.setenv("AZURE_OPENAI_BASE_URL", "https://example.openai.azure.com/openai/v1/")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "api-key")
    openai_cls = mocker.patch("ado_ai_pr_review.llm.azure_openai.OpenAI")

    azure_openai.build_openai_client()

    openai_cls.assert_called_once_with(api_key="api-key", base_url="https://example.openai.azure.com/openai/v1/")


def test_build_openai_client_uses_default_azure_credential_without_api_key(monkeypatch, mocker) -> None:
    monkeypatch.setenv("AZURE_OPENAI_BASE_URL", "https://example.openai.azure.com/openai/v1/")
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    credential_cls = mocker.patch("ado_ai_pr_review.llm.azure_openai.DefaultAzureCredential")
    token_provider = mocker.patch("ado_ai_pr_review.llm.azure_openai.get_bearer_token_provider")
    token_provider.return_value.return_value = "entra-openai-token"
    openai_cls = mocker.patch("ado_ai_pr_review.llm.azure_openai.OpenAI")

    azure_openai.build_openai_client()

    credential_cls.assert_called_once()
    token_provider.assert_called_once_with(credential_cls.return_value, "https://cognitiveservices.azure.com/.default")
    openai_cls.assert_called_once_with(api_key="entra-openai-token", base_url="https://example.openai.azure.com/openai/v1/")
```

- [ ] **Step 2: Run tests**

Run:

```bash
.venv/bin/pytest tests/test_azure_openai_auth.py tests/test_cli.py::test_local_runs_engine -v
```

Expected: PASS if current implementation already satisfies this.

- [ ] **Step 3: Update local README section**

Document:

```bash
az login
export AZURE_OPENAI_BASE_URL=https://acme-openai.openai.azure.com/openai/v1/
export AZURE_OPENAI_DEPLOYMENT=gpt-4o
unset AZURE_OPENAI_API_KEY
ado-ai-pr-review local --command review --target-branch main
```

Also document service principal env credentials for non-interactive local use: `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`.

- [ ] **Step 4: Commit**

```bash
git add src/ado_ai_pr_review/llm/azure_openai.py tests/test_azure_openai_auth.py README.md
git commit -m "test: cover local Azure authentication"
```

## Task 8: Infra and Marketplace Without PAT Collection

**Files:**
- Modify: `infra/mainTemplate.json`
- Modify: `infra/createUiDefinition.json`
- Modify: `docs/marketplace-testing.md`
- Modify: `docs/marketplace-publishing.md`
- Create: `tests/test_infra_auth.py`

- [ ] **Step 1: Write static infra tests**

Create `tests/test_infra_auth.py`:

```python
from __future__ import annotations

import json
from pathlib import Path


def test_arm_template_does_not_collect_ado_pat() -> None:
    template = json.loads(Path("infra/mainTemplate.json").read_text(encoding="utf-8"))
    text = json.dumps(template)

    assert "adoAuthToken" not in text
    assert "ADO_AUTH_TOKEN" not in text
    assert "ado-auth-token" not in text
    assert "AZURE_CLIENT_ID" in text


def test_create_ui_definition_does_not_collect_ado_pat() -> None:
    ui = json.loads(Path("infra/createUiDefinition.json").read_text(encoding="utf-8"))
    text = json.dumps(ui)

    assert "Azure DevOps PAT" not in text
    assert "adoAuthToken" not in text
    assert "managed identity" in text.lower() or "service principal" in text.lower()
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
.venv/bin/pytest tests/test_infra_auth.py -v
```

Expected: FAIL because infra still collects `adoAuthToken`.

- [ ] **Step 3: Update ARM template**

Remove:
- parameter `adoAuthToken`,
- Key Vault secret resource `ado-auth-token`,
- Container App secret entry `ado-auth-token`,
- env var `ADO_AUTH_TOKEN`.

Keep `AZURE_CLIENT_ID`.

Add outputs:

```json
"managedIdentityClientId": {
  "type": "string",
  "value": "[reference(resourceId('Microsoft.ManagedIdentity/userAssignedIdentities', variables('identityName'))).clientId]"
},
"managedIdentityPrincipalId": {
  "type": "string",
  "value": "[reference(resourceId('Microsoft.ManagedIdentity/userAssignedIdentities', variables('identityName'))).principalId]"
}
```

- [ ] **Step 4: Update CreateUiDefinition**

Remove PAT/password input. Add an `InfoBox` explaining that after deployment the managed identity must be added to Azure DevOps organization users with Basic access and minimal repo/PR permissions.

- [ ] **Step 5: Update marketplace docs**

Use deployment examples without PAT. Add command to read `managedIdentityPrincipalId` from deployment outputs. Document that an ADO org admin must add that identity before webhook processing can read repos or post PR comments.

- [ ] **Step 6: Run infra tests and JSON validation**

Run:

```bash
.venv/bin/pytest tests/test_infra_auth.py -v
python -m json.tool infra/mainTemplate.json >/tmp/mainTemplate.validated.json
python -m json.tool infra/createUiDefinition.json >/tmp/createUiDefinition.validated.json
```

Expected: PASS and both JSON validations exit 0.

- [ ] **Step 7: Commit**

```bash
git add infra/mainTemplate.json infra/createUiDefinition.json docs/marketplace-testing.md docs/marketplace-publishing.md tests/test_infra_auth.py
git commit -m "chore: remove PAT collection from Azure deployment"
```

## Task 9: Documentation Without Pipeline Mode

**Files:**
- Modify: `README.md`
- Modify: `docs/operations/ado-ai-review.md`
- Modify: `docs/follow-ups/webhook-auth.md`
- Delete or rewrite historical docs containing pipeline mode where repository policy requires no trace.
- Create: `tests/test_docs_pipeline_removed.py`

- [ ] **Step 1: Add docs scan test**

Create `tests/test_docs_pipeline_removed.py`:

```python
from __future__ import annotations

from pathlib import Path

FORBIDDEN = [
    "AdoPipelineAdapter",
    "ado-ai-pr-review pipeline",
    "azure-pipelines.ado-ai-review.yml",
    "templates/pipeline.yml",
    "SYSTEM_ACCESSTOKEN",
    "Pipeline Setup",
    "pipeline mode",
]


def test_active_docs_do_not_describe_pipeline_mode() -> None:
    paths = [
        Path("README.md"),
        Path("docs/operations/ado-ai-review.md"),
        Path("docs/marketplace-testing.md"),
        Path("docs/marketplace-publishing.md"),
        Path("docs/follow-ups/webhook-auth.md"),
    ]

    for path in paths:
        text = path.read_text(encoding="utf-8")
        for forbidden in FORBIDDEN:
            assert forbidden not in text, f"{path}: contains {forbidden!r}"
```

- [ ] **Step 2: Run docs test**

Run:

```bash
.venv/bin/pytest tests/test_docs_pipeline_removed.py -v
```

Expected: FAIL while README and operations docs still describe pipeline setup.

- [ ] **Step 3: Rewrite README**

README structure after rewrite:
- `Supported Modes`: Webhook and Local only.
- `Azure DevOps Identity Onboarding`: add managed identity/service principal to ADO org, assign Basic access, project membership, Code Read, Pull Request Contribute, branch Contribute only for `/ai fix`, Azure RBAC does not grant ADO permissions, first onboarding requires admin.
- `Webhook / Container Apps`: default `ADO_AUTH_MODE=entra`, explicit `ADO_AUTH_MODE=pat` plus `ADO_PAT` only for local/test fallback, inbound Basic Auth remains webhook protection.
- `Local Mode`: `az login` and env credential examples.
- `Security Boundary`.
- `Local Development`.

- [ ] **Step 4: Rewrite operations doc**

Replace with operational checklist:
- Container App has `AZURE_CLIENT_ID`.
- Managed identity principal ID is added to ADO org users.
- ADO repo/project permissions are assigned.
- Service hooks use Basic Auth.
- `ADO_AUTH_MODE` absent or `entra`.
- Temporary PAT fallback uses `ADO_AUTH_MODE=pat` and `ADO_PAT`, explicitly marked local/test only.

- [ ] **Step 5: Remove historical pipeline docs if no-trace policy applies**

Delete generated planning/status/spec files that describe pipeline mode, excluding this plan:

```bash
rm docs/superpowers/specs/2026-05-08-ado-ai-pr-review-design.md
rm docs/superpowers/specs/2026-05-09-adapter-layer-design.md
rm docs/superpowers/status/2026-05-09-ado-ai-pr-review-mvp-status.md
rm docs/superpowers/plans/2026-05-09-ado-ai-pr-review-mvp.md
rm docs/superpowers/plans/2026-05-09-bootstrap-and-docs.md
rm docs/superpowers/plans/2026-05-09-adapter-layer.md
```

- [ ] **Step 6: Run docs tests and scan**

Run:

```bash
.venv/bin/pytest tests/test_docs_pipeline_removed.py -v
rg -n "AdoPipelineAdapter|ado-ai-pr-review pipeline|azure-pipelines\\.ado-ai-review|templates/pipeline\\.yml|SYSTEM_ACCESSTOKEN|Pipeline Setup|pipeline mode" README.md docs src tests infra --glob '!docs/superpowers/plans/2026-05-12-ado-auth-pipeline-removal.md'
```

Expected: pytest PASS and `rg` exits 1 with no matches.

- [ ] **Step 7: Commit**

```bash
git add -A README.md docs tests/test_docs_pipeline_removed.py
git commit -m "docs: document Entra-based webhook deployment"
```

## Task 10: End-To-End Verification

**Files:**
- No code changes unless verification reveals a defect.

- [ ] **Step 1: Run focused auth/webhook/local tests**

Run:

```bash
.venv/bin/pytest \
  tests/test_ado_auth.py \
  tests/test_ado_rest.py \
  tests/test_ado_toolset.py \
  tests/test_git_toolset.py \
  tests/test_webhook_adapter.py \
  tests/test_webhook_server.py \
  tests/test_cli.py \
  tests/test_local_adapter.py \
  tests/test_azure_openai_auth.py \
  tests/test_infra_auth.py \
  tests/test_docs_pipeline_removed.py \
  -v
```

Expected: PASS.

- [ ] **Step 2: Run full test suite**

Run:

```bash
.venv/bin/pytest
```

Expected: PASS.

- [ ] **Step 3: Run lint/type checks**

Run:

```bash
.venv/bin/ruff check src tests
.venv/bin/mypy src
```

Expected: both commands exit 0.

- [ ] **Step 4: Run no-trace scans**

Run:

```bash
rg -n "AdoPipelineAdapter|RuntimeContext|SYSTEM_ACCESSTOKEN|BUILD_BUILDID|SYSTEM_PULLREQUEST|ado-ai-pr-review pipeline|azure-pipelines\\.ado-ai-review|templates/pipeline\\.yml|pipeline mode" src tests README.md docs infra templates pyproject.toml --glob '!docs/superpowers/plans/2026-05-12-ado-auth-pipeline-removal.md'
```

Expected: no matches.

Run:

```bash
rg -n "https://:[^@]+@|ADO_AUTH_TOKEN|ado-auth-token|adoAuthToken" src tests README.md docs infra --glob '!docs/superpowers/plans/2026-05-12-ado-auth-pipeline-removal.md'
```

Expected: no matches.

- [ ] **Step 5: Verify CLI commands**

Run:

```bash
ado-ai-pr-review --help
ado-ai-pr-review local --help
ado-ai-pr-review serve --help
ado-ai-pr-review pipeline --help
```

Expected:
- first three commands exit 0,
- `pipeline` exits non-zero because the command no longer exists.

- [ ] **Step 6: Verify local Azure auth manually**

Run:

```bash
az login
export AZURE_OPENAI_BASE_URL=https://acme-openai.openai.azure.com/openai/v1/
export AZURE_OPENAI_DEPLOYMENT=gpt-4o
unset AZURE_OPENAI_API_KEY
ado-ai-pr-review local --command review --repo-root . --target-branch main
```

Expected: local mode starts, computes git diff against `origin/main...HEAD`, and uses `DefaultAzureCredential` for Azure OpenAI.

- [ ] **Step 7: Verify PAT fallback is explicit**

Run:

```bash
export ADO_AUTH_MODE=pat
export ADO_PAT=pat-used-only-for-local-test
python - <<'PY'
from ado_ai_pr_review.auth import build_ado_auth_strategy
print(type(build_ado_auth_strategy()).__name__)
PY
```

Expected output:

```text
PatAdoAuthStrategy
```

Then:

```bash
unset ADO_AUTH_MODE
python - <<'PY'
from ado_ai_pr_review.auth import build_ado_auth_strategy
print(type(build_ado_auth_strategy()).__name__)
PY
```

Expected output:

```text
EntraAdoAuthStrategy
```

- [ ] **Step 8: Commit verification fixes only if needed**

```bash
git status --short
git add -A
git commit -m "test: verify Entra auth and pipeline removal"
```

Skip the commit if `git status --short` is empty.

## Acceptance Criteria

- `ado-ai-pr-review pipeline` is not registered.
- `src/ado_ai_pr_review/adapters/pipeline.py`, `src/ado_ai_pr_review/runtime.py`, `azure-pipelines.ado-ai-review.yml`, and `templates/pipeline.yml` are removed.
- Webhook uses `build_ado_auth_strategy()` and passes `AdoAuthStrategy` into `AdoWebhookAdapter`.
- Default ADO auth is Entra via `DefaultAzureCredential`.
- PAT requires `ADO_AUTH_MODE=pat` plus `ADO_PAT`; no production docs or infra collect PAT by default.
- Git clone uses `GIT_CONFIG_KEY_0=http.extraheader` and never injects token into URL.
- ADO REST calls use `AdoRestClient` with `Authorization` from strategy.
- Local mode still runs with Azure OpenAI via `AZURE_OPENAI_API_KEY` or `DefaultAzureCredential` after `az login` / env credentials.
- Infra deploys managed identity and outputs principal/client IDs for ADO onboarding.
- Docs state that service principal/managed identity must be added to Azure DevOps organization and assigned Azure DevOps permissions separately from Azure RBAC.
- Full suite, ruff, mypy, JSON validation, and no-trace scans pass.

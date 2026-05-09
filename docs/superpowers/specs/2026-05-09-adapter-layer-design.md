# Adapter Layer Design

Date: 2026-05-09

## Context

The ADO AI PR Review worker was built as a pipeline-only CLI tool. All orchestration logic lives in `cli.py:run_worker()` and `RuntimeContext.from_env()` hardcodes ten Azure DevOps pipeline environment variables. The goal of this refactor is to decouple presentation and access from core review logic so that the same engine can run in three modes: as an Azure DevOps pipeline job (current), as a local CLI tool against the current git branch, and as a webhook receiver running persistently in Azure Container Apps.

## Goals

- Introduce a `PlatformAdapter` protocol and `LLMPort` protocol as the only boundaries between the engine and the outside world.
- Extract review orchestration from `cli.py` into a standalone `ReviewEngine` class.
- Implement three platform adapters: `AdoPipelineAdapter` (current behavior), `LocalCliAdapter` (local git diff, stdout output), `AdoWebhookAdapter` (FastAPI + clone to temp dir).
- Add an optional `GitHubCopilotClient` as a second `LLMPort` implementation usable in local mode.
- Keep all existing business logic modules unchanged: `commands.py`, `reviewer.py`, `security.py`, `indexer.py`, `context.py`, `fixer.py`, `publisher.py`, `bootstrap.py`, `models.py`.
- Ship a FastAPI webhook server reachable via `ado-ai-pr-review serve`.

## Non-Goals

- Rewriting existing business logic modules.
- Changing the `ReviewConfig` schema or `.ado-ai-review.yml` format.
- Adding GitHub PR platform support (only Azure DevOps).
- Replacing `az` CLI with direct HTTP in the pipeline or local adapter.
- Full async engine (webhook handler fires and forgets; engine stays synchronous).

## File Structure

```
src/ado_ai_pr_review/
    # NEW
    ports.py                   # PlatformAdapter, LLMPort protocols + PRContext, ReviewRequest
    engine.py                  # ReviewEngine
    adapters/
        __init__.py
        pipeline.py            # AdoPipelineAdapter
        local.py               # LocalCliAdapter
        webhook.py             # AdoWebhookAdapter + AdoWebhookPayload
    llm/
        __init__.py
        azure_openai.py        # ModelClient (moved from model_client.py)
        github_copilot.py      # GitHubCopilotClient (optional)
    webhook_server.py          # FastAPI app

    # CHANGED
    cli.py                     # adds pipeline / local / serve subcommands
    tool_policy.py             # adds gh auth token allowlist entry

    # REMOVED
    model_client.py            # replaced by llm/azure_openai.py

    # UNCHANGED
    runtime.py, ado_toolset.py, git_toolset.py, cli_runner.py
    commands.py, config.py, bootstrap.py, templates.py
    indexer.py, context.py, security.py, reviewer.py
    fixer.py, publisher.py, observability.py, models.py
    errors.py, diff.py, logging_config.py
```

## Ports

### `ports.py`

```python
@dataclass(frozen=True)
class PRContext:
    pr_id: int | None     # None in local mode
    source_branch: str
    target_branch: str
    is_fork: bool
    build_id: str

@dataclass(frozen=True)
class ReviewRequest:
    repo_root: Path
    diff_text: str        # already redacted by SecurityScanner
    command: ReviewCommand
    pr_context: PRContext

class PlatformAdapter(Protocol):
    def load_request(self) -> ReviewRequest: ...
    def publish_onboarding(self) -> None: ...
    def publish_review(self, result: ReviewResult) -> None: ...
    def publish_error(self, exc: BaseException) -> None: ...

class LLMPort(Protocol):
    def review_json(self, system_prompt: str, user_prompt: str) -> ReviewResult: ...
```

`SecurityScanner.scan_diff()` runs inside the adapter's `load_request()`, so `ReviewRequest.diff_text` is always redacted before the engine sees it. `PRContext.pr_id` being `None` is the contract that signals local mode to the publisher.

## ReviewEngine

```python
class ReviewEngine:
    def __init__(
        self,
        platform: PlatformAdapter,
        model: LLMPort,
        repo_root: Path,
    ) -> None: ...

    def run(self) -> ReviewCommand: ...
```

The engine run sequence:

1. `Bootstrapper().create_missing_files(repo_root)` — if files created, call `platform.publish_onboarding()` and return `ONBOARDING`.
2. `ReviewConfig.load(repo_root)`.
3. `platform.load_request()` — if this raises, call `platform.publish_error()` and re-raise.
4. If `request.command is ONBOARDING`, call `platform.publish_onboarding()` and return.
5. `RepoIndexer`, `ContextSelector`, `ReviewOrchestrator` — unchanged pure logic.
6. `platform.publish_review(result)`.
7. Return `request.command`.

The FIX path with `MechanicalFixer` stays inside the engine, unchanged logically. `_post_error_thread()` is removed from `cli.py` and replaced by `platform.publish_error()`.

## Adapters

### `AdoPipelineAdapter`

Wraps the current `cli.py:run_worker()` setup. Constructor reads `RuntimeContext.from_env()`, builds `CliRunner`, `AdoToolset`, `GitToolset`, `SuggestionPublisher`. `load_request()` calls `git.fetch()`, `git.diff()`, `SecurityScanner.scan_diff()`, and reads PR threads via `CommandRouter`. Publish methods delegate to `SuggestionPublisher`. No logic changes — this is a reorganization of existing code.

### `LocalCliAdapter`

```python
class LocalCliAdapter:
    def __init__(
        self,
        repo_root: Path,
        command: ReviewCommand,
        target_branch: str = "main",
    ) -> None: ...
```

`load_request()` runs `git diff origin/{target_branch}...HEAD` and reads the current branch name from git. Returns `PRContext(pr_id=None, ...)`. Requires no ADO environment variables. `CliRunner` is constructed without secrets.

`publish_review()` prints summary and findings to stdout using `typer.echo`. Severity and title are formatted for terminal readability. `publish_error()` writes to stderr.

### `AdoWebhookAdapter`

```python
class AdoWebhookAdapter:
    def __init__(
        self,
        payload: AdoWebhookPayload,
        auth_token: str,
        temp_dir: Path,
    ) -> None: ...
```

`AdoWebhookPayload` is a Pydantic model parsing the ADO service hook JSON (`resource.pullRequestId`, `resource.repository.remoteUrl`, `resource.repository.project.name`, event type, etc.).

The constructor clones the PR source branch into `temp_dir` with `git clone --depth 50 --branch {source_branch} {remote_url}`. It then builds `RuntimeContext` from payload fields (not env vars), `AdoToolset`, `GitToolset`, and `SuggestionPublisher` pointing at the cloned repo. `load_request()` and publish methods work identically to `AdoPipelineAdapter`.

Command detection: if the webhook event type is `ms.vss-code.git-pullrequest-comment-event`, parse the comment from the payload directly. Otherwise fall back to reading all threads via `CommandRouter`.

The `auth_token` is injected into the git clone URL as a credential and passed to `AdoToolset` as the system access token. The authenticated URL must not appear in logs — `CliRunner` redacts it the same way it redacts `SYSTEM_ACCESSTOKEN` in pipeline mode.

## Webhook Server

```python
# webhook_server.py
app = FastAPI()

@app.post("/webhook/ado")
async def handle_ado_webhook(payload: AdoWebhookPayload, request: Request) -> dict:
    auth_token = _extract_token(request)
    asyncio.create_task(asyncio.to_thread(_process_sync, payload, auth_token))
    return {"status": "accepted"}   # immediate 200, ADO does not wait

def _process_sync(payload: AdoWebhookPayload, auth_token: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        adapter = AdoWebhookAdapter(payload, auth_token, Path(tmp))
        model = build_model_client()   # AZURE_OPENAI_* env vars
        engine = ReviewEngine(platform=adapter, model=model, repo_root=Path(tmp))
        engine.run()

@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
```

ADO service hooks expect HTTP 200 within approximately 5 seconds. `asyncio.to_thread()` offloads the synchronous `engine.run()` to a thread pool so it does not block the event loop. The `/health` endpoint supports Container Apps liveness and readiness probes.

## CLI Entry Points

Three subcommands replace the current single `run` command:

```
ado-ai-pr-review pipeline [--repo-root .] [--dry-run] [--verbose]
ado-ai-pr-review local --command review|security|fix [--target-branch main] [--repo-root .]
ado-ai-pr-review serve [--host 0.0.0.0] [--port 8080] [--verbose]
```

`pipeline` is the current `run` command renamed. The `Dockerfile` sets `CMD ["pipeline"]` so existing pipeline YAML (`docker run ... --repo-root /repo`) requires no changes.

`local` builds `LocalCliAdapter` and calls `ReviewEngine.run()` synchronously.

`serve` calls `uvicorn.run(webhook_server.app, host=host, port=port)`.

## LLM Adapters

`ModelClient` is moved from `model_client.py` to `llm/azure_openai.py` unchanged. `build_openai_client()` stays in the same file.

`GitHubCopilotClient` (`llm/github_copilot.py`) implements `LLMPort` using the GitHub Copilot OpenAI-compatible endpoint. It fetches a token via `gh auth token` through `CliRunner`. `CommandPolicy` gains one new allowlisted shape: `["gh", "auth", "token"]`.

LLM selection in `local` subcommand:

```
ado-ai-pr-review local --command review --llm azure     # default, requires AZURE_OPENAI_*
ado-ai-pr-review local --command review --llm copilot   # uses gh CLI token
```

`pipeline` and `serve` always use `--llm azure`.

## Data Flow — Local Mode

```
ado-ai-pr-review local --command review
    │
    ├─ LocalCliAdapter.load_request()
    │      git diff origin/main...HEAD → SecurityScanner → ReviewRequest
    │
    ├─ ReviewEngine.run()
    │      Bootstrapper → ConfigLoader → RepoIndexer → ContextSelector
    │      → ReviewOrchestrator(LLMPort) → ReviewResult
    │
    └─ LocalCliAdapter.publish_review()
           typer.echo (summary + findings)
```

## Data Flow — Webhook Mode

```
ADO service hook → POST /webhook/ado
    │
    ├─ FastAPI handler → asyncio.create_task → immediate 200
    │
    └─ _process()
           AdoWebhookAdapter(payload, token, temp_dir)
               git clone → AdoToolset → GitToolset
               load_request() → CommandRouter → diff → SecurityScanner
           ReviewEngine.run()
               Bootstrapper → ConfigLoader → RepoIndexer → ContextSelector
               → ReviewOrchestrator(LLMPort) → ReviewResult
           AdoWebhookAdapter.publish_review()
               SuggestionPublisher → ADO REST (az devops invoke)
```

## Testing

- Unit tests for `ReviewEngine` using a mock `PlatformAdapter` and mock `LLMPort`.
- Unit tests for `LocalCliAdapter.load_request()` using a mock `GitToolset`.
- Unit tests for `AdoWebhookPayload` parsing against sample ADO webhook payloads.
- Unit tests for `GitHubCopilotClient` token extraction using a mock `CliRunner`.
- Existing unit tests for `CommandRouter`, `SecurityScanner`, `RepoIndexer`, `ContextSelector`, `SuggestionPublisher`, `MechanicalFixer` remain unchanged.
- `AdoPipelineAdapter` has no new unit tests beyond existing coverage — its logic is the same code reorganized.

## Open Questions For Implementation

- Confirm the exact ADO service hook JSON shape for `ms.vss-code.git-pullrequest-comment-event` and `ms.vss-code.git-pullrequest-updated` to finalize `AdoWebhookPayload` field mapping.
- Decide whether `auth_token` in webhook mode comes from a request header (custom ADO service hook basic auth), a shared secret env var, or both.
- Confirm GitHub Copilot API base URL and whether the `gpt-4o` deployment name is stable for Copilot subscribers.

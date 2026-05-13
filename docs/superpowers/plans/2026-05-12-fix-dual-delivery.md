# Fix Command: Dual-Delivery Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign `/ai fix` so the LLM chooses per finding between two delivery modes: an inline ADO suggestion (just the replacement lines, posted as a `codeChange` thread for one-click Apply) or a fix-branch PR (full file committed and pushed).

**Architecture:** A new `FixPlanResult` Pydantic model (with two separate lists: `inline_suggestions` and `fix_branch_changes`) replaces the current `ReviewResult` for the fix command. A new `fix_plan_json` method on `LLMPort` handles the new schema. `SuggestionPublisher` posts `InlineSuggestion` items as `codeChange` threads (ADO "Apply" button); `MechanicalFixer` applies `FixBranchChange` items as commits on a new branch, then opens a PR as before.

**Tech Stack:** Python 3.13, Pydantic v2, pytest, uv (`uv run pytest`), existing `ModelClient` (Azure OpenAI Responses API) + `GitHubCopilotClient` (chat completions), ADO REST `threads` API.

---

## File Map

| File | Change |
|------|--------|
| `src/ado_ai_pr_review/models.py` | Add `InlineSuggestion`, `FixBranchChange`, `FixPlanResult` |
| `src/ado_ai_pr_review/ports.py` | Add `fix_plan_json` to `LLMPort`; add `publish_fix_result` to `PlatformAdapter` |
| `src/ado_ai_pr_review/reviewer.py` | Add `FIX_PLAN_SYSTEM_PROMPT`, `_build_fix_plan_system_prompt()`, `ReviewOrchestrator.fix_plan()` |
| `src/ado_ai_pr_review/llm/azure_openai.py` | Add `ModelClient.fix_plan_json()` |
| `src/ado_ai_pr_review/llm/github_copilot.py` | Add `_FIX_PLAN_SCHEMA_SUFFIX`, `GitHubCopilotClient.fix_plan_json()` |
| `src/ado_ai_pr_review/publisher.py` | Add `publish_fix_result()`, `_publish_inline_suggestion()` |
| `src/ado_ai_pr_review/adapters/webhook.py` | Add `AdoWebhookAdapter.publish_fix_result()` |
| `src/ado_ai_pr_review/adapters/local.py` | Add `LocalCliAdapter.publish_fix_result()` |
| `src/ado_ai_pr_review/handlers/fix.py` | Rewrite `FixHandler.handle()` — use `fix_plan()` + new models |
| `tests/test_model_client.py` | Add model-validation tests for new types + `ModelClient.fix_plan_json` test |
| `tests/test_github_copilot.py` | Add `GitHubCopilotClient.fix_plan_json` test |
| `tests/test_publisher.py` | Add `publish_fix_result` tests |
| `tests/test_reviewer.py` | Add `ReviewOrchestrator.fix_plan()` test |
| `tests/test_engine.py` | Update `_MockLLM` + `_MockPlatform`; update fix engine test |
| `tests/test_reviewer.py` | (Task 8) assert old FIX prompt is gone |

---

## Task 1: New Pydantic models — `InlineSuggestion`, `FixBranchChange`, `FixPlanResult`

**Files:**
- Modify: `src/ado_ai_pr_review/models.py`
- Test: `tests/test_model_client.py`

- [ ] **Step 1: Write failing tests**

Add to the bottom of `tests/test_model_client.py`:

```python
from ado_ai_pr_review.models import (
    FixBranchChange,
    FixPlanResult,
    FindingSeverity,
    InlineSuggestion,
)


def test_fix_plan_result_validates_inline_suggestion() -> None:
    result = FixPlanResult.model_validate(
        {
            "summary": "One inline fix.",
            "inline_suggestions": [
                {
                    "file_path": "src/app.py",
                    "line_start": 10,
                    "line_end": 12,
                    "severity": "high",
                    "title": "Fix NaN id",
                    "body": "Use 0 as fallback.",
                    "replacement_lines": "  const id = Math.max(0, ...ids) + 1;",
                }
            ],
        }
    )
    assert result.inline_suggestions[0].file_path == "src/app.py"
    assert result.inline_suggestions[0].severity is FindingSeverity.HIGH


def test_fix_plan_result_validates_fix_branch_change() -> None:
    result = FixPlanResult.model_validate(
        {
            "summary": "One branch fix.",
            "fix_branch_changes": [
                {
                    "file_path": "src/store.ts",
                    "title": "Fix remove filter",
                    "body": "Invert the filter condition.",
                    "full_file_content": "entire file here",
                    "commit_message": "fix: correct removeTodo filter",
                }
            ],
        }
    )
    assert result.fix_branch_changes[0].commit_message == "fix: correct removeTodo filter"


def test_inline_suggestion_rejects_descending_line_range() -> None:
    with pytest.raises(ValidationError):
        InlineSuggestion.model_validate(
            {
                "file_path": "src/app.py",
                "line_start": 20,
                "line_end": 10,
                "severity": "low",
                "title": "t",
                "body": "b",
                "replacement_lines": "x",
            }
        )


def test_fix_plan_result_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        FixPlanResult.model_validate({"summary": "ok", "unexpected": True})
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_model_client.py::test_fix_plan_result_validates_inline_suggestion -v
```

Expected: `FAILED` — `ImportError: cannot import name 'InlineSuggestion'`

- [ ] **Step 3: Add the new models to `models.py`**

Add the following three classes at the end of `src/ado_ai_pr_review/models.py` (after `FixCandidate`):

```python
class InlineSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_path: str
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    severity: FindingSeverity
    title: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=4_000)
    replacement_lines: str = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_line_range(self) -> Self:
        if self.line_end < self.line_start:
            raise ValueError("line_end must be >= line_start")
        return self


class FixBranchChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_path: str
    title: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=4_000)
    full_file_content: str = Field(min_length=1)
    commit_message: str = Field(min_length=1, max_length=256)


class FixPlanResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    summary: str = Field(min_length=1, max_length=4_000)
    inline_suggestions: list[InlineSuggestion] = Field(default_factory=list)
    fix_branch_changes: list[FixBranchChange] = Field(default_factory=list)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_model_client.py -v
```

Expected: all tests in the file pass.

- [ ] **Step 5: Commit**

```bash
git add src/ado_ai_pr_review/models.py tests/test_model_client.py
git commit -m "feat: add InlineSuggestion, FixBranchChange, FixPlanResult models"
```

---

## Task 2: `LLMPort.fix_plan_json` + `ReviewOrchestrator.fix_plan()` + system prompt

**Files:**
- Modify: `src/ado_ai_pr_review/ports.py`
- Modify: `src/ado_ai_pr_review/reviewer.py`
- Test: `tests/test_reviewer.py`

- [ ] **Step 1: Write failing test**

Add to the bottom of `tests/test_reviewer.py`:

```python
def test_orchestrator_fix_plan_calls_fix_plan_json(mocker: MockerFixture) -> None:
    from ado_ai_pr_review.models import FixPlanResult

    model_client = mocker.Mock()
    model_client.fix_plan_json.return_value = FixPlanResult(summary="one fix")
    orchestrator = ReviewOrchestrator(model_client=model_client)

    result = orchestrator.fix_plan(
        guidance=["No secrets."],
        selected_files=["src/store.ts\ncode"],
        diff_text="+ const x = 1;",
        local_security_summary="Local findings: 0",
    )

    assert result.summary == "one fix"
    call_kwargs = model_client.fix_plan_json.call_args.kwargs
    assert "+ const x = 1;" in call_kwargs["user_prompt"]
    assert "No secrets." in call_kwargs["user_prompt"]
    assert "inline_suggestions" in call_kwargs["system_prompt"]
    assert "fix_branch_changes" in call_kwargs["system_prompt"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_reviewer.py::test_orchestrator_fix_plan_calls_fix_plan_json -v
```

Expected: `FAILED` — `AttributeError: 'ReviewOrchestrator' object has no attribute 'fix_plan'`

- [ ] **Step 3: Add `fix_plan_json` to `LLMPort` in `ports.py`**

The current `ports.py` imports from models. Add `FixPlanResult` to the import and add the method to `LLMPort`:

```python
# Change the models import line from:
from ado_ai_pr_review.models import Finding, FixCandidate, ReviewCommand, ReviewResult
# to:
from ado_ai_pr_review.models import Finding, FixCandidate, FixPlanResult, ReviewCommand, ReviewResult
```

Add `fix_plan_json` method to `LLMPort`:

```python
@runtime_checkable
class LLMPort(Protocol):
    def review_json(self, system_prompt: str, user_prompt: str) -> ReviewResult: ...
    def fix_plan_json(self, system_prompt: str, user_prompt: str) -> FixPlanResult: ...
```

- [ ] **Step 4: Add `FIX_PLAN_SYSTEM_PROMPT`, `_build_fix_plan_system_prompt()`, and `fix_plan()` to `reviewer.py`**

Add `FixPlanResult` to the import at the top of `reviewer.py`:

```python
from ado_ai_pr_review.models import FixPlanResult, ReviewCommand, ReviewResult
```

Add the following after `FIX_SYSTEM_PROMPT` (before `_SYSTEM_PROMPT`):

```python
def _build_fix_plan_system_prompt() -> str:
    schema_json = json.dumps(FixPlanResult.model_json_schema(), indent=2)
    return (
        "You are a code fixer for an Azure DevOps pull request.\n"
        "Return ONLY raw JSON (no markdown, no prose) matching the schema below.\n"
        "\n"
        "For each fixable issue choose a delivery mode:\n"
        "\n"
        "inline_suggestions — for small, localised changes (1-10 contiguous lines).\n"
        "  replacement_lines: ONLY the new lines that replace line_start..line_end.\n"
        "  Do NOT include surrounding context. Do NOT include the full file.\n"
        "  ADO replaces exactly line_start..line_end with these lines when applied.\n"
        "\n"
        "fix_branch_changes — for complex, multi-line, or multi-location changes.\n"
        "  full_file_content: THE COMPLETE NEW CONTENT OF THE FILE after the fix.\n"
        "  No ellipsis, no truncation, no '// ... rest of file'.\n"
        "\n"
        "Decision rule: 1-10 contiguous lines changed in one location → inline_suggestion.\n"
        "More lines or changes in multiple locations → fix_branch_change.\n"
        "\n"
        "Only propose mechanical fixes: formatting, imports, naming, type annotations,\n"
        "simple logic bugs visible in the diff.\n"
        "Do not change business logic, algorithms, or API contracts.\n"
        "Do not include secret values.\n"
        "\n"
        "Schema:\n"
        + schema_json
    )


FIX_PLAN_SYSTEM_PROMPT = _build_fix_plan_system_prompt()
```

Add `fix_plan()` method to `ReviewOrchestrator` (after `run()`):

```python
def fix_plan(
    self,
    guidance: list[str],
    selected_files: list[str],
    diff_text: str,
    local_security_summary: str,
) -> FixPlanResult:
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
    return self._model_client.fix_plan_json(
        system_prompt=FIX_PLAN_SYSTEM_PROMPT,
        user_prompt=user_prompt,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/test_reviewer.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/ado_ai_pr_review/ports.py src/ado_ai_pr_review/reviewer.py tests/test_reviewer.py
git commit -m "feat: add LLMPort.fix_plan_json, ReviewOrchestrator.fix_plan, FIX_PLAN_SYSTEM_PROMPT"
```

---

## Task 3: `ModelClient.fix_plan_json` (Azure OpenAI)

**Files:**
- Modify: `src/ado_ai_pr_review/llm/azure_openai.py`
- Test: `tests/test_model_client.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_model_client.py`:

```python
def test_model_client_parses_fix_plan_json(mocker: MockerFixture) -> None:
    from ado_ai_pr_review.llm.azure_openai import ModelClient

    openai_client = mocker.Mock()
    openai_client.responses.create.return_value.output_text = (
        '{"summary":"two fixes",'
        '"inline_suggestions":[{"file_path":"src/app.py","line_start":5,"line_end":5,'
        '"severity":"high","title":"Fix x","body":"Fix it.","replacement_lines":"const x = 1;"}],'
        '"fix_branch_changes":[]}'
    )
    client = ModelClient(openai_client=openai_client, deployment="review-model")

    result = client.fix_plan_json(system_prompt="system", user_prompt="user")

    assert result.summary == "two fixes"
    assert len(result.inline_suggestions) == 1
    assert result.inline_suggestions[0].file_path == "src/app.py"
    openai_client.responses.create.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_model_client.py::test_model_client_parses_fix_plan_json -v
```

Expected: `FAILED` — `AttributeError: 'ModelClient' object has no attribute 'fix_plan_json'`

- [ ] **Step 3: Add `fix_plan_json` to `ModelClient`**

Change the import line at the top of `src/ado_ai_pr_review/llm/azure_openai.py` from:
```python
from ado_ai_pr_review.models import ReviewResult
```
to:
```python
from ado_ai_pr_review.models import FixPlanResult, ReviewResult
```

Add the method after `review_json`:

```python
def fix_plan_json(self, system_prompt: str, user_prompt: str) -> FixPlanResult:
    response = self._openai_client.responses.create(
        model=self._deployment,
        instructions=system_prompt,
        input=user_prompt,
        text={
            "format": {
                "type": "json_schema",
                "name": "fix_plan_result",
                "schema": FixPlanResult.model_json_schema(),
                "strict": True,
            }
        },
    )
    output_text = str(response.output_text)
    try:
        return FixPlanResult.model_validate(json.loads(output_text))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ModelOutputError(f"Model returned invalid fix plan JSON: {exc}") from exc
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_model_client.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/ado_ai_pr_review/llm/azure_openai.py tests/test_model_client.py
git commit -m "feat: add ModelClient.fix_plan_json for Azure OpenAI"
```

---

## Task 4: `GitHubCopilotClient.fix_plan_json`

**Files:**
- Modify: `src/ado_ai_pr_review/llm/github_copilot.py`
- Test: `tests/test_github_copilot.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_github_copilot.py`:

```python
def test_github_copilot_client_fix_plan_json_parses_response(mocker) -> None:  # type: ignore[no-untyped-def]
    from ado_ai_pr_review.llm.github_copilot import GitHubCopilotClient

    proc_mock = MagicMock()
    proc_mock.stdout = "ghu_test_token_12345\n"
    mocker.patch("ado_ai_pr_review.llm.github_copilot.subprocess.run", return_value=proc_mock)

    openai_mock = mocker.patch("ado_ai_pr_review.llm.github_copilot.OpenAI")
    mock_message = MagicMock()
    mock_message.content = '{"summary":"fixed","inline_suggestions":[],"fix_branch_changes":[]}'
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    openai_mock.return_value.chat.completions.create.return_value.choices = [mock_choice]

    client = GitHubCopilotClient()
    # FIX_PLAN_SYSTEM_PROMPT ends with "}" so suffix is empty
    from ado_ai_pr_review.reviewer import FIX_PLAN_SYSTEM_PROMPT
    result = client.fix_plan_json(system_prompt=FIX_PLAN_SYSTEM_PROMPT, user_prompt="user")

    assert result.summary == "fixed"
    assert result.inline_suggestions == []
    assert result.fix_branch_changes == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_github_copilot.py::test_github_copilot_client_fix_plan_json_parses_response -v
```

Expected: `FAILED` — `AttributeError: 'GitHubCopilotClient' object has no attribute 'fix_plan_json'`

- [ ] **Step 3: Add `_FIX_PLAN_SCHEMA_SUFFIX` and `fix_plan_json` to `github_copilot.py`**

Change the import at the top from:
```python
from ado_ai_pr_review.models import ReviewResult
```
to:
```python
from ado_ai_pr_review.models import FixPlanResult, ReviewResult
```

Add the module-level constant after `_SCHEMA_SUFFIX`:

```python
_FIX_PLAN_SCHEMA_SUFFIX = (
    "\n\nYou MUST return raw JSON (no markdown fences) matching this exact schema:\n"
    + json.dumps(FixPlanResult.model_json_schema(), indent=2)
)
```

Add the method to `GitHubCopilotClient` after `review_json`:

```python
def fix_plan_json(self, system_prompt: str, user_prompt: str) -> FixPlanResult:
    # FIX_PLAN_SYSTEM_PROMPT embeds the schema and ends with "}"; suffix is empty.
    # _FIX_PLAN_SCHEMA_SUFFIX is a fallback for callers that provide a schema-free prompt.
    suffix = "" if system_prompt.rstrip().endswith("}") else _FIX_PLAN_SCHEMA_SUFFIX
    response = self._client.chat.completions.create(
        model=_DEPLOYMENT,
        messages=[
            {"role": "system", "content": system_prompt + suffix},
            {"role": "user", "content": user_prompt},
        ],
    )
    raw = response.choices[0].message.content or ""
    output_text = _extract_json(raw)
    try:
        return FixPlanResult.model_validate(json.loads(output_text))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ModelOutputError(f"Model returned invalid fix plan JSON: {exc}") from exc
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_github_copilot.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/ado_ai_pr_review/llm/github_copilot.py tests/test_github_copilot.py
git commit -m "feat: add GitHubCopilotClient.fix_plan_json"
```

---

## Task 5: `SuggestionPublisher.publish_fix_result`

**Files:**
- Modify: `src/ado_ai_pr_review/publisher.py`
- Test: `tests/test_publisher.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_publisher.py`:

```python
from ado_ai_pr_review.models import (
    Finding,
    FindingSeverity,
    FindingType,
    FixPlanResult,
    InlineSuggestion,
    ReviewResult,
)


def test_publisher_publish_fix_result_posts_summary_and_inline_suggestion(mocker: MockerFixture) -> None:
    ado = mocker.Mock()
    publisher = SuggestionPublisher(ado_toolset=ado)
    result = FixPlanResult(
        summary="Two fixes.",
        inline_suggestions=[
            InlineSuggestion(
                file_path="src/store.ts",
                line_start=10,
                line_end=12,
                severity=FindingSeverity.HIGH,
                title="Fix id",
                body="Use max with 0.",
                replacement_lines="  const id = Math.max(0, ...ids) + 1;",
            )
        ],
    )

    publisher.publish_fix_result(result)

    assert ado.create_pr_thread.call_count == 2
    summary_body = ado.create_pr_thread.call_args_list[0].kwargs["body"]
    assert "Two fixes." in summary_body["comments"][0]["content"]
    assert summary_body["comments"][0]["commentType"] == "text"
    assert _BOT_MARKER in summary_body["comments"][0]["content"]
    suggestion_body = ado.create_pr_thread.call_args_list[1].kwargs["body"]
    assert suggestion_body["threadContext"]["filePath"] == "src/store.ts"
    assert suggestion_body["threadContext"]["rightFileStart"]["line"] == 10
    assert suggestion_body["threadContext"]["rightFileEnd"]["line"] == 12
    assert suggestion_body["comments"][0]["commentType"] == "codeChange"
    assert "Fix id" in suggestion_body["comments"][0]["content"]
    assert "const id = Math.max" in suggestion_body["comments"][0]["content"]
    assert _BOT_MARKER in suggestion_body["comments"][0]["content"]


def test_publisher_publish_fix_result_no_inline_calls_when_empty(mocker: MockerFixture) -> None:
    ado = mocker.Mock()
    publisher = SuggestionPublisher(ado_toolset=ado)

    publisher.publish_fix_result(FixPlanResult(summary="No suggestions."))

    assert ado.create_pr_thread.call_count == 1  # summary only
    body = ado.create_pr_thread.call_args.kwargs["body"]
    assert body["properties"]["adoAiReview.kind"]["$value"] == "fix-summary"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_publisher.py::test_publisher_publish_fix_result_posts_summary_and_inline_suggestion -v
```

Expected: `FAILED` — `AttributeError: 'SuggestionPublisher' object has no attribute 'publish_fix_result'`

- [ ] **Step 3: Add `publish_fix_result` and `_publish_inline_suggestion` to `publisher.py`**

Change the import at the top of `publisher.py` from:
```python
from ado_ai_pr_review.models import Finding, ReviewResult
```
to:
```python
from ado_ai_pr_review.models import Finding, FixPlanResult, InlineSuggestion, ReviewResult
```

Add the two new methods to `SuggestionPublisher` after `_publish_finding`:

```python
def publish_fix_result(self, result: FixPlanResult) -> None:
    self._ado.create_pr_thread(
        body={
            "comments": [
                {
                    "parentCommentId": 0,
                    "content": f"ADO AI fix summary:\n\n{result.summary}\n\n{_BOT_MARKER}",
                    "commentType": "text",
                }
            ],
            "status": "active",
            "properties": {"adoAiReview.kind": {"$type": "System.String", "$value": "fix-summary"}},
        }
    )
    for suggestion in result.inline_suggestions:
        self._publish_inline_suggestion(suggestion)

def _publish_inline_suggestion(self, suggestion: InlineSuggestion) -> None:
    content = (
        f"**{suggestion.severity.value.upper()}: {suggestion.title}**\n\n"
        f"{suggestion.body}\n\n"
        f"```\n{suggestion.replacement_lines}\n```\n\n"
        f"{_BOT_MARKER}"
    )
    self._ado.create_pr_thread(
        body={
            "comments": [{"parentCommentId": 0, "content": content, "commentType": "codeChange"}],
            "status": "active",
            "properties": {"adoAiReview.kind": {"$type": "System.String", "$value": "fix-suggestion"}},
            "threadContext": {
                "filePath": suggestion.file_path,
                "rightFileStart": {"line": suggestion.line_start, "offset": 1},
                "rightFileEnd": {"line": suggestion.line_end, "offset": 1},
            },
        }
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_publisher.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/ado_ai_pr_review/publisher.py tests/test_publisher.py
git commit -m "feat: add SuggestionPublisher.publish_fix_result with codeChange inline suggestions"
```

---

## Task 6: `PlatformAdapter.publish_fix_result` + adapter implementations

**Files:**
- Modify: `src/ado_ai_pr_review/ports.py`
- Modify: `src/ado_ai_pr_review/adapters/webhook.py`
- Modify: `src/ado_ai_pr_review/adapters/local.py`

No new tests needed — `publish_fix_result` on the adapters delegates straight to `SuggestionPublisher` (already tested) or prints to terminal. The webhook adapter test suite must still pass.

- [ ] **Step 1: Add `publish_fix_result` to `PlatformAdapter` in `ports.py`**

The `PlatformAdapter` Protocol currently does not import `FixPlanResult`. The import was already updated in Task 2. Add the method to the Protocol:

```python
@runtime_checkable
class PlatformAdapter(Protocol):
    def load_request(self) -> ReviewRequest: ...
    def publish_onboarding(self) -> None: ...
    def publish_review(self, result: ReviewResult) -> None: ...
    def publish_error(self, exc: BaseException) -> None: ...
    def publish_fix_result(self, result: FixPlanResult) -> None: ...
    def create_fix_branch(
        self,
        candidates: list[FixCandidate],
        branch_name: str,
        target_branch: str,
    ) -> bool: ...
```

- [ ] **Step 2: Add `publish_fix_result` to `AdoWebhookAdapter` in `adapters/webhook.py`**

Change the models import in `webhook.py` from:
```python
from ado_ai_pr_review.models import FixCandidate, ReviewCommand, ReviewResult
```
to:
```python
from ado_ai_pr_review.models import FixCandidate, FixPlanResult, ReviewCommand, ReviewResult
```

Add the method after `publish_review`:

```python
def publish_fix_result(self, result: FixPlanResult) -> None:
    if self._publisher is not None:
        self._publisher.publish_fix_result(result)
```

- [ ] **Step 3: Add `publish_fix_result` to `LocalCliAdapter` in `adapters/local.py`**

Change the models import in `local.py` from:
```python
from ado_ai_pr_review.models import FixCandidate, ReviewCommand, ReviewResult
```
to:
```python
from ado_ai_pr_review.models import FixCandidate, FixPlanResult, ReviewCommand, ReviewResult
```

Add the method after `publish_review`:

```python
def publish_fix_result(self, result: FixPlanResult) -> None:
    typer.echo(f"\n=== AI Fix Summary ===\n{result.summary}")
    for s in result.inline_suggestions:
        typer.echo(f"\n[INLINE SUGGESTION] {s.title} ({s.file_path}:{s.line_start}-{s.line_end})")
        typer.echo(s.body)
        typer.echo(f"Replacement:\n{s.replacement_lines}")
    if result.fix_branch_changes:
        typer.echo(f"\n{len(result.fix_branch_changes)} fix branch change(s) will be applied to a branch.")
```

- [ ] **Step 4: Run existing test suite to verify nothing is broken**

```bash
uv run pytest tests/test_webhook_adapter.py tests/test_local_adapter.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/ado_ai_pr_review/ports.py src/ado_ai_pr_review/adapters/webhook.py src/ado_ai_pr_review/adapters/local.py
git commit -m "feat: add publish_fix_result to PlatformAdapter, webhook and local adapters"
```

---

## Task 7: Rewrite `FixHandler` + update engine tests

**Files:**
- Modify: `src/ado_ai_pr_review/handlers/fix.py`
- Modify: `tests/test_engine.py`

- [ ] **Step 1: Update `_MockLLM` and `_MockPlatform` in `test_engine.py`**

`_MockLLM` needs `fix_plan_json`. `_MockPlatform` needs `publish_fix_result`. Find the existing class definitions and update them:

```python
# Change _MockLLM to also have fix_plan_json:
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

    def fix_plan_json(self, system_prompt: str, user_prompt: str) -> FixPlanResult:
        self.calls += 1
        if self._raises is not None:
            raise self._raises
        return FixPlanResult(summary="ok")
```

Also add `FixPlanResult` to the imports at the top of `test_engine.py`:
```python
from ado_ai_pr_review.models import (
    Finding,
    FindingSeverity,
    FindingType,
    FixCandidate,
    FixPlanResult,
    ReviewCommand,
    ReviewResult,
)
```

```python
# Change _MockPlatform to add publish_fix_result:
class _MockPlatform:
    def __init__(self, request: ReviewRequest | None = None, load_raises: Exception | None = None) -> None:
        self._request = request
        self._load_raises = load_raises
        self.onboarding_called = False
        self.review_result: ReviewResult | None = None
        self.fix_result: FixPlanResult | None = None
        self.error: BaseException | None = None
        self.fix_branch_args: tuple[object, ...] | None = None
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

    def publish_fix_result(self, result: FixPlanResult) -> None:
        self.fix_result = result

    def publish_error(self, exc: BaseException) -> None:
        self.error = exc

    def create_fix_branch(self, candidates: list[FixCandidate], branch_name: str, target_branch: str) -> bool:
        self.fix_branch_args = (candidates, branch_name, target_branch)
        return self.fix_branch_return
```

- [ ] **Step 2: Run existing engine tests to confirm they still pass (before handler change)**

```bash
uv run pytest tests/test_engine.py -v
```

Expected: all tests pass (the handler hasn't changed yet, so the existing fix test will still use `review_json`).

- [ ] **Step 3: Rewrite `FixHandler.handle()` in `handlers/fix.py`**

Replace the entire file with:

```python
from __future__ import annotations

import logging

from ado_ai_pr_review.config import ReviewConfig
from ado_ai_pr_review.handlers.base import select_context
from ado_ai_pr_review.models import FixCandidate, FixDelivery, ReviewCommand
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
            result = ReviewOrchestrator(model).fix_plan(
                guidance=selected.always_on_guidance,
                selected_files=selected.dynamic_files,
                diff_text=request.diff_text,
                local_security_summary=local_security_summary,
            )
        except Exception as exc:
            logger.error("fix failed: %s", exc)
            platform.publish_error(exc)
            raise

        platform.publish_fix_result(result)

        fix_candidates = [
            FixCandidate(
                delivery=FixDelivery.FIX_BRANCH_CANDIDATE,
                title=c.title,
                explanation=c.body,
                file_path=c.file_path,
                replacement=c.full_file_content,
                commit_message=c.commit_message,
            )
            for c in result.fix_branch_changes
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
            findings_count=len(result.inline_suggestions) + len(result.fix_branch_changes),
            inline_suggestions_count=len(result.inline_suggestions),
            fix_pr_created=fix_pr_created,
        )
        logger.info("review metrics", extra=metrics.to_payload())
```

- [ ] **Step 4: Run engine tests to verify they pass**

```bash
uv run pytest tests/test_engine.py -v
```

Expected: all tests pass. In particular `test_engine_delegates_fix_branch_to_platform` still passes because `create_fix_branch` is still called (with an empty candidates list, which the mock accepts) and `fix_branch_args` is set.

- [ ] **Step 5: Run full test suite**

```bash
uv run pytest -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/ado_ai_pr_review/handlers/fix.py tests/test_engine.py
git commit -m "feat: rewrite FixHandler to use fix_plan() dual-delivery flow"
```

---

## Task 8: Remove old FIX prompt from `reviewer.py`

**Files:**
- Modify: `src/ado_ai_pr_review/reviewer.py`
- Test: `tests/test_reviewer.py`

- [ ] **Step 1: Write a test that will fail if the old FIX prompt is still present**

Add to `tests/test_reviewer.py`:

```python
def test_reviewer_has_no_legacy_fix_system_prompt() -> None:
    import ado_ai_pr_review.reviewer as reviewer_module

    assert not hasattr(reviewer_module, "FIX_SYSTEM_PROMPT"), (
        "FIX_SYSTEM_PROMPT was replaced by FIX_PLAN_SYSTEM_PROMPT in the dual-delivery redesign"
    )
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_reviewer.py::test_reviewer_has_no_legacy_fix_system_prompt -v
```

Expected: `FAILED` — `AssertionError: FIX_SYSTEM_PROMPT was replaced...`

- [ ] **Step 3: Remove `_build_fix_schema()`, `FIX_SYSTEM_PROMPT`, and the `ReviewCommand.FIX` entry from `_SYSTEM_PROMPT` in `reviewer.py`**

Delete the entire `_build_fix_schema()` function (roughly lines 23–38 in the original file).

Delete the entire `FIX_SYSTEM_PROMPT` constant and the `_build_fix_schema()` call at the end.

Change `_SYSTEM_PROMPT` from:
```python
_SYSTEM_PROMPT = {
    ReviewCommand.SECURITY: SECURITY_SYSTEM_PROMPT,
    ReviewCommand.FIX: FIX_SYSTEM_PROMPT,
}
```
to:
```python
_SYSTEM_PROMPT = {
    ReviewCommand.SECURITY: SECURITY_SYSTEM_PROMPT,
}
```

- [ ] **Step 4: Run full test suite to confirm nothing broke**

```bash
uv run pytest -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/ado_ai_pr_review/reviewer.py tests/test_reviewer.py
git commit -m "refactor: remove legacy FIX_SYSTEM_PROMPT; fix command now uses fix_plan() path"
```

---

## Self-Review

**Spec coverage:**

| Requirement | Task |
|-------------|------|
| LLM decides per finding: inline vs. fix branch | Task 2 — `FIX_PLAN_SYSTEM_PROMPT` with decision rule |
| Inline suggestion posts only replacement lines | Task 5 — `_publish_inline_suggestion` uses `replacement_lines` |
| Inline suggestion uses `codeChange` commentType | Task 5 — hard-coded `"codeChange"` |
| Fix branch uses full file (as before) | Task 7 — `FixBranchChange.full_file_content` mapped to `FixCandidate.replacement` |
| Azure OpenAI client supports new schema | Task 3 |
| GitHub Copilot client supports new schema | Task 4 |
| Both adapters expose `publish_fix_result` | Task 6 |
| Old single-mode FIX prompt removed | Task 8 |
| All existing tests still pass at each commit | Each task runs full suite or targeted suite |

**No placeholders found.**

**Type consistency check:**
- `FixPlanResult` defined in Task 1, used in Tasks 2–7 ✓
- `InlineSuggestion.replacement_lines` used in Task 5 `_publish_inline_suggestion` ✓
- `FixBranchChange.full_file_content` mapped to `FixCandidate.replacement` in Task 7 ✓
- `ReviewOrchestrator.fix_plan()` returns `FixPlanResult`, called by `FixHandler` ✓
- `LLMPort.fix_plan_json` added in Task 2, implemented in Tasks 3–4 ✓
- `PlatformAdapter.publish_fix_result` added in Task 6, called in Task 7 ✓

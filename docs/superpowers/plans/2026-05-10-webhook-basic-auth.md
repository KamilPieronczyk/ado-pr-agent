# Webhook Basic Auth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Protect `/webhook/ado` against unauthenticated callers by verifying the `Authorization: Basic` header that Azure DevOps sends natively with every webhook POST.

**Architecture:** A pure `_verify_basic_auth(request)` function reads `WEBHOOK_USERNAME` / `WEBHOOK_PASSWORD` from env vars at call time and raises `HTTP 401` if the header is missing or wrong. When neither env var is set the function is a no-op (gradual rollout — existing deployments keep working until the operator explicitly opts in). The `handle_ado_webhook` endpoint gains a FastAPI `Request` parameter so it can forward the raw headers to the verifier.

**Tech Stack:** FastAPI `Request`, Python `base64` + `secrets` (stdlib), pytest + `fastapi.testclient.TestClient`.

---

## Background — what ADO actually sends

When you create a webhook subscription in ADO and fill in "Basic authentication credentials", ADO encodes `username:password` in Base64 and sends:

```
Authorization: Basic <base64(username:password)>
```

This is standard HTTP Basic Auth (RFC 7617). The `consumerInputs.basicAuthCredentials` field in the ADO Service Hooks REST API is **required** — ADO will not call an endpoint without it once credentials are configured.

ADO docs warn: **"You must use HTTPS for basic authentication on a webhook"** — our Container Apps deployment already uses HTTPS-only ingress, so this prerequisite is already met.

---

## File Map

| File | Change |
|---|---|
| `src/ado_ai_pr_review/webhook_server.py` | Add `_verify_basic_auth(request)`, update endpoint signature |
| `tests/test_webhook_server.py` | Add 6 new test cases covering all auth scenarios |

No new files needed.

---

## Task 1: Write the failing tests

**Files:**
- Modify: `tests/test_webhook_server.py`

- [ ] **Step 1.1 — Append the new test cases to `tests/test_webhook_server.py`**

Add these imports at the top of the file (after the existing imports):

```python
import base64
```

Then append the following test functions at the bottom of the file:

```python
def _basic_auth_header(username: str, password: str) -> str:
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return f"Basic {token}"


def test_webhook_auth_skipped_when_env_vars_not_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """No WEBHOOK_USERNAME/PASSWORD configured → endpoint passes through (gradual rollout)."""
    monkeypatch.setenv("ADO_AUTH_TOKEN", "fake-token")
    monkeypatch.setenv("AZURE_OPENAI_BASE_URL", "https://example.com/")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "model")
    monkeypatch.delenv("WEBHOOK_USERNAME", raising=False)
    monkeypatch.delenv("WEBHOOK_PASSWORD", raising=False)

    with patch("ado_ai_pr_review.webhook_server._process_sync"):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/webhook/ado", json=_PR_CREATED_PAYLOAD)

    assert response.status_code == 200


def test_webhook_auth_accepted_with_correct_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADO_AUTH_TOKEN", "fake-token")
    monkeypatch.setenv("AZURE_OPENAI_BASE_URL", "https://example.com/")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "model")
    monkeypatch.setenv("WEBHOOK_USERNAME", "ado-ai")
    monkeypatch.setenv("WEBHOOK_PASSWORD", "s3cr3t")

    with patch("ado_ai_pr_review.webhook_server._process_sync"):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/webhook/ado",
            json=_PR_CREATED_PAYLOAD,
            headers={"Authorization": _basic_auth_header("ado-ai", "s3cr3t")},
        )

    assert response.status_code == 200


def test_webhook_auth_rejected_when_header_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADO_AUTH_TOKEN", "fake-token")
    monkeypatch.setenv("WEBHOOK_USERNAME", "ado-ai")
    monkeypatch.setenv("WEBHOOK_PASSWORD", "s3cr3t")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/webhook/ado", json=_PR_CREATED_PAYLOAD)

    assert response.status_code == 401


def test_webhook_auth_rejected_with_wrong_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADO_AUTH_TOKEN", "fake-token")
    monkeypatch.setenv("WEBHOOK_USERNAME", "ado-ai")
    monkeypatch.setenv("WEBHOOK_PASSWORD", "s3cr3t")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/webhook/ado",
        json=_PR_CREATED_PAYLOAD,
        headers={"Authorization": _basic_auth_header("ado-ai", "wrong")},
    )

    assert response.status_code == 401


def test_webhook_auth_rejected_with_wrong_username(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADO_AUTH_TOKEN", "fake-token")
    monkeypatch.setenv("WEBHOOK_USERNAME", "ado-ai")
    monkeypatch.setenv("WEBHOOK_PASSWORD", "s3cr3t")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/webhook/ado",
        json=_PR_CREATED_PAYLOAD,
        headers={"Authorization": _basic_auth_header("attacker", "s3cr3t")},
    )

    assert response.status_code == 401


def test_webhook_auth_rejected_with_malformed_base64(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADO_AUTH_TOKEN", "fake-token")
    monkeypatch.setenv("WEBHOOK_USERNAME", "ado-ai")
    monkeypatch.setenv("WEBHOOK_PASSWORD", "s3cr3t")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/webhook/ado",
        json=_PR_CREATED_PAYLOAD,
        headers={"Authorization": "Basic !!!not-valid-base64!!!"},
    )

    assert response.status_code == 401
```

- [ ] **Step 1.2 — Run only the new tests to verify they all FAIL**

```bash
cd /Users/kamilpieronczyk/Documents/private-work/ado-ai-pr-review
pytest tests/test_webhook_server.py::test_webhook_auth_skipped_when_env_vars_not_set \
       tests/test_webhook_server.py::test_webhook_auth_accepted_with_correct_credentials \
       tests/test_webhook_server.py::test_webhook_auth_rejected_when_header_missing \
       tests/test_webhook_server.py::test_webhook_auth_rejected_with_wrong_password \
       tests/test_webhook_server.py::test_webhook_auth_rejected_with_wrong_username \
       tests/test_webhook_server.py::test_webhook_auth_rejected_with_malformed_base64 \
       -v
```

Expected: all 6 FAIL — `_basic_auth_header` may be undefined, and the endpoint currently doesn't enforce auth so the 401-expecting tests will get 200.

---

## Task 2: Implement `_verify_basic_auth` and update the endpoint

**Files:**
- Modify: `src/ado_ai_pr_review/webhook_server.py`

- [ ] **Step 2.1 — Replace the contents of `webhook_server.py`**

```python
from __future__ import annotations

import asyncio
import base64
import logging
import os
import secrets
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request

from ado_ai_pr_review.adapters.webhook import AdoWebhookAdapter, AdoWebhookPayload
from ado_ai_pr_review.engine import ReviewEngine
from ado_ai_pr_review.llm.azure_openai import ModelClient, build_openai_client

logger = logging.getLogger(__name__)

_background_tasks: set[asyncio.Task[None]] = set()

app = FastAPI(title="ADO AI PR Review Webhook")


def _verify_basic_auth(request: Request) -> None:
    """Verify the incoming request carries valid Basic Auth credentials.

    When WEBHOOK_USERNAME or WEBHOOK_PASSWORD is not set the check is skipped
    entirely, which allows a gradual rollout: existing deployments keep working
    until the operator configures the credentials.

    Raises HTTPException(401) if credentials are configured but wrong/missing.
    """
    username = os.getenv("WEBHOOK_USERNAME", "")
    password = os.getenv("WEBHOOK_PASSWORD", "")
    if not username or not password:
        return

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Basic "):
        raise HTTPException(status_code=401, detail="Missing credentials")

    try:
        decoded = base64.b64decode(auth_header[6:]).decode()
        req_user, _, req_pass = decoded.partition(":")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    ok = secrets.compare_digest(req_user, username) and secrets.compare_digest(req_pass, password)
    if not ok:
        raise HTTPException(status_code=401, detail="Invalid credentials")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/webhook/ado")
async def handle_ado_webhook(payload: AdoWebhookPayload, request: Request) -> dict[str, str]:
    _verify_basic_auth(request)
    auth_token = os.getenv("ADO_AUTH_TOKEN")
    if not auth_token:
        raise HTTPException(status_code=401, detail="ADO_AUTH_TOKEN not configured")
    task = asyncio.create_task(asyncio.to_thread(_process_sync, payload, auth_token))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
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

- [ ] **Step 2.2 — Run the full test_webhook_server suite**

```bash
cd /Users/kamilpieronczyk/Documents/private-work/ado-ai-pr-review
pytest tests/test_webhook_server.py -v
```

Expected output — all 10 tests PASS:
```
tests/test_webhook_server.py::test_health_returns_ok PASSED
tests/test_webhook_server.py::test_webhook_returns_accepted_immediately PASSED
tests/test_webhook_server.py::test_webhook_returns_400_on_invalid_payload PASSED
tests/test_webhook_server.py::test_webhook_returns_401_without_auth_token PASSED
tests/test_webhook_server.py::test_webhook_auth_skipped_when_env_vars_not_set PASSED
tests/test_webhook_server.py::test_webhook_auth_accepted_with_correct_credentials PASSED
tests/test_webhook_server.py::test_webhook_auth_rejected_when_header_missing PASSED
tests/test_webhook_server.py::test_webhook_auth_rejected_with_wrong_password PASSED
tests/test_webhook_server.py::test_webhook_auth_rejected_with_wrong_username PASSED
tests/test_webhook_server.py::test_webhook_auth_rejected_with_malformed_base64 PASSED
```

- [ ] **Step 2.3 — Run the full test suite to catch any regressions**

```bash
cd /Users/kamilpieronczyk/Documents/private-work/ado-ai-pr-review
pytest -x -q
```

Expected: all tests pass, 0 failures.

- [ ] **Step 2.4 — Run linter**

```bash
cd /Users/kamilpieronczyk/Documents/private-work/ado-ai-pr-review
ruff check src/ado_ai_pr_review/webhook_server.py tests/test_webhook_server.py
```

Expected: no output (no issues).

---

## Task 3: Update the follow-up doc and commit

**Files:**
- Modify: `docs/follow-ups/webhook-auth.md`

- [ ] **Step 3.1 — Mark the follow-up as implemented**

Update the status line at the top of `docs/follow-ups/webhook-auth.md`:

```markdown
**Status:** Implemented — Option A (Basic Auth) shipped in feat/adapter-layer
```

- [ ] **Step 3.2 — Commit**

```bash
cd /Users/kamilpieronczyk/Documents/private-work/ado-ai-pr-review
git add src/ado_ai_pr_review/webhook_server.py \
        tests/test_webhook_server.py \
        docs/follow-ups/webhook-auth.md
git commit -m "feat: add Basic Auth verification to /webhook/ado endpoint

Reads WEBHOOK_USERNAME + WEBHOOK_PASSWORD from env vars at request time.
When neither is set the check is a no-op (gradual rollout).
Uses secrets.compare_digest to prevent timing attacks.

ADO natively supports basicAuthCredentials as a required field in
webHooks consumer subscriptions (see docs/follow-ups/webhook-auth.md)."
```

---

## ADO Service Hook Configuration (operator checklist)

After deployment, the operator must:

1. Generate a strong password:
   ```bash
   openssl rand -hex 32
   ```
2. Set Container Apps env vars:
   - `WEBHOOK_USERNAME` = `ado-ai` (or any non-empty string)
   - `WEBHOOK_PASSWORD` = the generated hex string
3. In ADO: **Project Settings → Service hooks → edit subscription → Action tab**:
   - Scroll to "Basic authentication credentials"
   - Enter `username:password` (ADO accepts `user:pass` format and Base64-encodes it automatically)
4. Click **Test** — expect HTTP 200.

---

## Self-Review

**Spec coverage:**
- ✅ `_verify_basic_auth` reads env vars at call time → testable with `monkeypatch.setenv`
- ✅ No credentials configured → no-op (gradual rollout) — Task 1 test `test_webhook_auth_skipped_when_env_vars_not_set`
- ✅ Correct credentials → 200 — `test_webhook_auth_accepted_with_correct_credentials`
- ✅ Missing header → 401 — `test_webhook_auth_rejected_when_header_missing`
- ✅ Wrong password → 401 — `test_webhook_auth_rejected_with_wrong_password`
- ✅ Wrong username → 401 — `test_webhook_auth_rejected_with_wrong_username`
- ✅ Malformed base64 → 401 — `test_webhook_auth_rejected_with_malformed_base64`
- ✅ `secrets.compare_digest` used → timing-safe comparison
- ✅ Password with colons handled by `partition(":")` — only splits on the first colon
- ✅ Existing tests unaffected — they don't set `WEBHOOK_USERNAME`/`WEBHOOK_PASSWORD` so auth is skipped

**Placeholder scan:** No TBDs, no "add appropriate error handling", no "similar to task N".

**Type consistency:** `_verify_basic_auth` takes `Request` (fastapi), returns `None`, raises `HTTPException` — consistent with FastAPI conventions used throughout the codebase.

from __future__ import annotations

import asyncio
import base64
import logging
import os
import secrets
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ado_ai_pr_review.adapters.webhook import AdoWebhookAdapter, AdoWebhookPayload
from ado_ai_pr_review.engine import ReviewEngine
from ado_ai_pr_review.llm.azure_openai import ModelClient, build_openai_client
from ado_ai_pr_review.ports import LLMPort

logger = logging.getLogger(__name__)

_background_tasks: set[asyncio.Task[None]] = set()


def _build_model() -> LLMPort:
    if os.getenv("LLM_PROVIDER") == "copilot":
        from ado_ai_pr_review.cli_runner import CliRunner
        from ado_ai_pr_review.llm.github_copilot import GitHubCopilotClient
        from ado_ai_pr_review.tool_policy import CommandPolicy

        runner = CliRunner(policy=CommandPolicy.default())
        return GitHubCopilotClient(runner=runner)
    return ModelClient(
        openai_client=build_openai_client(),  # type: ignore[arg-type]
        deployment=os.environ["AZURE_OPENAI_DEPLOYMENT"],
    )

app = FastAPI(title="ADO AI PR Review Webhook")


@app.exception_handler(RequestValidationError)
async def _log_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    body = await request.body()
    logger.error(
        "Webhook payload validation failed: %s | body=%.2000s",
        exc.errors(),
        body.decode("utf-8", errors="replace"),
    )
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


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
        raise HTTPException(status_code=401, detail="Invalid credentials") from None

    user_ok = secrets.compare_digest(req_user, username)
    pass_ok = secrets.compare_digest(req_pass, password)
    if not (user_ok and pass_ok):
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
            model = _build_model()
            engine = ReviewEngine(platform=adapter, model=model, repo_root=temp_dir)
            engine.run()
        except Exception:
            logger.exception("webhook processing failed for PR %s", payload.pull_request_id)

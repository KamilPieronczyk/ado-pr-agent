from __future__ import annotations

import asyncio
import base64
import logging
import os
import secrets
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ado_ai_pr_review.adapters.webhook import AdoWebhookAdapter
from ado_ai_pr_review.adapters.webhook_payload import AdoWebhookPayload
from ado_ai_pr_review.auth import build_ado_auth_strategy
from ado_ai_pr_review.engine import ReviewEngine
from ado_ai_pr_review.llm.factory import build_llm
from ado_ai_pr_review.log_context import bind_request_context

logger = logging.getLogger(__name__)

_background_tasks: set[asyncio.Task[None]] = set()


app = FastAPI(title="ADO AI PR Review Webhook")


def _sanitize_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Strip non-serializable values (e.g. exception objects) from Pydantic error ctx dicts."""
    sanitized = []
    for err in errors:
        clean = {k: v for k, v in err.items() if k != "ctx"}
        ctx = err.get("ctx")
        if ctx:
            clean["ctx"] = {ck: str(cv) for ck, cv in ctx.items()}
        sanitized.append(clean)
    return sanitized


@app.exception_handler(RequestValidationError)
async def _log_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    body = await request.body()
    errors = exc.errors()
    logger.error(
        "Webhook payload validation failed: %s | body=%.2000s",
        errors,
        body.decode("utf-8", errors="replace"),
    )
    return JSONResponse(status_code=422, content={"detail": _sanitize_errors(list(errors))})


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
    request_id = (
        request.headers.get("X-Request-ID")
        or request.headers.get("X-Correlation-ID")
        or f"ado-pr-{payload.pull_request_id}-{secrets.token_hex(8)}"
    )
    task = asyncio.create_task(asyncio.to_thread(_process_sync, payload, request_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return {"status": "accepted", "request_id": request_id}


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

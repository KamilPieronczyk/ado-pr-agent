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

_background_tasks: set[asyncio.Task[None]] = set()

app = FastAPI(title="ADO AI PR Review Webhook")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/webhook/ado")
async def handle_ado_webhook(payload: AdoWebhookPayload) -> dict[str, str]:
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

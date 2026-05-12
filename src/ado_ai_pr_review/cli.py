from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path
from typing import Annotated

import typer

from ado_ai_pr_review.adapters.local import LocalCliAdapter
from ado_ai_pr_review.engine import ReviewEngine
from ado_ai_pr_review.llm.factory import build_llm
from ado_ai_pr_review.logging_config import configure_logging
from ado_ai_pr_review.models import ReviewCommand

logger = logging.getLogger(__name__)

app = typer.Typer(no_args_is_help=True)


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
    request_id = f"local-{secrets.token_hex(8)}"
    adapter = LocalCliAdapter(repo_root=root, command=command, target_branch=target_branch, request_id=request_id)
    model = build_llm(llm)
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

    import ado_ai_pr_review.webhook_server as _ws
    uvicorn.run(_ws.app, host=host, port=port)



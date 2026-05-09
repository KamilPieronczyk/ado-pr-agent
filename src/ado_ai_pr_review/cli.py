from __future__ import annotations

import os
from typing import Annotated, Any, cast

import typer

from ado_ai_pr_review.ado_toolset import AdoToolset
from ado_ai_pr_review.bootstrap import Bootstrapper
from ado_ai_pr_review.cli_runner import CliRunner
from ado_ai_pr_review.commands import CommandRouter
from ado_ai_pr_review.config import ReviewConfig
from ado_ai_pr_review.context import ContextSelector
from ado_ai_pr_review.git_toolset import GitToolset
from ado_ai_pr_review.indexer import RepoIndexer
from ado_ai_pr_review.logging_config import configure_logging
from ado_ai_pr_review.model_client import ModelClient, ResponsesClient, build_openai_client
from ado_ai_pr_review.models import ReviewCommand
from ado_ai_pr_review.publisher import SuggestionPublisher
from ado_ai_pr_review.reviewer import ReviewOrchestrator
from ado_ai_pr_review.runtime import RuntimeContext
from ado_ai_pr_review.security import SecurityScanner
from ado_ai_pr_review.tool_policy import CommandPolicy

app = typer.Typer(no_args_is_help=True)


@app.command()
def run(
    repo_root: Annotated[str, typer.Option("--repo-root")] = ".",
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    verbose: Annotated[bool, typer.Option("--verbose")] = False,
) -> None:
    """Run the ADO AI PR review worker."""
    configure_logging(verbose=verbose)
    context = RuntimeContext.from_env(repo_root=repo_root)
    decision = run_worker(context=context, dry_run=dry_run)
    typer.echo(f"ado-ai-pr-review completed command={decision.value}")


def run_worker(context: RuntimeContext, dry_run: bool) -> ReviewCommand:
    runner = CliRunner(
        policy=CommandPolicy.default(),
        secrets=[context.system_access_token or ""],
    )
    ado = AdoToolset(runner=runner, context=context)
    git = GitToolset(runner=runner, repo_root=context.repo_root)
    publisher = SuggestionPublisher(ado_toolset=ado)

    created = Bootstrapper().create_missing_files(context.repo_root)
    if created:
        if not dry_run:
            publisher.publish_onboarding()
        return ReviewCommand.ONBOARDING

    config = ReviewConfig.load(context.repo_root)
    threads = cast(dict[str, Any], ado.list_pr_threads())
    decision = CommandRouter().route(threads)
    if decision.command is ReviewCommand.ONBOARDING:
        if not dry_run:
            publisher.publish_onboarding()
        return decision.command

    git.fetch()
    target_ref = context.target_branch.removeprefix("refs/heads/")
    refspec = f"origin/{target_ref}...HEAD"
    diff_text = git.diff(refspec, unified=0)

    scanner = SecurityScanner()
    local_findings, redacted_diff = scanner.scan_diff(diff_text)
    entries = RepoIndexer(exclude=config.context.index.exclude).build(context.repo_root)
    selector = ContextSelector(max_files=config.context.dynamic_context.max_files)
    prefer_tags = {"security"} if decision.command is ReviewCommand.SECURITY else set()
    selected = selector.select(
        repo_root=context.repo_root,
        guidance_paths=[
            config.instructions.security if decision.command is ReviewCommand.SECURITY else config.instructions.reviewer,
            *config.guidelines.code_style,
            *config.guidelines.security,
        ],
        entries=entries,
        prefer_tags=prefer_tags,
    )

    model_client = ModelClient(
        openai_client=cast(ResponsesClient, build_openai_client()),
        deployment=os.environ["AZURE_OPENAI_DEPLOYMENT"],
    )
    result = ReviewOrchestrator(model_client=model_client).run(
        command=decision.command,
        guidance=selected.always_on_guidance,
        selected_files=selected.dynamic_files,
        diff_text=redacted_diff,
        local_security_summary=f"Local findings: {len(local_findings)}",
    )
    result.findings.extend(local_findings)
    if not dry_run:
        publisher.publish_review(result)
    return decision.command

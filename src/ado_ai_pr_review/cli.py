from __future__ import annotations

import contextlib
import logging
import os
from typing import Annotated, Any, cast

import typer

from ado_ai_pr_review.ado_toolset import AdoToolset
from ado_ai_pr_review.bootstrap import Bootstrapper
from ado_ai_pr_review.cli_runner import CliRunner
from ado_ai_pr_review.commands import CommandRouter
from ado_ai_pr_review.config import ReviewConfig
from ado_ai_pr_review.context import ContextSelector
from ado_ai_pr_review.fixer import MechanicalFixer
from ado_ai_pr_review.git_toolset import GitToolset
from ado_ai_pr_review.indexer import RepoIndexer
from ado_ai_pr_review.logging_config import configure_logging
from ado_ai_pr_review.model_client import ModelClient, ResponsesClient, build_openai_client
from ado_ai_pr_review.models import FindingType, FixCandidate, FixDelivery, ReviewCommand
from ado_ai_pr_review.observability import ReviewMetrics
from ado_ai_pr_review.publisher import SuggestionPublisher
from ado_ai_pr_review.reviewer import ReviewOrchestrator
from ado_ai_pr_review.runtime import RuntimeContext
from ado_ai_pr_review.security import SecurityScanner
from ado_ai_pr_review.tool_policy import CommandPolicy

logger = logging.getLogger(__name__)

app = typer.Typer(no_args_is_help=True)


def _post_error_thread(ado: AdoToolset, exc: BaseException, dry_run: bool) -> None:
    """Post a best-effort error comment to the PR thread."""
    if dry_run:
        return
    with contextlib.suppress(Exception):
        ado.create_pr_thread(body={
            "comments": [{
                "parentCommentId": 0,
                "content": f"ADO AI review failed: {type(exc).__name__}. Check pipeline logs for details.",
                "commentType": "text",
            }],
            "status": "active",
            "properties": {"adoAiReview.kind": {"$type": "System.String", "$value": "error"}},
        })


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

    # I1: Wire MechanicalFixer for /ai fix command
    if decision.command is ReviewCommand.FIX:
        fix_pr_created = False
        try:
            result = ReviewOrchestrator(model_client=model_client).run(
                command=decision.command,
                guidance=selected.always_on_guidance,
                selected_files=selected.dynamic_files,
                diff_text=redacted_diff,
                local_security_summary=f"Local findings: {len(local_findings)}",
            )
            result.findings.extend(local_findings)

            fix_candidates = [
                FixCandidate(
                    delivery=FixDelivery.FIX_BRANCH_CANDIDATE,
                    title=f.title,
                    explanation=f.body,
                    file_path=f.file_path,
                    replacement=f.suggested_code,
                    commit_message=f"fix: {f.title.lower()}",
                )
                for f in result.findings
                if f.type is FindingType.MECHANICAL_FIX and f.suggested_code and f.file_path
            ]

            branch_name = config.fix.branch.name_template.format(
                pr_id=context.pull_request_id,
                run_id=context.build_id,
            )

            fixer = MechanicalFixer(
                git_toolset=git,
                ado_toolset=ado,
                repo_root=context.repo_root,
            )

            try:
                fixer.create_fix_branch(
                    candidates=fix_candidates,
                    branch_name=branch_name,
                    target_branch=target_ref,
                )
                fix_pr_created = True
            except RuntimeError as no_candidates_exc:
                logger.warning("fix branch not created: %s", no_candidates_exc)
                if not dry_run:
                    with contextlib.suppress(Exception):
                        ado.create_pr_thread(body={
                            "comments": [{
                                "parentCommentId": 0,
                                "content": f"ADO AI fix: no mechanical candidates produced commits. {no_candidates_exc}",
                                "commentType": "text",
                            }],
                            "status": "active",
                            "properties": {"adoAiReview.kind": {"$type": "System.String", "$value": "fix-skipped"}},
                        })

        except Exception as exc:
            logger.error("review failed: %s", exc)
            _post_error_thread(ado, exc, dry_run)
            return decision.command

        # I2: Emit ReviewMetrics for fix path
        metrics = ReviewMetrics(
            command=decision.command.value,
            pr_id=context.pull_request_id,
            findings_count=len(result.findings),
            inline_suggestions_count=sum(1 for f in result.findings if f.suggested_code),
            fix_pr_created=fix_pr_created,
        )
        logger.info("review metrics: %s", metrics.to_payload())
        return decision.command

    # Standard review/security path — I9: error handling around model call and publishing
    try:
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
    except Exception as exc:
        logger.error("review failed: %s", exc)
        _post_error_thread(ado, exc, dry_run)
        return decision.command

    # I2: Emit ReviewMetrics for review/security path
    metrics = ReviewMetrics(
        command=decision.command.value,
        pr_id=context.pull_request_id,
        findings_count=len(result.findings),
        inline_suggestions_count=sum(1 for f in result.findings if f.suggested_code),
        fix_pr_created=False,
    )
    logger.info("review metrics: %s", metrics.to_payload())
    return decision.command

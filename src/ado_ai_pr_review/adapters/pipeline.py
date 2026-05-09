# src/ado_ai_pr_review/adapters/pipeline.py
from __future__ import annotations

import contextlib
import logging
from pathlib import Path
from typing import Any, cast

from ado_ai_pr_review.ado_toolset import AdoToolset
from ado_ai_pr_review.cli_runner import CliRunner
from ado_ai_pr_review.commands import CommandRouter
from ado_ai_pr_review.fixer import MechanicalFixer
from ado_ai_pr_review.git_toolset import GitToolset
from ado_ai_pr_review.models import FixCandidate, ReviewCommand, ReviewResult
from ado_ai_pr_review.ports import PRContext, ReviewRequest
from ado_ai_pr_review.publisher import SuggestionPublisher
from ado_ai_pr_review.runtime import RuntimeContext
from ado_ai_pr_review.security import SecurityScanner
from ado_ai_pr_review.tool_policy import CommandPolicy

logger = logging.getLogger(__name__)


class AdoPipelineAdapter:
    def __init__(self, repo_root: Path, dry_run: bool = False) -> None:
        self._dry_run = dry_run
        self._context = RuntimeContext.from_env(repo_root=str(repo_root))
        self._runner = CliRunner(
            policy=CommandPolicy.default(),
            secrets=[self._context.system_access_token or ""],
        )
        self._ado = AdoToolset(runner=self._runner, context=self._context)
        self._git = GitToolset(runner=self._runner, repo_root=repo_root)
        self._publisher = SuggestionPublisher(ado_toolset=self._ado)

    def load_request(self) -> ReviewRequest:
        threads = cast(dict[str, Any], self._ado.list_pr_threads())
        decision = CommandRouter().route(threads)
        pr_context = self._make_pr_context()

        if decision.command is ReviewCommand.ONBOARDING:
            return ReviewRequest(
                repo_root=self._context.repo_root,
                diff_text="",
                local_findings=(),
                command=ReviewCommand.ONBOARDING,
                pr_context=pr_context,
            )

        self._git.fetch()
        target_ref = self._context.target_branch.removeprefix("refs/heads/")
        refspec = f"origin/{target_ref}...HEAD"
        diff_text = self._git.diff(refspec, unified=0)
        local_findings, redacted_diff = SecurityScanner().scan_diff(diff_text)

        return ReviewRequest(
            repo_root=self._context.repo_root,
            diff_text=redacted_diff,
            local_findings=tuple(local_findings),
            command=decision.command,
            pr_context=pr_context,
        )

    def publish_onboarding(self) -> None:
        if self._dry_run:
            return
        self._publisher.publish_onboarding()

    def publish_review(self, result: ReviewResult) -> None:
        if self._dry_run:
            return
        self._publisher.publish_review(result)

    def publish_error(self, exc: BaseException) -> None:
        if self._dry_run:
            return
        logger.error("review failed: %s", exc, exc_info=True)
        with contextlib.suppress(Exception):
            self._ado.create_pr_thread(body={
                "comments": [{
                    "parentCommentId": 0,
                    "content": f"ADO AI review failed: {type(exc).__name__}. Check pipeline logs for details.",
                    "commentType": "text",
                }],
                "status": "active",
                "properties": {"adoAiReview.kind": {"$type": "System.String", "$value": "error"}},
            })

    def create_fix_branch(
        self,
        candidates: list[FixCandidate],
        branch_name: str,
        target_branch: str,
    ) -> bool:
        fixer = MechanicalFixer(
            git_toolset=self._git,
            ado_toolset=self._ado,
            repo_root=self._context.repo_root,
        )
        try:
            fixer.create_fix_branch(candidates, branch_name, target_branch)
            return True
        except RuntimeError as exc:
            logger.warning("fix branch not created: %s", exc)
            return False

    def _make_pr_context(self) -> PRContext:
        return PRContext(
            pr_id=self._context.pull_request_id,
            source_branch=self._context.source_branch,
            target_branch=self._context.target_branch,
            is_fork=self._context.is_fork,
            build_id=self._context.build_id,
        )

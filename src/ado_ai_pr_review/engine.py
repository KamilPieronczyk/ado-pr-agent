from __future__ import annotations

import logging
from pathlib import Path

from ado_ai_pr_review.bootstrap import Bootstrapper
from ado_ai_pr_review.config import ReviewConfig
from ado_ai_pr_review.context import ContextSelector
from ado_ai_pr_review.indexer import RepoIndexer
from ado_ai_pr_review.models import FindingType, FixCandidate, FixDelivery, ReviewCommand
from ado_ai_pr_review.observability import ReviewMetrics
from ado_ai_pr_review.ports import LLMPort, PlatformAdapter
from ado_ai_pr_review.reviewer import ReviewOrchestrator

logger = logging.getLogger(__name__)


class ReviewEngine:
    def __init__(
        self,
        platform: PlatformAdapter,
        model: LLMPort,
        repo_root: Path,
    ) -> None:
        self._platform = platform
        self._model = model
        self._repo_root = repo_root

    def run(self) -> ReviewCommand:
        created = Bootstrapper().create_missing_files(self._repo_root)
        if created:
            self._platform.publish_onboarding()
            return ReviewCommand.ONBOARDING

        config = ReviewConfig.load(self._repo_root)

        try:
            request = self._platform.load_request()
        except Exception as exc:
            logger.error("failed to load review request: %s", exc)
            self._platform.publish_error(exc)
            raise

        if request.command is ReviewCommand.ONBOARDING:
            self._platform.publish_onboarding()
            return ReviewCommand.ONBOARDING

        entries = RepoIndexer(exclude=config.context.index.exclude).build(request.repo_root)
        selector = ContextSelector(max_files=config.context.dynamic_context.max_files)
        prefer_tags = {"security"} if request.command is ReviewCommand.SECURITY else set()
        selected = selector.select(
            repo_root=request.repo_root,
            guidance_paths=[
                config.instructions.security if request.command is ReviewCommand.SECURITY else config.instructions.reviewer,
                *config.guidelines.code_style,
                *config.guidelines.security,
            ],
            entries=entries,
            prefer_tags=prefer_tags,
        )
        local_security_summary = f"Local findings: {len(request.local_findings)}"

        if request.command is ReviewCommand.FIX:
            return self._run_fix(request, config, selected, local_security_summary)

        try:
            result = ReviewOrchestrator(self._model).run(
                command=request.command,
                guidance=selected.always_on_guidance,
                selected_files=selected.dynamic_files,
                diff_text=request.diff_text,
                local_security_summary=local_security_summary,
            )
        except Exception as exc:
            logger.error("review failed: %s", exc)
            self._platform.publish_error(exc)
            raise

        result.findings.extend(request.local_findings)
        self._platform.publish_review(result)

        metrics = ReviewMetrics(
            command=request.command.value,
            pr_id=request.pr_context.pr_id or 0,
            findings_count=len(result.findings),
            inline_suggestions_count=sum(1 for f in result.findings if f.suggested_code),
            fix_pr_created=False,
        )
        logger.info("review metrics: %s", metrics.to_payload())
        return request.command

    def _run_fix(self, request, config, selected, local_security_summary) -> ReviewCommand:  # type: ignore[no-untyped-def]
        try:
            result = ReviewOrchestrator(self._model).run(
                command=request.command,
                guidance=selected.always_on_guidance,
                selected_files=selected.dynamic_files,
                diff_text=request.diff_text,
                local_security_summary=local_security_summary,
            )
            result.findings.extend(request.local_findings)

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
                pr_id=request.pr_context.pr_id or "local",
                run_id=request.pr_context.build_id,
            )
            target_branch = request.pr_context.target_branch.removeprefix("refs/heads/")

            fix_pr_created = self._platform.create_fix_branch(
                candidates=fix_candidates,
                branch_name=branch_name,
                target_branch=target_branch,
            )

            metrics = ReviewMetrics(
                command=request.command.value,
                pr_id=request.pr_context.pr_id or 0,
                findings_count=len(result.findings),
                inline_suggestions_count=sum(1 for f in result.findings if f.suggested_code),
                fix_pr_created=fix_pr_created,
            )
            logger.info("review metrics: %s", metrics.to_payload())
            return ReviewCommand(request.command)

        except Exception as exc:
            logger.error("fix failed: %s", exc)
            self._platform.publish_error(exc)
            raise

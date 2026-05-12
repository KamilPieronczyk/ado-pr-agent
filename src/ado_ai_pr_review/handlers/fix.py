from __future__ import annotations

import logging

from ado_ai_pr_review.config import ReviewConfig
from ado_ai_pr_review.handlers.base import select_context
from ado_ai_pr_review.models import FindingType, FixCandidate, FixDelivery, ReviewCommand, ReviewResult
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
            result = ReviewOrchestrator(model).run(
                command=ReviewCommand.FIX,
                guidance=selected.always_on_guidance,
                selected_files=selected.dynamic_files,
                diff_text=request.diff_text,
                local_security_summary=local_security_summary,
            )
        except Exception as exc:
            logger.error("fix failed: %s", exc)
            platform.publish_error(exc)
            raise

        merged_findings = [*result.findings, *request.local_findings]
        fix_candidates = [
            FixCandidate(
                delivery=FixDelivery.FIX_BRANCH_CANDIDATE,
                title=f.title,
                explanation=f.body,
                file_path=f.file_path,
                replacement=f.suggested_code,
                commit_message=f"fix: {f.title.lower()}",
            )
            for f in merged_findings
            if f.type is FindingType.MECHANICAL_FIX and f.suggested_code and f.file_path
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
            findings_count=len(merged_findings),
            inline_suggestions_count=sum(1 for f in merged_findings if f.suggested_code),
            fix_pr_created=fix_pr_created,
        )
        logger.info("review metrics", extra=metrics.to_payload())

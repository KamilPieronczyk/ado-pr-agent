from __future__ import annotations

import logging

from ado_ai_pr_review.config import ReviewConfig
from ado_ai_pr_review.handlers.base import select_context
from ado_ai_pr_review.models import ReviewCommand, ReviewResult
from ado_ai_pr_review.observability import ReviewMetrics
from ado_ai_pr_review.ports import LLMPort, PlatformAdapter, ReviewRequest
from ado_ai_pr_review.reviewer import ReviewOrchestrator

logger = logging.getLogger(__name__)


def _run(
    command: ReviewCommand,
    request: ReviewRequest,
    platform: PlatformAdapter,
    model: LLMPort,
    config: ReviewConfig,
) -> None:
    prefer_tags: frozenset[str] = frozenset({"security"}) if command is ReviewCommand.SECURITY else frozenset()
    primary_instruction = (
        config.instructions.security if command is ReviewCommand.SECURITY else config.instructions.reviewer
    )
    selected = select_context(request, config, primary_instruction, prefer_tags)
    local_security_summary = f"Local findings: {len(request.local_findings)}"

    try:
        result = ReviewOrchestrator(model).run(
            command=command,
            guidance=selected.always_on_guidance,
            selected_files=selected.dynamic_files,
            diff_text=request.diff_text,
            local_security_summary=local_security_summary,
        )
    except Exception as exc:
        logger.error("review failed: %s", exc)
        platform.publish_error(exc)
        raise

    merged = ReviewResult(
        summary=result.summary,
        findings=[*result.findings, *request.local_findings],
    )
    platform.publish_review(merged)

    metrics = ReviewMetrics(
        command=command.value,
        pr_id=request.pr_context.pr_id or 0,
        findings_count=len(merged.findings),
        inline_suggestions_count=sum(1 for f in merged.findings if f.suggested_code),
        fix_pr_created=False,
    )
    logger.info("review metrics", extra=metrics.to_payload())


class ReviewHandler:
    def handle(self, request: ReviewRequest, platform: PlatformAdapter, model: LLMPort, config: ReviewConfig) -> None:
        _run(ReviewCommand.REVIEW, request, platform, model, config)


class SecurityHandler:
    def handle(self, request: ReviewRequest, platform: PlatformAdapter, model: LLMPort, config: ReviewConfig) -> None:
        _run(ReviewCommand.SECURITY, request, platform, model, config)

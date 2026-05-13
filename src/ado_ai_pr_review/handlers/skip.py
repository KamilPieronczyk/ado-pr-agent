from __future__ import annotations

import logging

from ado_ai_pr_review.config import ReviewConfig
from ado_ai_pr_review.ports import LLMPort, PlatformAdapter, ReviewRequest

logger = logging.getLogger(__name__)


class SkipHandler:
    def handle(
        self,
        request: ReviewRequest,
        platform: PlatformAdapter,
        model: LLMPort,
        config: ReviewConfig | None,
    ) -> None:
        logger.debug("skipping event: unrecognised inline comment, no action taken")

from __future__ import annotations

import logging
from pathlib import Path

from ado_ai_pr_review.config import ReviewConfig
from ado_ai_pr_review.handlers import HANDLERS
from ado_ai_pr_review.log_context import bind_request_context
from ado_ai_pr_review.models import ReviewCommand
from ado_ai_pr_review.ports import LLMPort, PlatformAdapter


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
        config = ReviewConfig.load(self._repo_root)

        try:
            request = self._platform.load_request()
        except Exception as exc:
            logger.error("failed to load review request: %s", exc)
            self._platform.publish_error(exc)
            raise

        with bind_request_context(request.pr_context.request_id):
            handler = HANDLERS.get(request.command)
            if handler is None:
                raise ValueError(f"No handler registered for command {request.command!r}")
            handler.handle(request, self._platform, self._model, config)
            return request.command

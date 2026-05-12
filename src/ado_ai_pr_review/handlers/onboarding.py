from __future__ import annotations

from ado_ai_pr_review.config import ReviewConfig
from ado_ai_pr_review.ports import LLMPort, PlatformAdapter, ReviewRequest


class OnboardingHandler:
    def handle(
        self,
        request: ReviewRequest,
        platform: PlatformAdapter,
        model: LLMPort,
        config: ReviewConfig,
    ) -> None:
        platform.publish_onboarding()

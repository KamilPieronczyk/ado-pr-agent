from __future__ import annotations

from ado_ai_pr_review.handlers.base import CommandHandler
from ado_ai_pr_review.handlers.fix import FixHandler
from ado_ai_pr_review.handlers.onboarding import OnboardingHandler
from ado_ai_pr_review.handlers.review import ReviewHandler, SecurityHandler
from ado_ai_pr_review.handlers.skip import SkipHandler
from ado_ai_pr_review.models import ReviewCommand

HANDLERS: dict[ReviewCommand, CommandHandler] = {
    ReviewCommand.REVIEW: ReviewHandler(),
    ReviewCommand.SECURITY: SecurityHandler(),
    ReviewCommand.FIX: FixHandler(),
    ReviewCommand.ONBOARDING: OnboardingHandler(),
    ReviewCommand.SKIP: SkipHandler(),
}

__all__ = ["HANDLERS", "CommandHandler"]

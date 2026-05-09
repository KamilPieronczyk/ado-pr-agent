from ado_ai_pr_review.commands import CommandRouter
from ado_ai_pr_review.models import ReviewCommand


def test_command_router_selects_latest_actionable_command() -> None:
    threads = {
        "value": [
            {"id": 1, "publishedDate": "2026-05-08T09:00:00Z", "comments": [{"content": "/ai review"}]},
            {"id": 2, "publishedDate": "2026-05-08T10:00:00Z", "comments": [{"content": "please run /ai security"}]},
        ]
    }

    decision = CommandRouter().route(threads)

    assert decision.command is ReviewCommand.SECURITY
    assert decision.thread_id == 2


def test_command_router_returns_onboarding_when_no_command_exists() -> None:
    threads = {"value": [{"id": 1, "comments": [{"content": "Looks good"}]}]}

    decision = CommandRouter().route(threads)

    assert decision.command is ReviewCommand.ONBOARDING

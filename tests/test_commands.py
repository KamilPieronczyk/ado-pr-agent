import pytest

from ado_ai_pr_review.commands import CommandRouter, _BOT_MARKER
from ado_ai_pr_review.models import ReviewCommand


def test_command_router_selects_latest_actionable_command() -> None:
    threads = {
        "value": [
            {"id": 1, "publishedDate": "2026-05-08T09:00:00Z", "comments": [{"content": "/ai review"}]},
            {"id": 2, "publishedDate": "2026-05-08T10:00:00Z", "comments": [{"content": "/ai security"}]},
        ]
    }

    decision = CommandRouter().route(threads)

    assert decision.command is ReviewCommand.SECURITY
    assert decision.thread_id == 2


def test_command_router_returns_onboarding_when_no_command_exists() -> None:
    threads = {"value": [{"id": 1, "comments": [{"content": "Looks good"}]}]}

    decision = CommandRouter().route(threads)

    assert decision.command is ReviewCommand.ONBOARDING


@pytest.mark.parametrize(
    "content",
    [
        # Command buried in prose — must not trigger (prevents agent self-triggering).
        "ADO AI review is available. Comment `/ai review`, `/ai security`, or `/ai fix` to run it.",
        "please run /ai security",
        "I'd like /ai review",
        "maybe /ai fix would help",
    ],
)
def test_detect_command_ignores_embedded_commands(content: str) -> None:
    assert CommandRouter.detect_command(content) is None


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("/ai review", ReviewCommand.REVIEW),
        ("  /ai security  ", ReviewCommand.SECURITY),
        ("/ai fix", ReviewCommand.FIX),
        # Command on its own line within multiline text.
        ("LGTM overall\n/ai review", ReviewCommand.REVIEW),
        ("/ai security\nsome trailing text", ReviewCommand.SECURITY),
    ],
)
def test_detect_command_matches_line_prefixed_command(content: str, expected: ReviewCommand) -> None:
    assert CommandRouter.detect_command(content) is expected


def test_command_router_skips_threads_with_bot_marker() -> None:
    threads = {
        "value": [
            {
                "id": 1,
                "publishedDate": "2026-05-08T10:00:00Z",
                "comments": [{"content": f"/ai review\n\n{_BOT_MARKER}"}],
            },
        ]
    }

    decision = CommandRouter().route(threads)

    assert decision.command is ReviewCommand.ONBOARDING


def test_command_router_skips_threads_with_ado_property_and_bot_marker_independently() -> None:
    threads = {
        "value": [
            {
                "id": 1,
                "publishedDate": "2026-05-08T09:00:00Z",
                "properties": {"adoAiReview.kind": {"$type": "System.String", "$value": "summary"}},
                "comments": [{"content": "ADO AI review summary:\n\nAll good."}],
            },
            {
                "id": 2,
                "publishedDate": "2026-05-08T10:00:00Z",
                "comments": [{"content": f"Some bot comment\n\n{_BOT_MARKER}"}],
            },
            {
                "id": 3,
                "publishedDate": "2026-05-08T11:00:00Z",
                "comments": [{"content": "/ai fix"}],
            },
        ]
    }

    decision = CommandRouter().route(threads)

    assert decision.command is ReviewCommand.FIX
    assert decision.thread_id == 3

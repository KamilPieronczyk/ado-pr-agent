from __future__ import annotations

from pytest_mock import MockerFixture

from ado_ai_pr_review.models import (
    Finding,
    FindingSeverity,
    FindingType,
    FixPlanResult,
    InlineSuggestion,
    ReviewResult,
)
from ado_ai_pr_review.publisher import SuggestionPublisher, _BOT_MARKER


def test_publisher_creates_inline_suggestion_thread(mocker: MockerFixture) -> None:
    ado = mocker.Mock()
    publisher = SuggestionPublisher(ado_toolset=ado)
    result = ReviewResult(
        summary="One issue.",
        findings=[
            Finding(
                type=FindingType.BUG_RISK,
                severity=FindingSeverity.HIGH,
                title="Guard missing value",
                body="Handle None before formatting.",
                file_path="src/app.py",
                line_start=10,
                line_end=10,
                suggested_code="if value is None:\n    return None",
            )
        ],
    )

    publisher.publish_review(result)

    body = ado.create_pr_thread.call_args.kwargs["body"]
    assert body["threadContext"]["filePath"] == "src/app.py"
    comment = body["comments"][0]
    assert "if value is None" in comment["content"]
    assert comment["commentType"] == "codeChange"
    assert _BOT_MARKER in comment["content"]


def test_publisher_uses_text_comment_type_without_suggestion(mocker: MockerFixture) -> None:
    ado = mocker.Mock()
    publisher = SuggestionPublisher(ado_toolset=ado)
    result = ReviewResult(
        summary="One issue.",
        findings=[
            Finding(
                type=FindingType.BUG_RISK,
                severity=FindingSeverity.HIGH,
                title="Guard missing value",
                body="Handle None before formatting.",
                file_path="src/app.py",
                line_start=10,
            )
        ],
    )

    publisher.publish_review(result)

    body = ado.create_pr_thread.call_args.kwargs["body"]
    assert body["comments"][0]["commentType"] == "text"


def test_publisher_summary_contains_bot_marker(mocker: MockerFixture) -> None:
    ado = mocker.Mock()
    publisher = SuggestionPublisher(ado_toolset=ado)

    publisher.publish_review(ReviewResult(summary="All good.", findings=[]))

    calls = ado.create_pr_thread.call_args_list
    summary_body = calls[0].kwargs["body"]
    assert _BOT_MARKER in summary_body["comments"][0]["content"]


def test_publisher_onboarding_contains_bot_marker(mocker: MockerFixture) -> None:
    ado = mocker.Mock()
    publisher = SuggestionPublisher(ado_toolset=ado)

    publisher.publish_onboarding()

    body = ado.create_pr_thread.call_args.kwargs["body"]
    assert _BOT_MARKER in body["comments"][0]["content"]


def test_publisher_publish_fix_result_posts_summary_and_inline_suggestion(mocker: MockerFixture) -> None:
    ado = mocker.Mock()
    publisher = SuggestionPublisher(ado_toolset=ado)
    result = FixPlanResult(
        summary="Two fixes.",
        inline_suggestions=[
            InlineSuggestion(
                file_path="src/store.ts",
                line_start=10,
                line_end=12,
                severity=FindingSeverity.HIGH,
                title="Fix id",
                body="Use max with 0.",
                replacement_lines="  const id = Math.max(0, ...ids) + 1;",
            )
        ],
    )

    publisher.publish_fix_result(result)

    assert ado.create_pr_thread.call_count == 2
    summary_body = ado.create_pr_thread.call_args_list[0].kwargs["body"]
    assert "Two fixes." in summary_body["comments"][0]["content"]
    assert summary_body["comments"][0]["commentType"] == "text"
    assert _BOT_MARKER in summary_body["comments"][0]["content"]
    suggestion_body = ado.create_pr_thread.call_args_list[1].kwargs["body"]
    assert suggestion_body["threadContext"]["filePath"] == "src/store.ts"
    assert suggestion_body["threadContext"]["rightFileStart"]["line"] == 10
    assert suggestion_body["threadContext"]["rightFileEnd"]["line"] == 12
    assert suggestion_body["comments"][0]["commentType"] == "codeChange"
    assert "Fix id" in suggestion_body["comments"][0]["content"]
    assert "const id = Math.max" in suggestion_body["comments"][0]["content"]
    assert _BOT_MARKER in suggestion_body["comments"][0]["content"]


def test_publisher_publish_fix_result_no_inline_calls_when_empty(mocker: MockerFixture) -> None:
    ado = mocker.Mock()
    publisher = SuggestionPublisher(ado_toolset=ado)

    publisher.publish_fix_result(FixPlanResult(summary="No suggestions."))

    assert ado.create_pr_thread.call_count == 1  # summary only
    body = ado.create_pr_thread.call_args.kwargs["body"]
    assert body["properties"]["adoAiReview.kind"]["$value"] == "fix-summary"

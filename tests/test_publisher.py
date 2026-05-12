from __future__ import annotations

from unittest.mock import Mock

from pytest_mock import MockerFixture

from ado_ai_pr_review.models import Finding, FindingSeverity, FindingType, ReviewResult
from ado_ai_pr_review.publisher import SuggestionPublisher


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
    assert "```suggestion" in body["comments"][0]["content"]

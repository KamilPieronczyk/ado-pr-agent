import pytest
from pydantic import ValidationError

from ado_ai_pr_review.models import Finding, FindingSeverity, FindingType, ReviewResult


def test_review_result_validates_finding_payload() -> None:
    result = ReviewResult.model_validate(
        {
            "summary": "Two issues found.",
            "findings": [
                {
                    "type": "bug_risk",
                    "severity": "high",
                    "title": "Null value can reach formatter",
                    "body": "Guard the value before formatting.",
                    "file_path": "src/app.py",
                    "line_start": 12,
                    "line_end": 12,
                    "suggested_code": "if value is None:\n    return None",
                }
            ],
        }
    )

    assert isinstance(result.findings[0], Finding)
    assert result.findings[0].severity is FindingSeverity.HIGH
    assert result.findings[0].type is FindingType.BUG_RISK


def test_finding_rejects_line_end_without_line_start() -> None:
    with pytest.raises(ValidationError, match="line_start"):
        Finding.model_validate(
            {
                "type": "bug_risk",
                "severity": "high",
                "title": "Invalid range",
                "body": "Line end without start is ambiguous.",
                "line_end": 12,
            }
        )


def test_finding_rejects_descending_line_range() -> None:
    with pytest.raises(ValidationError, match="line_end"):
        Finding.model_validate(
            {
                "type": "bug_risk",
                "severity": "high",
                "title": "Invalid range",
                "body": "Line end must not precede line start.",
                "line_start": 20,
                "line_end": 12,
            }
        )


def test_review_result_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ReviewResult.model_validate({"summary": "No issues.", "unexpected": True})


from pytest_mock import MockerFixture

from ado_ai_pr_review.model_client import ModelClient


def test_model_client_parses_response_json(mocker: MockerFixture) -> None:
    openai_client = mocker.Mock()
    openai_client.responses.create.return_value.output_text = """
{"summary":"ok","findings":[]}
"""
    client = ModelClient(openai_client=openai_client, deployment="review-model")

    result = client.review_json(system_prompt="system", user_prompt="user")

    assert result.summary == "ok"
    openai_client.responses.create.assert_called_once()

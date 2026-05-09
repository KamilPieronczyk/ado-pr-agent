from pytest_mock import MockerFixture

from ado_ai_pr_review.models import ReviewCommand, ReviewResult
from ado_ai_pr_review.observability import ReviewMetrics
from ado_ai_pr_review.reviewer import ReviewOrchestrator


def test_orchestrator_uses_security_prompt_for_security_command(mocker: MockerFixture) -> None:
    model_client = mocker.Mock()
    model_client.review_json.return_value = ReviewResult(summary="ok", findings=[])
    orchestrator = ReviewOrchestrator(model_client=model_client)

    result = orchestrator.run(
        command=ReviewCommand.SECURITY,
        guidance=["secure guidance"],
        selected_files=["src/auth.py\ncode"],
        diff_text="+ change",
        local_security_summary="No local secrets detected.",
    )

    assert result.summary == "ok"
    system_prompt = model_client.review_json.call_args.kwargs["system_prompt"]
    assert "security reviewer" in system_prompt.lower()


def test_review_metrics_serializes_without_code_context() -> None:
    metrics = ReviewMetrics(
        command="review",
        pr_id=42,
        findings_count=3,
        inline_suggestions_count=1,
        fix_pr_created=False,
        token_usage={"input": 100, "output": 20},
    )

    payload = metrics.to_payload()

    assert payload["command"] == "review"
    assert "code_context" not in payload

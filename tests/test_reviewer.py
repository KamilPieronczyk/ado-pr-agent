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


def test_orchestrator_fix_plan_calls_fix_plan_json(mocker: MockerFixture) -> None:
    from ado_ai_pr_review.models import FixPlanResult

    model_client = mocker.Mock()
    model_client.fix_plan_json.return_value = FixPlanResult(summary="one fix")
    orchestrator = ReviewOrchestrator(model_client=model_client)

    result = orchestrator.fix_plan(
        guidance=["No secrets."],
        selected_files=["src/store.ts\ncode"],
        diff_text="+ const x = 1;",
        local_security_summary="Local findings: 0",
    )

    assert result.summary == "one fix"
    call_kwargs = model_client.fix_plan_json.call_args.kwargs
    assert "+ const x = 1;" in call_kwargs["user_prompt"]
    assert "No secrets." in call_kwargs["user_prompt"]
    assert "inline_suggestions" in call_kwargs["system_prompt"]
    assert "fix_branch_changes" in call_kwargs["system_prompt"]

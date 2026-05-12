from pathlib import Path

from ado_ai_pr_review.ado_context import AdoContext


def test_ado_context_has_no_pipeline_token_field(tmp_path: Path) -> None:
    context = AdoContext(
        repo_root=tmp_path,
        organization_url="https://dev.azure.com/acme/",
        project="Payments",
        repository_id="repo-guid",
        repository_name="payments-api",
        pull_request_id=42,
        source_branch="refs/heads/feature/auth",
        target_branch="refs/heads/main",
        is_fork=False,
        run_id="webhook",
    )

    assert context.run_id == "webhook"
    assert not hasattr(context, "system_access_token")

import pytest
from typer.testing import CliRunner

from ado_ai_pr_review.cli import app
from ado_ai_pr_review.errors import ConfigurationError
from ado_ai_pr_review.runtime import RuntimeContext


def test_cli_help_renders() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "run" in result.output


def test_cli_run_dry_run_executes_worker() -> None:
    result = CliRunner().invoke(app, ["run", "--dry-run"])

    assert result.exit_code == 0
    assert "dry_run=True" in result.output


def test_cli_no_args_renders_help_without_running_worker() -> None:
    result = CliRunner().invoke(app, [])

    assert result.exit_code == 0
    assert "run" in result.output
    assert "dry_run=" not in result.output


def test_runtime_context_reads_pipeline_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SYSTEM_TEAMFOUNDATIONCOLLECTIONURI", "https://dev.azure.com/acme/")
    monkeypatch.setenv("SYSTEM_TEAMPROJECT", "Payments")
    monkeypatch.setenv("BUILD_REPOSITORY_ID", "repo-123")
    monkeypatch.setenv("BUILD_REPOSITORY_NAME", "checkout-repo")
    monkeypatch.setenv("SYSTEM_PULLREQUEST_PULLREQUESTID", "42")
    monkeypatch.setenv("SYSTEM_PULLREQUEST_SOURCEBRANCH", "refs/heads/users/alice/change")
    monkeypatch.setenv("SYSTEM_PULLREQUEST_TARGETBRANCH", "refs/heads/main")
    monkeypatch.setenv("SYSTEM_PULLREQUEST_ISFORK", "False")
    monkeypatch.setenv("BUILD_BUILDID", "9001")
    monkeypatch.setenv("SYSTEM_ACCESSTOKEN", "token-value")

    context = RuntimeContext.from_env(repo_root=".")

    assert context.organization_url == "https://dev.azure.com/acme/"
    assert context.project == "Payments"
    assert context.repository_id == "repo-123"
    assert context.pull_request_id == 42
    assert context.is_fork is False
    assert context.system_access_token == "token-value"


def test_runtime_context_requires_pr_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SYSTEM_PULLREQUEST_PULLREQUESTID", raising=False)

    with pytest.raises(ConfigurationError, match="SYSTEM_PULLREQUEST_PULLREQUESTID"):
        RuntimeContext.from_env(repo_root=".")


def test_runtime_context_accepts_true_is_fork_with_whitespace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SYSTEM_TEAMFOUNDATIONCOLLECTIONURI", "https://dev.azure.com/acme/")
    monkeypatch.setenv("SYSTEM_TEAMPROJECT", "Payments")
    monkeypatch.setenv("BUILD_REPOSITORY_ID", "repo-123")
    monkeypatch.setenv("SYSTEM_PULLREQUEST_PULLREQUESTID", "42")
    monkeypatch.setenv("SYSTEM_PULLREQUEST_ISFORK", "true ")

    context = RuntimeContext.from_env(repo_root=".")

    assert context.is_fork is True


def test_runtime_context_accepts_zero_is_fork_as_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SYSTEM_TEAMFOUNDATIONCOLLECTIONURI", "https://dev.azure.com/acme/")
    monkeypatch.setenv("SYSTEM_TEAMPROJECT", "Payments")
    monkeypatch.setenv("BUILD_REPOSITORY_ID", "repo-123")
    monkeypatch.setenv("SYSTEM_PULLREQUEST_PULLREQUESTID", "42")
    monkeypatch.setenv("SYSTEM_PULLREQUEST_ISFORK", "0")

    context = RuntimeContext.from_env(repo_root=".")

    assert context.is_fork is False


def test_runtime_context_rejects_unknown_is_fork_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SYSTEM_TEAMFOUNDATIONCOLLECTIONURI", "https://dev.azure.com/acme/")
    monkeypatch.setenv("SYSTEM_TEAMPROJECT", "Payments")
    monkeypatch.setenv("BUILD_REPOSITORY_ID", "repo-123")
    monkeypatch.setenv("SYSTEM_PULLREQUEST_PULLREQUESTID", "42")
    monkeypatch.setenv("SYSTEM_PULLREQUEST_ISFORK", "maybe")

    with pytest.raises(ConfigurationError, match="SYSTEM_PULLREQUEST_ISFORK"):
        RuntimeContext.from_env(repo_root=".")


def test_runtime_context_rejects_whitespace_required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SYSTEM_TEAMFOUNDATIONCOLLECTIONURI", "https://dev.azure.com/acme/")
    monkeypatch.setenv("SYSTEM_TEAMPROJECT", "   ")
    monkeypatch.setenv("BUILD_REPOSITORY_ID", "repo-123")
    monkeypatch.setenv("SYSTEM_PULLREQUEST_PULLREQUESTID", "42")

    with pytest.raises(ConfigurationError, match="SYSTEM_TEAMPROJECT"):
        RuntimeContext.from_env(repo_root=".")

# tests/test_cli.py
from __future__ import annotations

import os
from pathlib import Path

import pytest
from pytest_mock import MockerFixture
from typer.testing import CliRunner

from ado_ai_pr_review.cli import app
from ado_ai_pr_review.errors import ConfigurationError
from ado_ai_pr_review.models import ReviewCommand
from ado_ai_pr_review.runtime import RuntimeContext

# ── pipeline subcommand ────────────────────────────────────────────────────────

def test_pipeline_help_renders() -> None:
    result = CliRunner().invoke(app, ["pipeline", "--help"])
    assert result.exit_code == 0
    assert "repo-root" in result.output


def test_pipeline_runs_engine(mocker: MockerFixture, tmp_path: Path) -> None:
    mocker.patch.dict(os.environ, {
        "SYSTEM_TEAMFOUNDATIONCOLLECTIONURI": "https://dev.azure.com/acme/",
        "SYSTEM_TEAMPROJECT": "P",
        "BUILD_REPOSITORY_ID": "r",
        "SYSTEM_PULLREQUEST_PULLREQUESTID": "1",
        "AZURE_OPENAI_BASE_URL": "https://example.com/",
        "AZURE_OPENAI_DEPLOYMENT": "model",
    })
    mocker.patch("ado_ai_pr_review.cli.AdoPipelineAdapter")
    mocker.patch("ado_ai_pr_review.cli.build_openai_client")
    engine_mock = mocker.patch("ado_ai_pr_review.cli.ReviewEngine")
    engine_mock.return_value.run.return_value = ReviewCommand.ONBOARDING

    result = CliRunner().invoke(app, ["pipeline", "--repo-root", str(tmp_path), "--dry-run"])

    assert result.exit_code == 0
    assert "completed" in result.output
    engine_mock.return_value.run.assert_called_once()


def test_pipeline_exits_1_on_engine_error(mocker: MockerFixture, tmp_path: Path) -> None:
    mocker.patch.dict(os.environ, {
        "SYSTEM_TEAMFOUNDATIONCOLLECTIONURI": "https://dev.azure.com/acme/",
        "SYSTEM_TEAMPROJECT": "P",
        "BUILD_REPOSITORY_ID": "r",
        "SYSTEM_PULLREQUEST_PULLREQUESTID": "1",
        "AZURE_OPENAI_BASE_URL": "https://example.com/",
        "AZURE_OPENAI_DEPLOYMENT": "model",
    })
    mocker.patch("ado_ai_pr_review.cli.AdoPipelineAdapter")
    mocker.patch("ado_ai_pr_review.cli.build_openai_client")
    engine_mock = mocker.patch("ado_ai_pr_review.cli.ReviewEngine")
    engine_mock.return_value.run.side_effect = RuntimeError("model unavailable")

    result = CliRunner().invoke(app, ["pipeline", "--repo-root", str(tmp_path)])

    assert result.exit_code == 1


# ── local subcommand ───────────────────────────────────────────────────────────

def test_local_help_renders() -> None:
    result = CliRunner().invoke(app, ["local", "--help"])
    assert result.exit_code == 0
    assert "command" in result.output


def test_local_runs_engine(mocker: MockerFixture, tmp_path: Path) -> None:
    mocker.patch.dict(os.environ, {
        "AZURE_OPENAI_BASE_URL": "https://example.com/",
        "AZURE_OPENAI_DEPLOYMENT": "model",
    })
    mocker.patch("ado_ai_pr_review.cli.LocalCliAdapter")
    mocker.patch("ado_ai_pr_review.cli.build_openai_client")
    engine_mock = mocker.patch("ado_ai_pr_review.cli.ReviewEngine")
    engine_mock.return_value.run.return_value = ReviewCommand.REVIEW

    result = CliRunner().invoke(app, ["local", "--command", "review", "--repo-root", str(tmp_path)])

    assert result.exit_code == 0


# ── RuntimeContext (unchanged, still in test_cli.py) ─────────────────────────

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
    assert context.pull_request_id == 42
    assert context.is_fork is False
    assert context.system_access_token == "token-value"


def test_runtime_context_requires_pr_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SYSTEM_PULLREQUEST_PULLREQUESTID", raising=False)
    with pytest.raises(ConfigurationError, match="SYSTEM_PULLREQUEST_PULLREQUESTID"):
        RuntimeContext.from_env(repo_root=".")


def test_runtime_context_accepts_true_is_fork_with_whitespace(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SYSTEM_TEAMFOUNDATIONCOLLECTIONURI", "https://dev.azure.com/acme/")
    monkeypatch.setenv("SYSTEM_TEAMPROJECT", "Payments")
    monkeypatch.setenv("BUILD_REPOSITORY_ID", "repo-123")
    monkeypatch.setenv("SYSTEM_PULLREQUEST_PULLREQUESTID", "42")
    monkeypatch.setenv("SYSTEM_PULLREQUEST_ISFORK", "true ")

    context = RuntimeContext.from_env(repo_root=".")

    assert context.is_fork is True


def test_runtime_context_rejects_unknown_is_fork_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SYSTEM_TEAMFOUNDATIONCOLLECTIONURI", "https://dev.azure.com/acme/")
    monkeypatch.setenv("SYSTEM_TEAMPROJECT", "Payments")
    monkeypatch.setenv("BUILD_REPOSITORY_ID", "repo-123")
    monkeypatch.setenv("SYSTEM_PULLREQUEST_PULLREQUESTID", "42")
    monkeypatch.setenv("SYSTEM_PULLREQUEST_ISFORK", "maybe")

    with pytest.raises(ConfigurationError, match="SYSTEM_PULLREQUEST_ISFORK"):
        RuntimeContext.from_env(repo_root=".")

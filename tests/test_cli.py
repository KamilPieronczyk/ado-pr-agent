# tests/test_cli.py
from __future__ import annotations

import os
from pathlib import Path

from pytest_mock import MockerFixture
from typer.testing import CliRunner

from ado_ai_pr_review.cli import app
from ado_ai_pr_review.models import ReviewCommand

# ── removed commands ──────────────────────────────────────────────────────────

def test_pipeline_command_is_not_registered() -> None:
    result = CliRunner().invoke(app, ["pipeline", "--help"])

    assert result.exit_code != 0


# ── local subcommand ──────────────────────────────────────────────────────────

def test_local_help_renders() -> None:
    result = CliRunner().invoke(app, ["local", "--help"])

    assert result.exit_code == 0
    assert "command" in result.output


def test_serve_help_still_renders() -> None:
    result = CliRunner().invoke(app, ["serve", "--help"])

    assert result.exit_code == 0
    assert "host" in result.output


def test_local_runs_engine(mocker: MockerFixture, tmp_path: Path) -> None:
    mocker.patch.dict(os.environ, {
        "AZURE_OPENAI_BASE_URL": "https://example.com/",
        "AZURE_OPENAI_DEPLOYMENT": "model",
    })
    mocker.patch("ado_ai_pr_review.cli.LocalCliAdapter")
    mocker.patch("ado_ai_pr_review.llm.factory.build_openai_client")
    engine_mock = mocker.patch("ado_ai_pr_review.cli.ReviewEngine")
    engine_mock.return_value.run.return_value = ReviewCommand.REVIEW

    result = CliRunner().invoke(app, ["local", "--command", "review", "--repo-root", str(tmp_path)])

    assert result.exit_code == 0

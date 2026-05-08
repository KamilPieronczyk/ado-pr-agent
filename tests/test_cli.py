from typer.testing import CliRunner

from ado_ai_pr_review.cli import app


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

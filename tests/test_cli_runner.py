import subprocess
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from ado_ai_pr_review.cli_runner import CliRunner
from ado_ai_pr_review.errors import CommandExecutionError, CommandRejectedError
from ado_ai_pr_review.tool_policy import CommandPolicy


def test_cli_runner_redacts_secret_output(mocker: MockerFixture, tmp_path: Path) -> None:
    completed = subprocess.CompletedProcess(
        args=["git", "status", "--short"],
        returncode=0,
        stdout="token=abc123\n",
        stderr="",
    )
    mocker.patch("subprocess.run", return_value=completed)
    runner = CliRunner(policy=CommandPolicy.default(), secrets=["abc123"])

    result = runner.run(["git", "status", "--short"], cwd=tmp_path)

    assert result.stdout == "token=[REDACTED]\n"
    assert result.returncode == 0


def test_cli_runner_rejected_command_does_not_run_subprocess(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    run = mocker.patch("subprocess.run")
    runner = CliRunner(policy=CommandPolicy.default())

    with pytest.raises(CommandRejectedError):
        runner.run(["bash", "-lc", "echo unsafe"], cwd=tmp_path)

    run.assert_not_called()


def test_cli_runner_redacts_secret_stderr(mocker: MockerFixture, tmp_path: Path) -> None:
    completed = subprocess.CompletedProcess(
        args=["git", "status"],
        returncode=0,
        stdout="",
        stderr="warning abc123\n",
    )
    mocker.patch("subprocess.run", return_value=completed)
    runner = CliRunner(policy=CommandPolicy.default(), secrets=["abc123"])

    result = runner.run(["git", "status"], cwd=tmp_path)

    assert result.stderr == "warning [REDACTED]\n"


def test_cli_runner_nonzero_raises_with_redacted_output(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    completed = subprocess.CompletedProcess(
        args=["git", "status"],
        returncode=2,
        stdout="",
        stderr="failed with token abc123\n",
    )
    mocker.patch("subprocess.run", return_value=completed)
    runner = CliRunner(policy=CommandPolicy.default(), secrets=["abc123"])

    with pytest.raises(CommandExecutionError) as exc_info:
        runner.run(["git", "status"], cwd=tmp_path)

    message = str(exc_info.value)
    assert "git status" in message
    assert "exit code 2" in message
    assert "failed with token [REDACTED]" in message
    assert "abc123" not in message


def test_cli_runner_wraps_timeout_with_redacted_output(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    mocker.patch(
        "subprocess.run",
        side_effect=subprocess.TimeoutExpired(
            cmd=["git", "status"],
            timeout=1,
            output="stdout abc123",
            stderr="stderr abc123",
        ),
    )
    runner = CliRunner(
        policy=CommandPolicy.default(),
        secrets=["abc123"],
        timeout_seconds=1,
    )

    with pytest.raises(CommandExecutionError) as exc_info:
        runner.run(["git", "status"], cwd=tmp_path)

    message = str(exc_info.value)
    assert "git status" in message
    assert "timed out after 1 seconds" in message
    assert "[REDACTED]" in message
    assert "abc123" not in message


def test_cli_runner_wraps_os_error(mocker: MockerFixture, tmp_path: Path) -> None:
    mocker.patch("subprocess.run", side_effect=OSError("exec failed abc123"))
    runner = CliRunner(policy=CommandPolicy.default(), secrets=["abc123"])

    with pytest.raises(CommandExecutionError) as exc_info:
        runner.run(["git", "status"], cwd=tmp_path)

    message = str(exc_info.value)
    assert "git status" in message
    assert "exec failed [REDACTED]" in message


def test_cli_runner_redacts_before_capping_output(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    completed = subprocess.CompletedProcess(
        args=["git", "status"],
        returncode=0,
        stdout="xxabc123yy",
        stderr="",
    )
    mocker.patch("subprocess.run", return_value=completed)
    runner = CliRunner(policy=CommandPolicy.default(), secrets=["abc123"], max_output_chars=5)

    result = runner.run(["git", "status"], cwd=tmp_path)

    assert result.stdout == "xx[RE"
    assert "abc" not in result.stdout
    assert "abc12" not in result.stdout

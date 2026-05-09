from pathlib import Path
from unittest.mock import call

from pytest_mock import MockerFixture

from ado_ai_pr_review.cli_runner import CommandResult
from ado_ai_pr_review.diff import parse_changed_files
from ado_ai_pr_review.git_toolset import GitToolset
from ado_ai_pr_review.tool_policy import CommandPolicy


def test_parse_changed_files_from_name_status() -> None:
    files = parse_changed_files("M\tsrc/app.py\nA\ttests/test_app.py\nD\told.py\n")

    assert [file.path for file in files] == ["src/app.py", "tests/test_app.py", "old.py"]
    assert files[0].status == "M"


def test_git_toolset_get_diff_uses_git_diff(mocker: MockerFixture, tmp_path: Path) -> None:
    runner = mocker.Mock()
    runner.run.return_value = CommandResult(
        argv=[],
        returncode=0,
        stdout="diff --git a/src/app.py b/src/app.py\n",
        stderr="",
    )
    toolset = GitToolset(runner=runner, repo_root=tmp_path)

    diff = toolset.diff("origin/main...HEAD", unified=0)

    assert diff.startswith("diff --git")
    assert runner.run.call_args.args[0] == ["git", "diff", "--unified=0", "origin/main...HEAD"]


def test_git_toolset_fetch_argv_matches_default_policy(mocker: MockerFixture, tmp_path: Path) -> None:
    runner = mocker.Mock()
    runner.run.return_value = CommandResult(argv=[], returncode=0, stdout="", stderr="")
    toolset = GitToolset(runner=runner, repo_root=tmp_path)

    toolset.fetch()

    argv = runner.run.call_args.args[0]
    assert argv == ["git", "fetch", "origin", "--prune"]
    CommandPolicy.default().validate(argv)


def test_git_toolset_diff_argv_matches_default_policy(mocker: MockerFixture, tmp_path: Path) -> None:
    runner = mocker.Mock()
    runner.run.return_value = CommandResult(argv=[], returncode=0, stdout="", stderr="")
    toolset = GitToolset(runner=runner, repo_root=tmp_path)

    toolset.diff("origin/main...HEAD", unified=0)

    argv = runner.run.call_args.args[0]
    assert argv == ["git", "diff", "--unified=0", "origin/main...HEAD"]
    CommandPolicy.default().validate(argv)


def test_git_toolset_name_status_argv_matches_default_policy(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    runner = mocker.Mock()
    runner.run.return_value = CommandResult(argv=[], returncode=0, stdout="", stderr="")
    toolset = GitToolset(runner=runner, repo_root=tmp_path)

    toolset.name_status("origin/main...HEAD")

    argv = runner.run.call_args.args[0]
    assert argv == ["git", "diff", "--name-status", "origin/main...HEAD"]
    CommandPolicy.default().validate(argv)


def test_git_toolset_checkout_new_branch_argv_matches_default_policy(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    runner = mocker.Mock()
    runner.run.return_value = CommandResult(argv=[], returncode=0, stdout="", stderr="")
    toolset = GitToolset(runner=runner, repo_root=tmp_path)

    toolset.checkout_new_branch("review/branch-1")

    argv = runner.run.call_args.args[0]
    assert argv == ["git", "checkout", "-B", "review/branch-1"]
    CommandPolicy.default().validate(argv)


def test_git_toolset_add_argv_matches_default_policy(mocker: MockerFixture, tmp_path: Path) -> None:
    runner = mocker.Mock()
    runner.run.return_value = CommandResult(argv=[], returncode=0, stdout="", stderr="")
    toolset = GitToolset(runner=runner, repo_root=tmp_path)

    toolset.add(["src/app.py"])

    argv = runner.run.call_args.args[0]
    assert argv == ["git", "add", "src/app.py"]
    CommandPolicy.default().validate(argv)


def test_git_toolset_commit_argv_matches_default_policy(mocker: MockerFixture, tmp_path: Path) -> None:
    runner = mocker.Mock()
    runner.run.side_effect = [
        CommandResult(argv=[], returncode=0, stdout="", stderr=""),
        CommandResult(argv=[], returncode=0, stdout="abc123\n", stderr=""),
    ]
    toolset = GitToolset(runner=runner, repo_root=tmp_path)

    sha = toolset.commit("review changes")

    assert sha == "abc123"
    assert runner.run.call_args_list == [
        call(["git", "commit", "-m", "review changes"], cwd=tmp_path),
        call(["git", "rev-parse", "HEAD"], cwd=tmp_path),
    ]
    for argv in (call_args.args[0] for call_args in runner.run.call_args_list):
        CommandPolicy.default().validate(argv)


def test_git_toolset_push_argv_matches_default_policy(mocker: MockerFixture, tmp_path: Path) -> None:
    runner = mocker.Mock()
    runner.run.return_value = CommandResult(argv=[], returncode=0, stdout="", stderr="")
    toolset = GitToolset(runner=runner, repo_root=tmp_path)

    toolset.push("origin", "review/branch-1")

    argv = runner.run.call_args.args[0]
    assert argv == ["git", "push", "origin", "review/branch-1"]
    CommandPolicy.default().validate(argv)

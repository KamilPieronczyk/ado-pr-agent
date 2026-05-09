# tests/test_local_adapter.py
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ado_ai_pr_review.models import ReviewCommand
from ado_ai_pr_review.tool_policy import CommandPolicy


def test_command_policy_allows_rev_parse_abbrev_ref_head() -> None:
    policy = CommandPolicy.default()
    policy.validate(["git", "rev-parse", "--abbrev-ref", "HEAD"])  # must not raise


def test_local_adapter_load_request_returns_review_request(tmp_path: Path) -> None:
    from ado_ai_pr_review.adapters.local import LocalCliAdapter
    from ado_ai_pr_review.cli_runner import CliRunner
    from ado_ai_pr_review.git_toolset import GitToolset

    runner = MagicMock(spec=CliRunner)
    runner.run.return_value = MagicMock(stdout="feature-branch\n", returncode=0, stderr="", argv=[])

    git = MagicMock(spec=GitToolset)
    git.diff.return_value = ""

    adapter = LocalCliAdapter(
        repo_root=tmp_path,
        command=ReviewCommand.REVIEW,
        target_branch="main",
        _runner=runner,
        _git=git,
    )
    request = adapter.load_request()

    assert request.command is ReviewCommand.REVIEW
    assert request.pr_context.pr_id is None
    assert request.pr_context.source_branch == "feature-branch"
    assert request.pr_context.target_branch == "main"
    assert request.pr_context.build_id == "local"
    assert request.diff_text == ""
    assert request.local_findings == ()


def test_local_adapter_publish_review_writes_to_stdout(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from ado_ai_pr_review.adapters.local import LocalCliAdapter
    from ado_ai_pr_review.models import ReviewResult

    adapter = LocalCliAdapter(repo_root=tmp_path, command=ReviewCommand.REVIEW)
    result = ReviewResult(summary="All good.", findings=[])
    adapter.publish_review(result)

    out = capsys.readouterr().out
    assert "All good." in out


def test_local_adapter_publish_error_writes_to_stderr(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from ado_ai_pr_review.adapters.local import LocalCliAdapter

    adapter = LocalCliAdapter(repo_root=tmp_path, command=ReviewCommand.REVIEW)
    adapter.publish_error(RuntimeError("boom"))

    err = capsys.readouterr().err
    assert "boom" in err


def test_local_adapter_create_fix_branch_commits_and_returns_false(tmp_path: Path) -> None:
    from ado_ai_pr_review.adapters.local import LocalCliAdapter
    from ado_ai_pr_review.cli_runner import CliRunner
    from ado_ai_pr_review.git_toolset import GitToolset
    from ado_ai_pr_review.models import FixCandidate, FixDelivery

    runner = MagicMock(spec=CliRunner)
    runner.run.return_value = MagicMock(stdout="abc1234\n", returncode=0, stderr="", argv=[])

    git = MagicMock(spec=GitToolset)
    git.commit.return_value = "abc1234"

    candidate_file = tmp_path / "file.py"
    candidate_file.write_text("original", encoding="utf-8")

    adapter = LocalCliAdapter(
        repo_root=tmp_path,
        command=ReviewCommand.FIX,
        _runner=runner,
        _git=git,
    )
    candidates = [
        FixCandidate(
            delivery=FixDelivery.FIX_BRANCH_CANDIDATE,
            title="Fix import",
            explanation="Remove unused import.",
            file_path="file.py",
            replacement="fixed",
            commit_message="fix: remove unused import",
        )
    ]
    result = adapter.create_fix_branch(candidates, "ai-fix/pr-1/run-1", "main")

    assert result is False
    git.checkout_new_branch.assert_called_once_with("ai-fix/pr-1/run-1")
    git.add.assert_called_once_with(["file.py"])
    git.commit.assert_called_once_with("fix: remove unused import")
    assert candidate_file.read_text() == "fixed"

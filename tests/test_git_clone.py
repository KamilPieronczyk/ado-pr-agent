from __future__ import annotations

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from ado_ai_pr_review.errors import WorkspaceBoundaryError
from ado_ai_pr_review.git_clone import GitCloneService


def test_git_clone_service_runs_git_clone(mocker: MockerFixture, tmp_path: Path) -> None:
    runner = mocker.Mock()
    destination = tmp_path / "repo"
    service = GitCloneService(runner=runner)

    service.clone_branch("https://example.com/repo.git", "main", destination)

    runner.run.assert_called_once_with(
        ["git", "clone", "--depth", "50", "--branch", "main", "https://example.com/repo.git", str(destination)],
        cwd=destination.parent,
    )


def test_git_clone_service_rejects_non_empty_destination(mocker: MockerFixture, tmp_path: Path) -> None:
    runner = mocker.Mock()
    destination = tmp_path / "repo"
    destination.mkdir()
    (destination / "existing.txt").write_text("content", encoding="utf-8")
    service = GitCloneService(runner=runner)

    with pytest.raises(WorkspaceBoundaryError, match="not empty"):
        service.clone_branch("https://example.com/repo.git", "main", destination)

    runner.run.assert_not_called()

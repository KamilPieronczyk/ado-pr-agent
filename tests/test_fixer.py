from pathlib import Path
from typing import cast

import pytest
from pytest_mock import MockerFixture

from ado_ai_pr_review.fixer import MechanicalFixer
from ado_ai_pr_review.models import FixCandidate, FixDelivery


def test_fixer_rejects_non_mechanical_candidate() -> None:
    fixer = MechanicalFixer(git_toolset=None, ado_toolset=None)
    candidate = FixCandidate(
        delivery=FixDelivery.FIX_BRANCH_CANDIDATE,
        title="Rewrite pricing logic",
        explanation="Change discount behavior.",
    )

    assert fixer.is_allowed(candidate) is False


def test_fixer_creates_one_commit_per_branch_candidate(mocker: MockerFixture, tmp_path: Path) -> None:
    git = mocker.Mock()
    ado = mocker.Mock()
    ado.create_pr.return_value = {"pullRequestId": 99, "url": "https://dev.azure.com/acme/pr/99"}
    (tmp_path / "src").mkdir()
    fixer = MechanicalFixer(git_toolset=git, ado_toolset=ado, repo_root=tmp_path)
    candidates = [
        FixCandidate(
            delivery=FixDelivery.FIX_BRANCH_CANDIDATE,
            title="Format imports",
            explanation="Import cleanup.",
            file_path="src/app.py",
            replacement="import os\n",
            commit_message="fix: format imports",
        )
    ]

    pr = fixer.create_fix_branch(
        candidates=candidates,
        branch_name="ai-fix/pr-42/9001",
        target_branch="feature",
    )

    pr_dict = cast(dict[str, object], pr)
    assert pr_dict["pullRequestId"] == 99
    git.commit.assert_called_once_with("fix: format imports")


def test_fixer_raises_when_no_commits_produced(mocker: MockerFixture, tmp_path: Path) -> None:
    git = mocker.Mock()
    ado = mocker.Mock()
    fixer = MechanicalFixer(git_toolset=git, ado_toolset=ado, repo_root=tmp_path)
    # A candidate that fails is_allowed (business logic)
    candidates = [
        FixCandidate(
            delivery=FixDelivery.FIX_BRANCH_CANDIDATE,
            title="Rewrite pricing logic",
            explanation="Change discount behavior.",
            file_path="src/app.py",
            replacement="pass\n",
            commit_message="fix: pricing",
        )
    ]

    with pytest.raises(RuntimeError, match="No mechanical candidates"):
        fixer.create_fix_branch(
            candidates=candidates,
            branch_name="ai-fix/pr-42/9001",
            target_branch="feature",
        )

from pathlib import Path
from typing import cast

import pytest
from pytest_mock import MockerFixture

from ado_ai_pr_review.fixer import MechanicalFixPolicy, MechanicalFixer
from ado_ai_pr_review.models import FixCandidate, FixDelivery


def _candidate(
    title: str = "Format imports",
    explanation: str = "Import cleanup.",
    file_path: str = "src/app.py",
    replacement: str = "import os\n",
    commit_message: str = "fix: format imports",
    delivery: FixDelivery = FixDelivery.FIX_BRANCH_CANDIDATE,
) -> FixCandidate:
    return FixCandidate(
        delivery=delivery,
        title=title,
        explanation=explanation,
        file_path=file_path,
        replacement=replacement,
        commit_message=commit_message,
    )


# --- MechanicalFixPolicy ---

def test_policy_rejects_business_logic_candidate() -> None:
    policy = MechanicalFixPolicy()
    assert policy.is_allowed(_candidate(title="Rewrite pricing logic", explanation="Change discount behavior.")) is False


def test_policy_allows_mechanical_candidate() -> None:
    policy = MechanicalFixPolicy()
    assert policy.is_allowed(_candidate(title="Format imports", explanation="Import cleanup.")) is True


# --- MechanicalFixer.apply_commits ---

def test_fixer_creates_one_commit_per_branch_candidate(mocker: MockerFixture, tmp_path: Path) -> None:
    git = mocker.Mock()
    git.commit.return_value = "abc1234"
    (tmp_path / "src").mkdir()

    fixer = MechanicalFixer(git=git, repo_root=tmp_path)
    policy = MechanicalFixPolicy()
    shas = fixer.apply_commits(
        candidates=[_candidate()],
        branch_name="ai-fix/pr-42/9001",
        policy=policy,
    )

    assert shas == ["abc1234"]
    git.checkout_new_branch.assert_called_once_with("ai-fix/pr-42/9001")
    git.commit.assert_called_once_with("fix: format imports")


def test_fixer_raises_when_no_commits_produced(mocker: MockerFixture, tmp_path: Path) -> None:
    git = mocker.Mock()
    fixer = MechanicalFixer(git=git, repo_root=tmp_path)
    policy = MechanicalFixPolicy()
    # A candidate that fails is_allowed (business logic)
    candidates = [_candidate(title="Rewrite pricing logic", explanation="Change discount behavior.")]

    with pytest.raises(RuntimeError, match="No mechanical candidates"):
        fixer.apply_commits(candidates, branch_name="ai-fix/pr-42/9001", policy=policy)


def test_fixer_rejects_candidate_path_outside_repo(mocker: MockerFixture, tmp_path: Path) -> None:
    git = mocker.Mock()
    fixer = MechanicalFixer(git=git, repo_root=tmp_path)
    policy = MechanicalFixPolicy()
    candidates = [_candidate(file_path="../other-repo/app.py")]

    with pytest.raises(RuntimeError, match="No mechanical candidates"):
        fixer.apply_commits(candidates, branch_name="ai-fix/pr-42/1", policy=policy)

    git.add.assert_not_called()


def test_fixer_rejects_symlink_write_target(mocker: MockerFixture, tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.py"
    outside.write_text("print('outside')\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").symlink_to(outside)
    git = mocker.Mock()
    fixer = MechanicalFixer(git=git, repo_root=tmp_path)
    policy = MechanicalFixPolicy()
    candidates = [_candidate(file_path="src/app.py")]

    with pytest.raises(RuntimeError, match="No mechanical candidates"):
        fixer.apply_commits(candidates, branch_name="ai-fix/pr-42/1", policy=policy)

    assert outside.read_text(encoding="utf-8") == "print('outside')\n"

from __future__ import annotations

import logging
from pathlib import Path

from ado_ai_pr_review.errors import WorkspaceBoundaryError
from ado_ai_pr_review.models import FixCandidate, FixDelivery
from ado_ai_pr_review.ports import GitPort
from ado_ai_pr_review.workspace import WorkspaceBoundary

logger = logging.getLogger(__name__)

MECHANICAL_WORDS = {
    "format",
    "formatting",
    "lint",
    "import",
    "imports",
    "rename",
    "type",
    "typing",
    "test",
    "mechanical",
}


class MechanicalFixPolicy:
    """Stateless allow/deny policy for fix candidates. No I/O, no dependencies."""

    def is_allowed(self, candidate: FixCandidate) -> bool:
        text = f"{candidate.title} {candidate.explanation} {candidate.commit_message or ''}".lower()
        if any(word in text for word in ["business", "pricing", "discount", "authorization behavior"]):
            return False
        return any(word in text for word in MECHANICAL_WORDS)


class MechanicalFixer:
    """Applies mechanical fix candidates: checkout branch, write files, commit.

    Does NOT push or create a PR — that responsibility belongs to the adapter.
    """

    def __init__(self, git: GitPort, repo_root: Path) -> None:
        self._git = git
        self._repo_root = repo_root

    def apply_commits(
        self,
        candidates: list[FixCandidate],
        branch_name: str,
        policy: MechanicalFixPolicy,
    ) -> list[str]:
        """Checkout branch, apply allowed candidates, return list of commit SHAs.

        Raises RuntimeError if no candidates produce a commit.
        """
        workspace = WorkspaceBoundary(self._repo_root)
        # Pre-filter to determine if there are any actionable candidates before checking out
        actionable = [
            c for c in candidates
            if c.delivery is FixDelivery.FIX_BRANCH_CANDIDATE
            and policy.is_allowed(c)
            and c.file_path
            and c.replacement is not None
            and c.commit_message
        ]
        if not actionable:
            raise RuntimeError("No mechanical candidates produced commits; fix branch aborted")
        self._git.checkout_new_branch(branch_name)
        commit_shas: list[str] = []
        for candidate in actionable:
            try:
                workspace.safe_write_text(candidate.file_path, candidate.replacement)  # type: ignore[arg-type]
            except WorkspaceBoundaryError:
                logger.warning("skipping unsafe fix candidate: %s", candidate.file_path)
                continue
            self._git.add([candidate.file_path])
            commit_shas.append(self._git.commit(candidate.commit_message))  # type: ignore[arg-type]
        if not commit_shas:
            raise RuntimeError("No mechanical candidates produced commits; fix branch aborted")
        return commit_shas

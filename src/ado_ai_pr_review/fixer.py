from __future__ import annotations

import logging
from pathlib import Path

from ado_ai_pr_review.ado_toolset import AdoToolset
from ado_ai_pr_review.errors import WorkspaceBoundaryError
from ado_ai_pr_review.git_toolset import GitToolset
from ado_ai_pr_review.models import FixCandidate, FixDelivery
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


class MechanicalFixer:
    def __init__(self, git_toolset: GitToolset | None, ado_toolset: AdoToolset | None, repo_root: Path | None = None) -> None:
        self._git = git_toolset
        self._ado = ado_toolset
        self._repo_root = repo_root

    def is_allowed(self, candidate: FixCandidate) -> bool:
        text = f"{candidate.title} {candidate.explanation} {candidate.commit_message or ''}".lower()
        if any(word in text for word in ["business", "pricing", "discount", "authorization behavior"]):
            return False
        return any(word in text for word in MECHANICAL_WORDS)

    def create_fix_branch(
        self,
        candidates: list[FixCandidate],
        branch_name: str,
        target_branch: str,
    ) -> object:
        if self._git is None or self._ado is None:
            raise RuntimeError("Git and ADO toolsets are required to create a fix branch")
        workspace = WorkspaceBoundary(self._repo_root) if self._repo_root is not None else None
        self._git.checkout_new_branch(branch_name)
        commit_shas: list[str] = []
        for candidate in candidates:
            if candidate.delivery is not FixDelivery.FIX_BRANCH_CANDIDATE or not self.is_allowed(candidate):
                continue
            if not candidate.file_path or candidate.replacement is None or not candidate.commit_message:
                continue
            if workspace is None:
                continue
            try:
                workspace.safe_write_text(candidate.file_path, candidate.replacement)
            except WorkspaceBoundaryError:
                logger.warning("skipping unsafe fix candidate: %s", candidate.file_path)
                continue
            self._git.add([candidate.file_path])
            commit_shas.append(self._git.commit(candidate.commit_message))
        if not commit_shas:
            raise RuntimeError("No mechanical candidates produced commits; fix branch aborted")
        self._git.push("origin", branch_name)
        description = "Mechanical AI fix branch.\n\nCherry-pick commits:\n" + "\n".join(
            f"- `git cherry-pick {sha}`" for sha in commit_shas
        )
        return self._ado.create_pr(
            source_branch=branch_name,
            target_branch=target_branch,
            title="AI mechanical fixes",
            description=description,
        )

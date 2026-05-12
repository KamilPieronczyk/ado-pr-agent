from __future__ import annotations

from pathlib import Path

from ado_ai_pr_review.cli_runner import CliRunner
from ado_ai_pr_review.errors import WorkspaceBoundaryError


class GitCloneService:
    def __init__(self, runner: CliRunner) -> None:
        self._runner = runner

    def clone_branch(self, remote_url: str, branch: str, destination: Path) -> None:
        destination_parent = destination.parent.resolve()
        destination_resolved = destination.resolve()
        try:
            destination_resolved.relative_to(destination_parent)
        except ValueError as exc:
            raise WorkspaceBoundaryError(f"Clone destination outside temp parent: {destination}") from exc
        if destination.exists() and any(destination.iterdir()):
            raise WorkspaceBoundaryError(f"Clone destination is not empty: {destination}")
        self._runner.run(
            ["git", "clone", "--depth", "50", "--branch", branch, remote_url, str(destination_resolved)],
            cwd=destination_parent,
        )

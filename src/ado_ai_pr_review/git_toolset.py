from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from ado_ai_pr_review.cli_runner import CliRunner, CommandResult


class GitToolset:
    def __init__(self, runner: CliRunner, repo_root: Path) -> None:
        self._runner = runner
        self._repo_root = repo_root

    def fetch(self, remote: str = "origin") -> CommandResult:
        return self._runner.run(["git", "fetch", remote, "--prune"], cwd=self._repo_root)

    def diff(self, ref_range: str, unified: int = 0) -> str:
        result = self._runner.run(
            ["git", "diff", f"--unified={unified}", ref_range],
            cwd=self._repo_root,
        )
        return result.stdout

    def name_status(self, ref_range: str) -> str:
        result = self._runner.run(
            ["git", "diff", "--name-status", ref_range],
            cwd=self._repo_root,
        )
        return result.stdout

    def checkout_new_branch(self, branch: str) -> CommandResult:
        return self._runner.run(["git", "checkout", "-B", branch], cwd=self._repo_root)

    def add(self, paths: Sequence[str]) -> CommandResult:
        return self._runner.run(["git", "add", *paths], cwd=self._repo_root)

    def commit(self, message: str) -> str:
        self._runner.run(["git", "commit", "-m", message], cwd=self._repo_root)
        result = self._runner.run(["git", "rev-parse", "HEAD"], cwd=self._repo_root)
        return result.stdout.strip()

    def push(self, remote: str, branch: str) -> CommandResult:
        return self._runner.run(["git", "push", remote, branch], cwd=self._repo_root)

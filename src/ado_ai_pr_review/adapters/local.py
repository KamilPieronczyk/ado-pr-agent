# src/ado_ai_pr_review/adapters/local.py
from __future__ import annotations

import logging
from pathlib import Path

import typer

from ado_ai_pr_review.cli_runner import CliRunner
from ado_ai_pr_review.fixer import MechanicalFixer
from ado_ai_pr_review.git_toolset import GitToolset
from ado_ai_pr_review.models import FixCandidate, FixDelivery, ReviewCommand, ReviewResult
from ado_ai_pr_review.ports import PRContext, ReviewRequest
from ado_ai_pr_review.security import SecurityScanner
from ado_ai_pr_review.tool_policy import CommandPolicy

logger = logging.getLogger(__name__)


class LocalCliAdapter:
    def __init__(
        self,
        repo_root: Path,
        command: ReviewCommand,
        target_branch: str = "main",
        *,
        _runner: CliRunner | None = None,
        _git: GitToolset | None = None,
    ) -> None:
        self._repo_root = repo_root
        self._command = command
        self._target_branch = target_branch
        self._runner = _runner or CliRunner(policy=CommandPolicy.default())
        self._git = _git or GitToolset(runner=self._runner, repo_root=repo_root)

    def load_request(self) -> ReviewRequest:
        source_branch = self._runner.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=self._repo_root,
        ).stdout.strip()

        refspec = f"origin/{self._target_branch}...HEAD"
        diff_text = self._git.diff(refspec, unified=0)
        local_findings, redacted_diff = SecurityScanner().scan_diff(diff_text)

        return ReviewRequest(
            repo_root=self._repo_root,
            diff_text=redacted_diff,
            local_findings=tuple(local_findings),
            command=self._command,
            pr_context=PRContext(
                pr_id=None,
                source_branch=source_branch,
                target_branch=self._target_branch,
                is_fork=False,
                build_id="local",
            ),
        )

    def publish_onboarding(self) -> None:
        typer.echo("ADO AI review is available. Run with --command review|security|fix.")

    def publish_review(self, result: ReviewResult) -> None:
        typer.echo(f"\n=== AI Review Summary ===\n{result.summary}")
        for finding in result.findings:
            location = f"{finding.file_path}:{finding.line_start}" if finding.file_path else "general"
            typer.echo(f"\n[{finding.severity.value.upper()}] {finding.title} ({location})")
            typer.echo(finding.body)
            if finding.suggested_code:
                typer.echo(f"Suggestion:\n{finding.suggested_code}")

    def publish_error(self, exc: BaseException) -> None:
        typer.echo(f"Error: {exc}", err=True)

    def create_fix_branch(
        self,
        candidates: list[FixCandidate],
        branch_name: str,
        target_branch: str,
    ) -> bool:
        fixer = MechanicalFixer(git_toolset=None, ado_toolset=None, repo_root=self._repo_root)
        allowed = [
            c for c in candidates
            if c.delivery is FixDelivery.FIX_BRANCH_CANDIDATE
            and fixer.is_allowed(c)
            and c.file_path
            and c.replacement is not None
            and c.commit_message
        ]
        if not allowed:
            typer.echo("No mechanical fix candidates.")
            return False
        self._git.checkout_new_branch(branch_name)
        for candidate in allowed:
            assert candidate.file_path is not None
            assert candidate.replacement is not None
            assert candidate.commit_message is not None
            path = self._repo_root / candidate.file_path
            path.write_text(candidate.replacement, encoding="utf-8")
            self._git.add([candidate.file_path])
            sha = self._git.commit(candidate.commit_message)
            typer.echo(f"  {sha[:8]} {candidate.commit_message}")
        typer.echo(f"Fix branch '{branch_name}' created locally (not pushed).")
        return False

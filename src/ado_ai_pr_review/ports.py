from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ado_ai_pr_review.models import Finding, FixCandidate, ReviewCommand, ReviewResult


@dataclass(frozen=True)
class PRContext:
    pr_id: int | None
    source_branch: str
    target_branch: str
    is_fork: bool
    build_id: str


@dataclass(frozen=True)
class ReviewRequest:
    repo_root: Path
    diff_text: str                       # already redacted by SecurityScanner
    local_findings: tuple[Finding, ...]  # raw findings from SecurityScanner
    command: ReviewCommand
    pr_context: PRContext


class PlatformAdapter(Protocol):
    def load_request(self) -> ReviewRequest: ...
    def publish_onboarding(self) -> None: ...
    def publish_review(self, result: ReviewResult) -> None: ...
    def publish_error(self, exc: BaseException) -> None: ...
    def create_fix_branch(
        self,
        candidates: list[FixCandidate],
        branch_name: str,
        target_branch: str,
    ) -> bool: ...


class LLMPort(Protocol):
    def review_json(self, system_prompt: str, user_prompt: str) -> ReviewResult: ...

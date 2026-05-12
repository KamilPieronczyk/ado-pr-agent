from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from ado_ai_pr_review.models import Finding, FixCandidate, FixPlanResult, ReviewCommand, ReviewResult


@dataclass(frozen=True)
class PRContext:
    pr_id: int | None
    source_branch: str
    target_branch: str
    is_fork: bool
    run_id: str
    request_id: str = "unknown"


@dataclass(frozen=True)
class ReviewRequest:
    repo_root: Path
    diff_text: str                       # already redacted by SecurityScanner
    local_findings: tuple[Finding, ...]  # raw findings from SecurityScanner
    command: ReviewCommand
    pr_context: PRContext


@runtime_checkable
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


@runtime_checkable
class LLMPort(Protocol):
    def review_json(self, system_prompt: str, user_prompt: str) -> ReviewResult: ...
    def fix_plan_json(self, system_prompt: str, user_prompt: str) -> FixPlanResult: ...


@runtime_checkable
class GitPort(Protocol):
    def checkout_new_branch(self, branch: str) -> object: ...
    def add(self, paths: Sequence[str]) -> object: ...
    def commit(self, message: str) -> str: ...
    def push(self, remote: str, branch: str) -> object: ...


@runtime_checkable
class AdoApiPort(Protocol):
    def create_pr(
        self,
        source_branch: str,
        target_branch: str,
        title: str,
        description: str,
    ) -> object: ...

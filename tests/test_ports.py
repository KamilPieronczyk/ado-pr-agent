from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from ado_ai_pr_review.models import ReviewCommand
from ado_ai_pr_review.ports import PRContext, ReviewRequest


def test_pr_context_is_frozen() -> None:
    ctx = PRContext(pr_id=1, source_branch="feat", target_branch="main", is_fork=False, build_id="42")
    with pytest.raises(FrozenInstanceError):
        ctx.pr_id = 2  # type: ignore[misc]


def test_pr_context_allows_none_pr_id() -> None:
    ctx = PRContext(pr_id=None, source_branch="feat", target_branch="main", is_fork=False, build_id="local")
    assert ctx.pr_id is None


def test_review_request_is_frozen() -> None:
    ctx = PRContext(pr_id=1, source_branch="feat", target_branch="main", is_fork=False, build_id="42")
    req = ReviewRequest(
        repo_root=Path("/tmp"),
        diff_text="some diff",
        local_findings=(),
        command=ReviewCommand.REVIEW,
        pr_context=ctx,
    )
    with pytest.raises(FrozenInstanceError):
        req.diff_text = "other"  # type: ignore[misc]


def test_review_request_stores_local_findings() -> None:
    from ado_ai_pr_review.models import Finding, FindingSeverity, FindingType
    finding = Finding(
        type=FindingType.SECURITY,
        severity=FindingSeverity.CRITICAL,
        title="Secret",
        body="Remove it.",
    )
    ctx = PRContext(pr_id=1, source_branch="feat", target_branch="main", is_fork=False, build_id="1")
    req = ReviewRequest(
        repo_root=Path("/tmp"),
        diff_text="",
        local_findings=(finding,),
        command=ReviewCommand.SECURITY,
        pr_context=ctx,
    )
    assert len(req.local_findings) == 1
    assert req.local_findings[0].title == "Secret"

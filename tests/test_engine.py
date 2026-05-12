from __future__ import annotations

from pathlib import Path

import pytest

from ado_ai_pr_review.models import (
    Finding,
    FindingSeverity,
    FindingType,
    FixCandidate,
    FixPlanResult,
    ReviewCommand,
    ReviewResult,
)
from ado_ai_pr_review.ports import PRContext, ReviewRequest


def _make_pr_context(pr_id: int | None = 42) -> PRContext:
    return PRContext(
        pr_id=pr_id,
        source_branch="refs/heads/feature",
        target_branch="refs/heads/main",
        is_fork=False,
        run_id="1",
    )


def _make_request(command: ReviewCommand = ReviewCommand.REVIEW, repo_root: Path | None = None) -> ReviewRequest:
    return ReviewRequest(
        repo_root=repo_root or Path("/tmp"),
        diff_text="diff text",
        local_findings=(),
        command=command,
        pr_context=_make_pr_context(),
    )


class _MockPlatform:
    def __init__(self, request: ReviewRequest | None = None, load_raises: Exception | None = None) -> None:
        self._request = request
        self._load_raises = load_raises
        self.onboarding_called = False
        self.review_result: ReviewResult | None = None
        self.error: BaseException | None = None
        self.fix_branch_args: tuple[object, ...] | None = None
        self.fix_branch_return = False

    def load_request(self) -> ReviewRequest:
        if self._load_raises is not None:
            raise self._load_raises
        assert self._request is not None
        return self._request

    def publish_onboarding(self) -> None:
        self.onboarding_called = True

    def publish_review(self, result: ReviewResult) -> None:
        self.review_result = result

    def publish_error(self, exc: BaseException) -> None:
        self.error = exc

    def create_fix_branch(self, candidates: list[FixCandidate], branch_name: str, target_branch: str) -> bool:
        self.fix_branch_args = (candidates, branch_name, target_branch)
        return self.fix_branch_return


class _MockLLM:
    def __init__(self, result: ReviewResult | None = None, raises: Exception | None = None) -> None:
        self._result = result
        self._raises = raises
        self.calls: int = 0

    def review_json(self, system_prompt: str, user_prompt: str) -> ReviewResult:
        self.calls += 1
        if self._raises is not None:
            raise self._raises
        assert self._result is not None
        return self._result

    def fix_plan_json(self, system_prompt: str, user_prompt: str) -> FixPlanResult:
        raise NotImplementedError


def _make_review_result(summary: str = "ok") -> ReviewResult:
    return ReviewResult(summary=summary, findings=[])


def test_engine_publishes_onboarding_for_onboarding_command(tmp_path: Path) -> None:
    """Engine should call publish_onboarding when load_request returns ONBOARDING command."""
    from ado_ai_pr_review.engine import ReviewEngine

    _write_config(tmp_path)
    request = _make_request(command=ReviewCommand.ONBOARDING, repo_root=tmp_path)
    platform = _MockPlatform(request=request)
    engine = ReviewEngine(platform=platform, model=_MockLLM(), repo_root=tmp_path)
    cmd = engine.run()

    assert cmd is ReviewCommand.ONBOARDING
    assert platform.onboarding_called



def test_engine_runs_review_and_publishes(tmp_path: Path) -> None:
    from ado_ai_pr_review.engine import ReviewEngine

    _write_config(tmp_path)
    request = _make_request(command=ReviewCommand.REVIEW, repo_root=tmp_path)
    llm = _MockLLM(result=_make_review_result("two issues"))
    platform = _MockPlatform(request=request)
    engine = ReviewEngine(platform=platform, model=llm, repo_root=tmp_path)
    cmd = engine.run()

    assert cmd is ReviewCommand.REVIEW
    assert platform.review_result is not None
    assert platform.review_result.summary == "two issues"
    assert llm.calls == 1


def test_engine_extends_findings_with_local_findings(tmp_path: Path) -> None:
    from ado_ai_pr_review.engine import ReviewEngine

    _write_config(tmp_path)
    local_finding = Finding(
        type=FindingType.SECURITY,
        severity=FindingSeverity.CRITICAL,
        title="Secret",
        body="Remove it.",
    )
    request = ReviewRequest(
        repo_root=tmp_path,
        diff_text="diff",
        local_findings=(local_finding,),
        command=ReviewCommand.REVIEW,
        pr_context=_make_pr_context(),
    )
    llm = _MockLLM(result=_make_review_result())
    platform = _MockPlatform(request=request)
    engine = ReviewEngine(platform=platform, model=llm, repo_root=tmp_path)
    engine.run()

    assert platform.review_result is not None
    assert any(f.title == "Secret" for f in platform.review_result.findings)


def test_engine_calls_publish_error_and_reraises_on_load_failure(tmp_path: Path) -> None:
    from ado_ai_pr_review.engine import ReviewEngine

    _write_config(tmp_path)
    exc = RuntimeError("no diff")
    platform = _MockPlatform(load_raises=exc)
    engine = ReviewEngine(platform=platform, model=_MockLLM(), repo_root=tmp_path)

    with pytest.raises(RuntimeError, match="no diff"):
        engine.run()

    assert platform.error is exc


def test_engine_delegates_fix_branch_to_platform(tmp_path: Path) -> None:
    from ado_ai_pr_review.engine import ReviewEngine

    _write_config(tmp_path)
    request = _make_request(command=ReviewCommand.FIX, repo_root=tmp_path)
    llm = _MockLLM(result=_make_review_result())
    platform = _MockPlatform(request=request)
    engine = ReviewEngine(platform=platform, model=llm, repo_root=tmp_path)
    engine.run()

    assert platform.fix_branch_args is not None


def test_engine_runs_review_without_config_file(tmp_path: Path) -> None:
    from ado_ai_pr_review.engine import ReviewEngine

    request = _make_request(command=ReviewCommand.REVIEW, repo_root=tmp_path)
    llm = _MockLLM(result=_make_review_result("no config needed"))
    platform = _MockPlatform(request=request)
    engine = ReviewEngine(platform=platform, model=llm, repo_root=tmp_path)
    cmd = engine.run()

    assert cmd is ReviewCommand.REVIEW
    assert platform.review_result is not None
    assert platform.review_result.summary == "no config needed"


def test_review_result_is_value_object() -> None:
    from ado_ai_pr_review.models import ReviewResult

    r = ReviewResult(summary="ok", findings=[])
    with pytest.raises(Exception):
        r.findings = []  # frozen model must reject attribute assignment


def _write_config(root: Path) -> None:
    from ado_ai_pr_review.bootstrap import Bootstrapper

    # Let the bootstrapper create all the default files first so subsequent
    # engine.run() calls don't see any missing files and short-circuit to onboarding.
    Bootstrapper().create_missing_files(root)

    # Overwrite the config with a minimal valid version so ReviewConfig.load() succeeds.
    (root / ".ado-ai-review.yml").write_text(
        "version: 1\ninstructions:\n  reviewer: r.md\n  security: s.md\n  indexer: i.md\n  fixer: f.md\n",
        encoding="utf-8",
    )

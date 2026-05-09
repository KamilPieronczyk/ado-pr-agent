from __future__ import annotations

import contextlib
import logging
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ado_ai_pr_review.ado_toolset import AdoToolset
from ado_ai_pr_review.cli_runner import CliRunner
from ado_ai_pr_review.commands import CommandRouter
from ado_ai_pr_review.fixer import MechanicalFixer
from ado_ai_pr_review.git_toolset import GitToolset
from ado_ai_pr_review.models import FixCandidate, ReviewCommand, ReviewResult
from ado_ai_pr_review.ports import PRContext, ReviewRequest
from ado_ai_pr_review.publisher import SuggestionPublisher
from ado_ai_pr_review.runtime import RuntimeContext
from ado_ai_pr_review.security import SecurityScanner
from ado_ai_pr_review.tool_policy import CommandPolicy

logger = logging.getLogger(__name__)


class _RepoProject(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str


class _Repository(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    name: str
    remote_url: str = Field(alias="remoteUrl")
    project: _RepoProject


class _PullRequestResource(BaseModel):
    model_config = ConfigDict(extra="allow")
    pull_request_id: int = Field(alias="pullRequestId")
    source_ref_name: str = Field(alias="sourceRefName")
    target_ref_name: str = Field(alias="targetRefName")
    repository: _Repository


class _Comment(BaseModel):
    model_config = ConfigDict(extra="allow")
    content: str = ""


class _Resource(BaseModel):
    model_config = ConfigDict(extra="allow")
    # Direct PR events (created, updated)
    pull_request_id: int | None = Field(default=None, alias="pullRequestId")
    source_ref_name: str | None = Field(default=None, alias="sourceRefName")
    target_ref_name: str | None = Field(default=None, alias="targetRefName")
    repository: _Repository | None = None
    # Comment events
    pull_request: _PullRequestResource | None = Field(default=None, alias="pullRequest")
    comment: _Comment | None = None


class _Collection(BaseModel):
    model_config = ConfigDict(extra="allow")
    base_url: str = Field(alias="baseUrl")


class _ResourceContainers(BaseModel):
    model_config = ConfigDict(extra="allow")
    collection: _Collection


class AdoWebhookPayload(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    event_type: str = Field(alias="eventType")
    resource: _Resource
    resource_containers: _ResourceContainers = Field(alias="resourceContainers")

    @model_validator(mode="after")
    def validate_pr_resolvable(self) -> AdoWebhookPayload:
        try:
            _ = self.pull_request_id
        except ValueError as exc:
            raise ValueError("Cannot resolve pull request from payload") from exc
        return self

    @property
    def pull_request_id(self) -> int:
        if self.resource.pull_request is not None:
            return self.resource.pull_request.pull_request_id
        if self.resource.pull_request_id is not None:
            return self.resource.pull_request_id
        raise ValueError("pull_request_id not found in payload")

    @property
    def source_ref_name(self) -> str:
        if self.resource.pull_request is not None:
            return self.resource.pull_request.source_ref_name
        return self.resource.source_ref_name or ""

    @property
    def target_ref_name(self) -> str:
        if self.resource.pull_request is not None:
            return self.resource.pull_request.target_ref_name
        return self.resource.target_ref_name or ""

    @property
    def repository_name(self) -> str:
        repo = self.resource.pull_request.repository if self.resource.pull_request else self.resource.repository
        return repo.name if repo else ""

    @property
    def remote_url(self) -> str:
        repo = self.resource.pull_request.repository if self.resource.pull_request else self.resource.repository
        return repo.remote_url if repo else ""

    @property
    def project_name(self) -> str:
        repo = self.resource.pull_request.repository if self.resource.pull_request else self.resource.repository
        return repo.project.name if repo else ""

    @property
    def organization_url(self) -> str:
        return self.resource_containers.collection.base_url

    @property
    def inline_command(self) -> str | None:
        if self.resource.comment and self.resource.comment.content:
            return self.resource.comment.content
        return None


class AdoWebhookAdapter:
    def __init__(
        self,
        payload: AdoWebhookPayload,
        auth_token: str,
        temp_dir: Path,
    ) -> None:
        self._payload = payload
        self._auth_token = auth_token
        self._temp_dir = temp_dir

        # Clone the repo branch into temp_dir
        authenticated_url = self._authenticated_clone_url()
        source_branch = payload.source_ref_name.removeprefix("refs/heads/")
        bootstrap_runner = CliRunner(policy=CommandPolicy.default(), secrets=[auth_token])
        bootstrap_runner.run(
            ["git", "clone", "--depth", "50", "--branch", source_branch, authenticated_url, str(temp_dir)],
            cwd=temp_dir.parent,
        )

        # Build RuntimeContext from payload (not env vars)
        self._context = RuntimeContext(
            repo_root=temp_dir,
            organization_url=payload.organization_url,
            project=payload.project_name,
            repository_id="",  # not needed for REST calls via az
            repository_name=payload.repository_name,
            pull_request_id=payload.pull_request_id,
            source_branch=payload.source_ref_name,
            target_branch=payload.target_ref_name,
            is_fork=False,
            build_id="webhook",
            system_access_token=auth_token,
        )
        self._runner = CliRunner(policy=CommandPolicy.default(), secrets=[auth_token])
        self._ado = AdoToolset(runner=self._runner, context=self._context)
        self._git = GitToolset(runner=self._runner, repo_root=temp_dir)
        self._publisher = SuggestionPublisher(ado_toolset=self._ado)

    def load_request(self) -> ReviewRequest:
        if self._payload.inline_command is not None:
            command = CommandRouter._detect(self._payload.inline_command)
            if command is None:
                command = ReviewCommand.ONBOARDING
        else:
            threads = cast(dict[str, Any], self._ado.list_pr_threads())
            decision = CommandRouter().route(threads)
            command = decision.command

        if command is ReviewCommand.ONBOARDING:
            return ReviewRequest(
                repo_root=self._temp_dir,
                diff_text="",
                local_findings=(),
                command=ReviewCommand.ONBOARDING,
                pr_context=self._make_pr_context(),
            )

        target_ref = self._payload.target_ref_name.removeprefix("refs/heads/")
        diff_text = self._git.diff(f"origin/{target_ref}...HEAD", unified=0)
        local_findings, redacted_diff = SecurityScanner().scan_diff(diff_text)

        return ReviewRequest(
            repo_root=self._temp_dir,
            diff_text=redacted_diff,
            local_findings=tuple(local_findings),
            command=command,
            pr_context=self._make_pr_context(),
        )

    def publish_onboarding(self) -> None:
        self._publisher.publish_onboarding()

    def publish_review(self, result: ReviewResult) -> None:
        self._publisher.publish_review(result)

    def publish_error(self, exc: BaseException) -> None:
        logger.error("webhook review failed: %s", exc, exc_info=True)
        with contextlib.suppress(Exception):
            self._ado.create_pr_thread(body={
                "comments": [{
                    "parentCommentId": 0,
                    "content": f"ADO AI review failed: {type(exc).__name__}. Check webhook logs for details.",
                    "commentType": "text",
                }],
                "status": "active",
                "properties": {"adoAiReview.kind": {"$type": "System.String", "$value": "error"}},
            })

    def create_fix_branch(
        self,
        candidates: list[FixCandidate],
        branch_name: str,
        target_branch: str,
    ) -> bool:
        fixer = MechanicalFixer(
            git_toolset=self._git,
            ado_toolset=self._ado,
            repo_root=self._temp_dir,
        )
        try:
            fixer.create_fix_branch(candidates, branch_name, target_branch)
            return True
        except RuntimeError as exc:
            logger.warning("fix branch not created: %s", exc)
            return False

    def _make_pr_context(self) -> PRContext:
        return PRContext(
            pr_id=self._payload.pull_request_id,
            source_branch=self._payload.source_ref_name,
            target_branch=self._payload.target_ref_name,
            is_fork=False,
            build_id="webhook",
        )

    def _authenticated_clone_url(self) -> str:
        url = self._payload.remote_url
        if url.startswith("https://"):
            return url.replace("https://", f"https://:{self._auth_token}@", 1)
        return url

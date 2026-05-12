from __future__ import annotations

import base64
import contextlib
import json as _json
import logging
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ado_ai_pr_review.ado_toolset import AdoToolset
from ado_ai_pr_review.cli_runner import CliRunner
from ado_ai_pr_review.commands import CommandRouter
from ado_ai_pr_review.fixer import MechanicalFixer
from ado_ai_pr_review.git_clone import GitCloneService
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
    name: str = ""


class _Repository(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str = ""
    name: str = ""
    remote_url: str = Field(default="", alias="remoteUrl")
    project: _RepoProject = Field(default_factory=_RepoProject)


class _PullRequestResource(BaseModel):
    model_config = ConfigDict(extra="allow")
    pull_request_id: int = Field(alias="pullRequestId")
    source_ref_name: str = Field(default="", alias="sourceRefName")
    target_ref_name: str = Field(default="", alias="targetRefName")
    repository: _Repository = Field(default_factory=_Repository)


class _Comment(BaseModel):
    model_config = ConfigDict(extra="allow")
    content: str = ""


class _SelfLink(BaseModel):
    model_config = ConfigDict(extra="allow")
    href: str = ""


class _ResourceLinks(BaseModel):
    """Captures _links from flat-comment event payloads."""

    model_config = ConfigDict(extra="allow")
    pull_requests: _SelfLink = Field(default_factory=_SelfLink, alias="pullRequests")
    repository: _SelfLink = Field(default_factory=_SelfLink)

    def pr_id(self) -> int | None:
        m = re.search(r"/pullRequests/(\d+)", self.pull_requests.href)
        return int(m.group(1)) if m else None

    def repo_id(self) -> str:
        m = re.search(r"/repositories/([a-f0-9\-]+)", self.repository.href)
        return m.group(1) if m else ""


class _Resource(BaseModel):
    model_config = ConfigDict(extra="allow")
    # Direct PR events (created, updated)
    pull_request_id: int | None = Field(default=None, alias="pullRequestId")
    source_ref_name: str | None = Field(default=None, alias="sourceRefName")
    target_ref_name: str | None = Field(default=None, alias="targetRefName")
    repository: _Repository | None = None
    # Nested comment events (resource has pullRequest + comment sub-objects)
    pull_request: _PullRequestResource | None = Field(default=None, alias="pullRequest")
    comment: _Comment | None = None
    # Flat comment events: resource IS the comment (ADO ms.vss-code.git-pullrequest-comment-event)
    content: str | None = None
    links: _ResourceLinks = Field(default_factory=_ResourceLinks, alias="_links")


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
        # Flat comment event: PR ID lives in _links.pullRequests.href
        pr_id = self.resource.links.pr_id()
        if pr_id is not None:
            return pr_id
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
    def repository_id(self) -> str:
        repo = self.resource.pull_request.repository if self.resource.pull_request else self.resource.repository
        if repo and repo.id:
            return repo.id
        return self.resource.links.repo_id()

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
        # Nested comment event: resource has a comment sub-object
        if self.resource.comment and self.resource.comment.content:
            return self.resource.comment.content
        # Flat comment event: resource.content IS the comment text
        if self.resource.content:
            return self.resource.content
        return None

    @property
    def is_flat_comment_event(self) -> bool:
        """True when the payload is a flat-comment event (resource = the comment itself)."""
        return (
            self.resource.pull_request is None
            and self.resource.pull_request_id is None
            and self.resource.links.pr_id() is not None
        )


class AdoWebhookAdapter:
    def __init__(
        self,
        payload: AdoWebhookPayload,
        auth_token: str,
        temp_dir: Path,
        request_id: str = "unknown",
    ) -> None:
        self._payload = payload
        self._auth_token = auth_token
        self._temp_dir = temp_dir
        self._request_id = request_id

        self._runner = CliRunner(policy=CommandPolicy.default(), secrets=[auth_token])

        # For flat-comment events the payload lacks repo/branch info; fetch via REST.
        if payload.is_flat_comment_event:
            pr_details = self._fetch_pr_details(
                org_url=payload.organization_url,
                repo_id=payload.repository_id,
                pr_id=payload.pull_request_id,
            )
        else:
            pr_details = {}

        self._source_ref = payload.source_ref_name or pr_details.get("sourceRefName", "")
        self._target_ref = payload.target_ref_name or pr_details.get("targetRefName", "")
        repo_info: dict[str, Any] = pr_details.get("repository", {})
        self._remote_url = payload.remote_url or repo_info.get("remoteUrl", "")
        self._repo_name = payload.repository_name or repo_info.get("name", "")
        self._repo_id = payload.repository_id or repo_info.get("id", "")
        self._project_name = payload.project_name or repo_info.get("project", {}).get("name", "")

        # Clone the repo branch into temp_dir
        authenticated_url = self._make_authenticated_url(self._remote_url)
        source_branch = self._source_ref.removeprefix("refs/heads/")
        GitCloneService(self._runner).clone_branch(authenticated_url, source_branch, temp_dir)

        self._context = RuntimeContext(
            repo_root=temp_dir,
            organization_url=payload.organization_url,
            project=self._project_name,
            repository_id=self._repo_id,
            repository_name=self._repo_name,
            pull_request_id=payload.pull_request_id,
            source_branch=self._source_ref,
            target_branch=self._target_ref,
            is_fork=False,
            build_id="webhook",
            system_access_token=auth_token,
        )
        self._ado = AdoToolset(runner=self._runner, context=self._context)
        self._git = GitToolset(runner=self._runner, repo_root=temp_dir)
        self._publisher = SuggestionPublisher(ado_toolset=self._ado)

    def load_request(self) -> ReviewRequest:
        if self._payload.inline_command is not None:
            command = CommandRouter.detect_command(self._payload.inline_command)
            if command is None:
                # Unrecognised comment (e.g. agent's own reply) — skip silently.
                command = ReviewCommand.SKIP
        else:
            threads = cast(dict[str, Any], self._ado.list_pr_threads())
            decision = CommandRouter().route(threads)
            command = decision.command

        if command in (ReviewCommand.ONBOARDING, ReviewCommand.SKIP):
            return ReviewRequest(
                repo_root=self._temp_dir,
                diff_text="",
                local_findings=(),
                command=command,
                pr_context=self._make_pr_context(),
            )

        target_ref = self._target_ref.removeprefix("refs/heads/")
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
            source_branch=self._source_ref,
            target_branch=self._target_ref,
            is_fork=False,
            build_id="webhook",
            request_id=self._request_id,
        )

    def _fetch_pr_details(self, org_url: str, repo_id: str, pr_id: int) -> dict[str, Any]:
        """Fetch PR details from ADO REST API (used for flat-comment event payloads)."""
        org = org_url.rstrip("/")
        if repo_id:
            url = f"{org}/_apis/git/repositories/{repo_id}/pullRequests/{pr_id}?api-version=7.0"
        else:
            url = f"{org}/_apis/git/pullRequests/{pr_id}?api-version=7.0"
        credentials = base64.b64encode(f":{self._auth_token}".encode()).decode()
        req = urllib.request.Request(url, headers={"Authorization": f"Basic {credentials}"})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return cast(dict[str, Any], _json.loads(resp.read().decode()))
        except urllib.error.URLError as exc:
            logger.error("Failed to fetch PR details from ADO API: %s", exc)
            return {}

    def _make_authenticated_url(self, url: str) -> str:
        if url.startswith("https://"):
            # ADO remote URLs often contain the org name as a username
            # (e.g. https://OrgName@dev.azure.com/...). Strip it before
            # inserting the PAT to avoid an invalid double-@ URL.
            if "@" in url[len("https://"):]:
                url = "https://" + url.split("@", 1)[1]
            return url.replace("https://", f"https://:{self._auth_token}@", 1)
        return url

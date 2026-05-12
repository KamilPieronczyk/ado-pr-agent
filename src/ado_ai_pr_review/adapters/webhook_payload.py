from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    pull_request_id: int | None = Field(default=None, alias="pullRequestId")
    source_ref_name: str | None = Field(default=None, alias="sourceRefName")
    target_ref_name: str | None = Field(default=None, alias="targetRefName")
    repository: _Repository | None = None
    pull_request: _PullRequestResource | None = Field(default=None, alias="pullRequest")
    comment: _Comment | None = None
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
        if self.resource.comment and self.resource.comment.content:
            return self.resource.comment.content
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

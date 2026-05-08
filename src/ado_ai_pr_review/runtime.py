from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from ado_ai_pr_review.errors import ConfigurationError


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigurationError(f"Missing required environment variable: {name}")
    return value


def _optional_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes"}:
        return True
    if normalized in {"0", "false", "no"}:
        return False
    raise ConfigurationError(f"{name} must be one of: 1, true, yes, 0, false, no")


@dataclass(frozen=True)
class RuntimeContext:
    repo_root: Path
    organization_url: str
    project: str
    repository_id: str
    repository_name: str
    pull_request_id: int
    source_branch: str
    target_branch: str
    is_fork: bool
    build_id: str
    system_access_token: str | None

    @classmethod
    def from_env(cls, repo_root: str) -> RuntimeContext:
        pr_id = _required_env("SYSTEM_PULLREQUEST_PULLREQUESTID")
        try:
            pull_request_id = int(pr_id)
        except ValueError as exc:
            raise ConfigurationError("SYSTEM_PULLREQUEST_PULLREQUESTID must be an integer") from exc

        return cls(
            repo_root=Path(repo_root).resolve(),
            organization_url=_required_env("SYSTEM_TEAMFOUNDATIONCOLLECTIONURI"),
            project=_required_env("SYSTEM_TEAMPROJECT"),
            repository_id=_required_env("BUILD_REPOSITORY_ID"),
            repository_name=os.getenv("BUILD_REPOSITORY_NAME", ""),
            pull_request_id=pull_request_id,
            source_branch=os.getenv("SYSTEM_PULLREQUEST_SOURCEBRANCH", ""),
            target_branch=os.getenv("SYSTEM_PULLREQUEST_TARGETBRANCH", ""),
            is_fork=_optional_bool("SYSTEM_PULLREQUEST_ISFORK", False),
            build_id=os.getenv("BUILD_BUILDID", "local"),
            system_access_token=os.getenv("SYSTEM_ACCESSTOKEN"),
        )

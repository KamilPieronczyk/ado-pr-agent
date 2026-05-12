from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AdoContext:
    repo_root: Path
    organization_url: str
    project: str
    repository_id: str
    repository_name: str
    pull_request_id: int
    source_branch: str
    target_branch: str
    is_fork: bool
    run_id: str

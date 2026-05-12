from __future__ import annotations

from pathlib import Path

from ado_ai_pr_review.models import RepoIndexEntry
from ado_ai_pr_review.workspace import WorkspaceBoundary


class RepoIndexer:
    def __init__(self, exclude: list[str]) -> None:
        self._exclude = exclude

    def build(self, repo_root: Path) -> list[RepoIndexEntry]:
        workspace = WorkspaceBoundary(repo_root)
        entries: list[RepoIndexEntry] = []
        for relative_path in workspace.iter_relative_files(exclude=self._exclude):
            relative = relative_path.as_posix()
            language = self._language(relative)
            if language == "unknown":
                continue
            tags = self._tags(relative)
            entries.append(
                RepoIndexEntry(
                    path=relative,
                    language=language,
                    description=f"{language} file at {relative}",
                    tags=tags,
                    relevance=50,
                )
            )
        return entries

    @staticmethod
    def _language(relative: str) -> str:
        suffix = Path(relative).suffix.lower()
        return {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".cs": "csharp",
            ".go": "go",
            ".java": "java",
            ".md": "markdown",
            ".yml": "yaml",
            ".yaml": "yaml",
            ".json": "json",
        }.get(suffix, "unknown")

    @staticmethod
    def _tags(relative: str) -> list[str]:
        lowered = relative.lower()
        tags: set[str] = set()
        if lowered.startswith("tests/") or "/test" in lowered or lowered.endswith("_test.py"):
            tags.add("tests")
        if any(word in lowered for word in ["auth", "login", "secret", "token", "credential"]):
            tags.add("security")
        if any(word in lowered for word in ["controller", "api", "route", "endpoint"]):
            tags.add("api")
        if any(word in lowered for word in ["domain", "entity", "aggregate"]):
            tags.add("domain")
        if lowered.endswith((".yml", ".yaml", ".json")):
            tags.add("config")
        if lowered.endswith(".md"):
            tags.add("docs")
        return sorted(tags)

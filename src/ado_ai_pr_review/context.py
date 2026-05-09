from __future__ import annotations

from pathlib import Path

from ado_ai_pr_review.models import RepoIndexEntry, SelectedContext


class ContextSelector:
    def __init__(self, max_files: int, max_chars_per_file: int = 8_000) -> None:
        self._max_files = max_files
        self._max_chars_per_file = max_chars_per_file

    def select(
        self,
        repo_root: Path,
        guidance_paths: list[str],
        entries: list[RepoIndexEntry],
        prefer_tags: set[str] | None = None,
    ) -> SelectedContext:
        guidance = []
        for relative in guidance_paths:
            path = repo_root / relative
            if path.exists() and path.is_file():
                guidance.append(path.read_text(encoding="utf-8"))

        prefer_tags = prefer_tags or set()
        ranked = sorted(
            entries,
            key=lambda entry: (
                len(prefer_tags.intersection(entry.tags)),
                entry.relevance,
                entry.path,
            ),
            reverse=True,
        )

        dynamic_files: list[str] = []
        for entry in ranked[: self._max_files]:
            path = repo_root / entry.path
            if path.exists() and path.is_file():
                content = path.read_text(encoding="utf-8")
                if len(content) > self._max_chars_per_file:
                    half = self._max_chars_per_file // 2
                    content = (
                        content[:half]
                        + f"\n... [truncated: {len(content)} chars total, showing first and last {half}] ...\n"
                        + content[-half:]
                    )
                dynamic_files.append(f"{entry.path}\n{content}")

        return SelectedContext(always_on_guidance=guidance, dynamic_files=dynamic_files)

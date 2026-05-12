from __future__ import annotations

import logging
from pathlib import Path

from ado_ai_pr_review.errors import WorkspaceBoundaryError
from ado_ai_pr_review.models import RepoIndexEntry, SelectedContext
from ado_ai_pr_review.workspace import WorkspaceBoundary

logger = logging.getLogger(__name__)


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
        workspace = WorkspaceBoundary(repo_root)

        guidance = []
        for relative in guidance_paths:
            try:
                content = workspace.safe_read_text(relative)
                guidance.append(content)
            except WorkspaceBoundaryError as exc:
                logger.warning("Skipping guidance file outside workspace: %s (%s)", relative, exc)
            except FileNotFoundError:
                logger.warning("Skipping missing guidance file: %s", relative)

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
            try:
                content = workspace.safe_read_text(entry.path)
            except WorkspaceBoundaryError as exc:
                logger.debug("Skipping dynamic file outside workspace: %s (%s)", entry.path, exc)
                continue
            except FileNotFoundError:
                logger.debug("Skipping missing dynamic file: %s", entry.path)
                continue
            if len(content) > self._max_chars_per_file:
                half = self._max_chars_per_file // 2
                content = (
                    content[:half]
                    + f"\n... [truncated: {len(content)} chars total, showing first and last {half}] ...\n"
                    + content[-half:]
                )
            dynamic_files.append(f"{entry.path}\n{content}")

        return SelectedContext(always_on_guidance=guidance, dynamic_files=dynamic_files)

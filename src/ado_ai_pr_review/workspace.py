from __future__ import annotations

import os
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

from ado_ai_pr_review.errors import WorkspaceBoundaryError


@dataclass(frozen=True)
class WorkspaceBoundary:
    root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", self.root.resolve())

    def safe_read_text(self, relative_path: str, *, max_chars: int | None = None) -> str:
        path = self.resolve_existing_file(relative_path)
        content = path.read_text(encoding="utf-8")
        if max_chars is not None:
            return content[:max_chars]
        return content

    def safe_write_text(self, relative_path: str, content: str) -> Path:
        path = self.resolve_write_path(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def resolve_existing_file(self, relative_path: str) -> Path:
        path = self._candidate_path(relative_path)
        if path.is_symlink():
            raise WorkspaceBoundaryError(f"Refusing to read symlink inside workspace: {relative_path}")
        resolved = path.resolve()
        self._require_inside(resolved, relative_path)
        if not resolved.is_file():
            raise WorkspaceBoundaryError(f"Path is not a file inside workspace: {relative_path}")
        return resolved

    def resolve_write_path(self, relative_path: str) -> Path:
        path = self._candidate_path(relative_path)
        self._reject_symlink_ancestors(path, relative_path)
        if path.is_symlink():
            raise WorkspaceBoundaryError(f"Refusing to write through symlink inside workspace: {relative_path}")
        resolved = path.resolve(strict=False)
        self._require_inside(resolved, relative_path)
        return resolved

    def require_cwd(self, cwd: Path) -> Path:
        resolved = cwd.resolve()
        self._require_inside(resolved, str(cwd))
        if not resolved.is_dir():
            raise WorkspaceBoundaryError(f"cwd is not a directory inside workspace: {cwd}")
        return resolved

    def iter_relative_files(self, exclude: list[str]) -> Iterator[Path]:
        for path in self.root.rglob("*"):
            if path.is_symlink() or not path.is_file():
                continue
            resolved = path.resolve()
            try:
                self._require_inside(resolved, str(path))
            except WorkspaceBoundaryError:
                continue
            relative = resolved.relative_to(self.root)
            relative_posix = relative.as_posix()
            if any(fnmatch(relative_posix, pattern) for pattern in exclude):
                continue
            yield relative

    def _candidate_path(self, requested_path: str) -> Path:
        path = Path(requested_path)
        if path.is_absolute():
            self._reject_absolute_parent_escape(path, requested_path)
        else:
            self._reject_relative_parent_escape(path, requested_path)
            path = self.root / path
        return path

    def _reject_relative_parent_escape(self, path: Path, requested_path: str) -> None:
        depth = 0
        for part in path.parts:
            if part in ("", "."):
                continue
            if part == "..":
                depth -= 1
                if depth < 0:
                    raise WorkspaceBoundaryError(f"Path escapes outside workspace: {requested_path}")
                continue
            depth += 1

    def _reject_absolute_parent_escape(self, path: Path, requested_path: str) -> None:
        root_parts = self.root.parts
        if path.parts[: len(root_parts)] != root_parts:
            raise WorkspaceBoundaryError(f"Path escapes outside workspace: {requested_path}")

        if ".." not in path.parts:
            return

        current_parts: list[str] = []
        entered_workspace = False

        for part in path.parts:
            if part in ("", "."):
                continue
            if part == "..":
                if len(current_parts) > 1:
                    current_parts.pop()
            else:
                current_parts.append(part)

            current = tuple(current_parts)
            if self._is_under_root_parts(current, root_parts):
                entered_workspace = True
                continue
            if entered_workspace:
                raise WorkspaceBoundaryError(f"Path escapes outside workspace: {requested_path}")

    def _is_under_root_parts(self, path_parts: tuple[str, ...], root_parts: tuple[str, ...]) -> bool:
        return len(path_parts) >= len(root_parts) and path_parts[: len(root_parts)] == root_parts

    def _require_inside(self, path: Path, requested_path: str) -> None:
        if not path.is_relative_to(self.root):
            raise WorkspaceBoundaryError(f"Path escapes outside workspace: {requested_path}")

    def _reject_symlink_ancestors(self, path: Path, requested_path: str) -> None:
        parent = path.parent
        ancestors = [parent, *parent.parents]
        for ancestor in ancestors:
            if ancestor == self.root.parent:
                break
            if ancestor.is_symlink():
                raise WorkspaceBoundaryError(
                    f"Refusing to write below symlink parent inside workspace: {requested_path}"
                )


@dataclass(frozen=True)
class ProcessContext:
    workspace: WorkspaceBoundary
    request_id: str
    base_env: Mapping[str, str]

    @classmethod
    def from_current_env(cls, workspace: WorkspaceBoundary, request_id: str) -> ProcessContext:
        return cls(workspace=workspace, request_id=request_id, base_env=dict(os.environ))

    def require_cwd(self, cwd: Path) -> Path:
        return self.workspace.require_cwd(cwd)

    def build_env(self, overrides: Mapping[str, str] | None = None) -> dict[str, str]:
        env = dict(self.base_env)
        if overrides:
            env.update(overrides)
        env.setdefault("GIT_TERMINAL_PROMPT", "0")
        env["ADO_AI_REQUEST_ID"] = self.request_id
        return env

from __future__ import annotations

from pathlib import Path

import pytest

from ado_ai_pr_review.errors import WorkspaceBoundaryError
from ado_ai_pr_review.workspace import ProcessContext, WorkspaceBoundary


def test_workspace_reads_relative_file_inside_root(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('ok')\n", encoding="utf-8")

    workspace = WorkspaceBoundary(tmp_path)

    assert workspace.safe_read_text("src/app.py") == "print('ok')\n"


def test_workspace_reads_absolute_file_inside_root(tmp_path: Path) -> None:
    file_path = tmp_path / "app.py"
    file_path.write_text("print('ok')\n", encoding="utf-8")
    workspace = WorkspaceBoundary(tmp_path)

    assert workspace.safe_read_text(str(file_path)) == "print('ok')\n"


def test_workspace_rejects_parent_traversal(tmp_path: Path) -> None:
    workspace = WorkspaceBoundary(tmp_path)

    with pytest.raises(WorkspaceBoundaryError, match="outside workspace"):
        workspace.safe_read_text("../other-repo/secret.py")


def test_workspace_rejects_parent_traversal_that_returns_inside_root(tmp_path: Path) -> None:
    (tmp_path / "file.txt").write_text("secret", encoding="utf-8")
    workspace = WorkspaceBoundary(tmp_path)

    with pytest.raises(WorkspaceBoundaryError, match="outside workspace"):
        workspace.safe_read_text(f"../{tmp_path.name}/file.txt")


def test_workspace_rejects_write_parent_traversal_that_returns_inside_root(tmp_path: Path) -> None:
    workspace = WorkspaceBoundary(tmp_path)

    with pytest.raises(WorkspaceBoundaryError, match="outside workspace"):
        workspace.safe_write_text(f"../{tmp_path.name}/file.txt", "secret")


def test_workspace_rejects_absolute_parent_traversal_that_returns_inside_root(
    tmp_path: Path,
) -> None:
    (tmp_path / "file.txt").write_text("secret", encoding="utf-8")
    workspace = WorkspaceBoundary(tmp_path)
    path = tmp_path / ".." / tmp_path.name / "file.txt"

    with pytest.raises(WorkspaceBoundaryError, match="outside workspace"):
        workspace.safe_read_text(str(path))


def test_workspace_rejects_absolute_write_parent_traversal_that_returns_inside_root(
    tmp_path: Path,
) -> None:
    workspace = WorkspaceBoundary(tmp_path)
    path = tmp_path / ".." / tmp_path.name / "file.txt"

    with pytest.raises(WorkspaceBoundaryError, match="outside workspace"):
        workspace.safe_write_text(str(path), "secret")


def test_workspace_rejects_absolute_path_outside_root(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    workspace = WorkspaceBoundary(tmp_path)

    with pytest.raises(WorkspaceBoundaryError, match="outside workspace"):
        workspace.safe_read_text(str(outside))


def test_workspace_rejects_absolute_write_path_outside_root(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.txt"
    workspace = WorkspaceBoundary(tmp_path)

    with pytest.raises(WorkspaceBoundaryError, match="outside workspace"):
        workspace.safe_write_text(str(outside), "secret")


def test_workspace_rejects_symlink_to_outside_root(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-secret.txt"
    outside.write_text("secret", encoding="utf-8")
    link = tmp_path / "link.txt"
    link.symlink_to(outside)
    workspace = WorkspaceBoundary(tmp_path)

    with pytest.raises(WorkspaceBoundaryError, match="symlink"):
        workspace.safe_read_text("link.txt")


def test_process_context_builds_env_and_validates_cwd(tmp_path: Path) -> None:
    workspace = WorkspaceBoundary(tmp_path)
    process = ProcessContext(workspace=workspace, request_id="req-1", base_env={"PATH": "/bin"})

    env = process.build_env({"CUSTOM": "yes"})

    assert env["PATH"] == "/bin"
    assert env["CUSTOM"] == "yes"
    assert env["ADO_AI_REQUEST_ID"] == "req-1"
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    assert process.require_cwd(tmp_path) == tmp_path.resolve()

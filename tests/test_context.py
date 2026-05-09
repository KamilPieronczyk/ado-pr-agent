from pathlib import Path

from ado_ai_pr_review.context import ContextSelector
from ado_ai_pr_review.models import RepoIndexEntry


def test_context_selector_loads_guidance_and_relevant_files(tmp_path: Path) -> None:
    (tmp_path / ".ado-ai-review").mkdir()
    guidance = tmp_path / ".ado-ai-review" / "reviewer.md"
    guidance.write_text("Review carefully.\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('hello')\n", encoding="utf-8")

    selected = ContextSelector(max_files=1).select(
        repo_root=tmp_path,
        guidance_paths=[".ado-ai-review/reviewer.md"],
        entries=[
            RepoIndexEntry(
                path="src/app.py",
                language="python",
                description="Application entrypoint.",
                tags=["api"],
                relevance=90,
            )
        ],
    )

    assert selected.always_on_guidance == ["Review carefully.\n"]
    assert selected.dynamic_files == ["src/app.py\nprint('hello')\n"]


def test_context_selector_truncates_large_files(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    large_file = tmp_path / "src" / "big.py"
    large_file.write_text("x" * 20_000, encoding="utf-8")

    selected = ContextSelector(max_files=1, max_chars_per_file=100).select(
        repo_root=tmp_path,
        guidance_paths=[],
        entries=[
            RepoIndexEntry(
                path="src/big.py",
                language="python",
                description="Big file.",
                tags=[],
                relevance=90,
            )
        ],
    )

    assert len(selected.dynamic_files) == 1
    content = selected.dynamic_files[0]
    assert "truncated" in content
    assert len(content) < 300  # well under 20k

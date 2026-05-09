from pathlib import Path

from ado_ai_pr_review.indexer import RepoIndexer


def test_repo_indexer_tags_test_and_security_files(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "auth.py").write_text("def login(): pass\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_auth.py").write_text("def test_login(): pass\n", encoding="utf-8")

    entries = RepoIndexer(exclude=[]).build(tmp_path)

    auth = next(entry for entry in entries if entry.path == "src/auth.py")
    test = next(entry for entry in entries if entry.path == "tests/test_auth.py")
    assert "security" in auth.tags
    assert "tests" in test.tags

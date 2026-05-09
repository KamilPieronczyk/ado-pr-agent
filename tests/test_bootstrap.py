from pathlib import Path

from ado_ai_pr_review.bootstrap import Bootstrapper


def test_bootstrapper_creates_missing_files_without_overwriting(tmp_path: Path) -> None:
    existing = tmp_path / ".ado-ai-review" / "instructions"
    existing.mkdir(parents=True)
    reviewer = existing / "reviewer.md"
    reviewer.write_text("custom reviewer guidance\n", encoding="utf-8")

    created = Bootstrapper().create_missing_files(tmp_path)

    assert ".ado-ai-review.yml" in created
    assert ".ado-ai-review/instructions/security.md" in created
    assert reviewer.read_text(encoding="utf-8") == "custom reviewer guidance\n"


def test_bootstrapper_returns_empty_list_when_all_files_exist(tmp_path: Path) -> None:
    bootstrapper = Bootstrapper()

    bootstrapper.create_missing_files(tmp_path)
    created = bootstrapper.create_missing_files(tmp_path)

    assert created == []

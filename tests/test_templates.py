import yaml

from ado_ai_pr_review.templates import BOOTSTRAP_FILES

EXPECTED_KEYS = {
    ".ado-ai-review.yml",
    ".ado-ai-review/instructions/reviewer.md",
    ".ado-ai-review/instructions/security.md",
    ".ado-ai-review/instructions/indexer.md",
    ".ado-ai-review/instructions/fixer.md",
    ".ado-ai-review/guidelines/code-style.md",
    ".ado-ai-review/guidelines/security.md",
}


def test_bootstrap_files_has_all_expected_keys() -> None:
    assert BOOTSTRAP_FILES.keys() == EXPECTED_KEYS


def test_bootstrap_files_all_non_empty() -> None:
    for path, content in BOOTSTRAP_FILES.items():
        assert isinstance(content, str), f"{path!r}: expected str"
        assert len(content) > 50, f"{path!r}: content too short ({len(content)} chars)"


def test_bootstrap_config_is_valid_yaml() -> None:
    data = yaml.safe_load(BOOTSTRAP_FILES[".ado-ai-review.yml"])
    assert data["version"] == 1
    assert "instructions" in data
    assert "reviewer" in data["instructions"]


def test_bootstrap_instruction_files_have_headings() -> None:
    instruction_keys = [k for k in BOOTSTRAP_FILES if "/instructions/" in k]
    for key in instruction_keys:
        assert BOOTSTRAP_FILES[key].startswith("# "), f"{key!r}: should start with a Markdown H1 heading"

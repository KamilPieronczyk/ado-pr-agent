from __future__ import annotations

from importlib.resources import files

# Anchor to the data package. subdirectories (instructions/, guidelines/) have __init__.py
# so they are valid package anchors too. Using the package name is more explicit than
# files("ado_ai_pr_review") / "data" and works in all deployment modes.
_DATA = files("ado_ai_pr_review.data")


def _read(rel: str) -> str:
    # Traverse one segment at a time to stay compatible with Traversable API,
    # which is required for zip-based installs. str.split("/") handles any depth.
    parts = rel.split("/")
    node = _DATA
    for part in parts:
        node = node / part
    return node.read_text(encoding="utf-8")


BOOTSTRAP_FILES: dict[str, str] = {
    ".ado-ai-review.yml": _read("ado-ai-review.yml"),
    ".ado-ai-review/instructions/reviewer.md": _read("instructions/reviewer.md"),
    ".ado-ai-review/instructions/security.md": _read("instructions/security.md"),
    ".ado-ai-review/instructions/indexer.md": _read("instructions/indexer.md"),
    ".ado-ai-review/instructions/fixer.md": _read("instructions/fixer.md"),
    ".ado-ai-review/guidelines/code-style.md": _read("guidelines/code-style.md"),
    ".ado-ai-review/guidelines/security.md": _read("guidelines/security.md"),
}

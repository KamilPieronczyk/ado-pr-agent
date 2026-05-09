from __future__ import annotations

from pathlib import Path

from ado_ai_pr_review.templates import BOOTSTRAP_FILES


class Bootstrapper:
    def create_missing_files(self, repo_root: Path) -> list[str]:
        created: list[str] = []
        for relative_path, content in BOOTSTRAP_FILES.items():
            path = repo_root / relative_path
            if path.exists():
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            created.append(relative_path)
        return created

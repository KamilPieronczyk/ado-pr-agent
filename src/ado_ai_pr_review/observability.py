from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ReviewMetrics:
    command: str
    pr_id: int
    findings_count: int
    inline_suggestions_count: int
    fix_pr_created: bool
    token_usage: dict[str, int] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "pr_id": self.pr_id,
            "findings_count": self.findings_count,
            "inline_suggestions_count": self.inline_suggestions_count,
            "fix_pr_created": self.fix_pr_created,
            "token_usage": self.token_usage,
        }

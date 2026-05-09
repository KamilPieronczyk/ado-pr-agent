from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ado_ai_pr_review.models import ReviewCommand


@dataclass(frozen=True)
class CommandDecision:
    command: ReviewCommand
    thread_id: int | None
    comment: str | None


class CommandRouter:
    def route(self, threads_payload: dict[str, Any]) -> CommandDecision:
        candidates: list[tuple[str, int, str]] = []
        for thread in threads_payload.get("value", []):
            thread_id = int(thread.get("id", 0))
            published = str(thread.get("publishedDate", ""))
            for comment in thread.get("comments", []):
                content = str(comment.get("content", ""))
                command = self._detect(content)
                if command is not None:
                    candidates.append((published, thread_id, command.value))
        if not candidates:
            return CommandDecision(command=ReviewCommand.ONBOARDING, thread_id=None, comment=None)
        _published, thread_id, command_value = sorted(candidates, key=lambda item: item[0])[-1]
        return CommandDecision(
            command=ReviewCommand(command_value),
            thread_id=thread_id,
            comment=f"/ai {command_value}",
        )

    @staticmethod
    def _detect(content: str) -> ReviewCommand | None:
        lowered = content.lower()
        if "/ai fix" in lowered:
            return ReviewCommand.FIX
        if "/ai security" in lowered:
            return ReviewCommand.SECURITY
        if "/ai review" in lowered:
            return ReviewCommand.REVIEW
        return None

    @staticmethod
    def detect_command(text: str) -> ReviewCommand | None:
        """Public API for detecting a ReviewCommand from a free-text string."""
        return CommandRouter._detect(text)

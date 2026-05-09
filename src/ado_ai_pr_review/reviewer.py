from __future__ import annotations

from ado_ai_pr_review.models import ReviewCommand, ReviewResult
from ado_ai_pr_review.ports import LLMPort

GENERAL_SYSTEM_PROMPT = """You are an Azure DevOps pull request reviewer.
Return only JSON matching the supplied schema.
Prioritize correctness, bug risk, test gaps, readability, and maintainability.
Do not propose business logic rewrites.
Do not include secret values.
"""

SECURITY_SYSTEM_PROMPT = """You are a security reviewer for an Azure DevOps pull request.
Return only JSON matching the supplied schema.
Focus on secrets, injection, authentication, authorization, input validation, unsafe deserialization, and sensitive data handling.
Do not include secret values.
"""


class ReviewOrchestrator:
    def __init__(self, model_client: LLMPort) -> None:
        self._model_client = model_client

    def run(
        self,
        command: ReviewCommand,
        guidance: list[str],
        selected_files: list[str],
        diff_text: str,
        local_security_summary: str,
    ) -> ReviewResult:
        system_prompt = SECURITY_SYSTEM_PROMPT if command is ReviewCommand.SECURITY else GENERAL_SYSTEM_PROMPT
        user_prompt = "\n\n".join(
            [
                "Repository guidance:",
                *guidance,
                "Selected context files:",
                *selected_files,
                "Local security scan:",
                local_security_summary,
                "Pull request diff:",
                diff_text,
            ]
        )
        return self._model_client.review_json(system_prompt=system_prompt, user_prompt=user_prompt)

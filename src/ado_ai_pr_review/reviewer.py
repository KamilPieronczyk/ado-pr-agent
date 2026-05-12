from __future__ import annotations

import json

from ado_ai_pr_review.models import FixPlanResult, ReviewCommand, ReviewResult
from ado_ai_pr_review.ports import LLMPort

GENERAL_SYSTEM_PROMPT = """You are an Azure DevOps pull request reviewer.
Return only JSON matching the supplied schema.
Prioritize correctness, bug risk, test gaps, readability, and maintainability.
Do not propose business logic rewrites.
Do not include secret values.

For each finding set file_path, line_start, and line_end to the affected location.
Set suggested_code ONLY when you have a specific, ready-to-apply replacement for that exact line range.
  suggested_code must contain ONLY the replacement lines (no surrounding context, no full file).
  ADO will replace line_start..line_end with suggested_code when the user clicks Apply.
Leave suggested_code null for concerns, questions, or observations that do not have a clear replacement.
"""

SECURITY_SYSTEM_PROMPT = """You are a security reviewer for an Azure DevOps pull request.
Return only JSON matching the supplied schema.
Focus on secrets, injection, authentication, authorization, input validation, unsafe deserialization, and sensitive data handling.
Do not include secret values.

For each finding set file_path, line_start, and line_end to the affected location.
Set suggested_code ONLY when you have a specific, ready-to-apply replacement for that exact line range.
  suggested_code must contain ONLY the replacement lines (no surrounding context, no full file).
  ADO will replace line_start..line_end with suggested_code when the user clicks Apply.
Leave suggested_code null for concerns or questions that do not have a clear replacement.
"""


def _build_fix_plan_system_prompt() -> str:
    schema_json = json.dumps(FixPlanResult.model_json_schema(), indent=2)
    return (
        "You are a code fixer for an Azure DevOps pull request.\n"
        "Return ONLY raw JSON (no markdown, no prose) matching the schema below.\n"
        "\n"
        "For each fixable issue choose a delivery mode:\n"
        "\n"
        "inline_suggestions — for small, localised changes (1-10 contiguous lines).\n"
        "  replacement_lines: ONLY the new lines that replace line_start..line_end.\n"
        "  Do NOT include surrounding context. Do NOT include the full file.\n"
        "  ADO replaces exactly line_start..line_end with these lines when applied.\n"
        "  severity: required — one of: low, medium, high, critical.\n"
        "\n"
        "fix_branch_changes — for complex, multi-line, or multi-location changes.\n"
        "  full_file_content: THE COMPLETE NEW CONTENT OF THE FILE after the fix.\n"
        "  No ellipsis, no truncation, no '// ... rest of file'.\n"
        "\n"
        "Decision rule: 1-10 contiguous lines changed in one location → inline_suggestions.\n"
        "More lines or changes in multiple locations → fix_branch_changes.\n"
        "\n"
        "Only propose mechanical fixes: formatting, imports, naming, type annotations,\n"
        "simple logic bugs visible in the diff.\n"
        "Do not change business logic, algorithms, or API contracts.\n"
        "Do not include secret values.\n"
        "\n"
        "Schema:\n"
        + schema_json
    )


FIX_PLAN_SYSTEM_PROMPT = _build_fix_plan_system_prompt()

_SYSTEM_PROMPT = {
    ReviewCommand.SECURITY: SECURITY_SYSTEM_PROMPT,
}


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
        system_prompt = _SYSTEM_PROMPT.get(command, GENERAL_SYSTEM_PROMPT)
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

    def fix_plan(
        self,
        guidance: list[str],
        selected_files: list[str],
        diff_text: str,
        local_security_summary: str,
    ) -> FixPlanResult:
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
        return self._model_client.fix_plan_json(
            system_prompt=FIX_PLAN_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )

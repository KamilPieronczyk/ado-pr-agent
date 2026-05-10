from __future__ import annotations

import copy
import json

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


def _build_fix_schema() -> str:
    """Return a ReviewResult JSON schema where Finding.suggested_code is required (not nullable)."""
    schema = copy.deepcopy(ReviewResult.model_json_schema())
    finding = schema["$defs"]["Finding"]
    # Make suggested_code a required non-null string
    finding["properties"]["suggested_code"] = {"type": "string", "title": "Suggested Code"}
    required: list[str] = finding.setdefault("required", [])
    if "suggested_code" not in required:
        required.append("suggested_code")
    if "file_path" not in required:
        required.append("file_path")
    if "line_start" not in required:
        required.append("line_start")
    if "line_end" not in required:
        required.append("line_end")
    return json.dumps(schema, indent=2)


FIX_SYSTEM_PROMPT = (
    "You are a mechanical code fixer for an Azure DevOps pull request.\n"
    "Return ONLY raw JSON (no markdown, no prose) matching the schema below.\n"
    "Only emit findings with type \"mechanical_fix\".\n"
    "\n"
    "Every finding MUST include suggested_code, file_path, line_start, and line_end.\n"
    "suggested_code = THE COMPLETE NEW CONTENT OF THE FILE after the fix is applied.\n"
    "This is the ENTIRE file, not just the changed lines. The fixer will overwrite the\n"
    "file with this content. No ellipsis, no truncation, no '// ... rest of file'.\n"
    "line_start and line_end indicate which lines you changed (for documentation only).\n"
    "If you cannot provide the full file content, OMIT that finding entirely.\n"
    "\n"
    "Only propose changes from the mechanical fix whitelist in the fixer instructions.\n"
    "Do not change business logic, algorithms, or API contracts.\n"
    "Do not include secret values.\n"
    "\n"
    "Schema (suggested_code, file_path, line_start, line_end are ALL REQUIRED):\n"
    + _build_fix_schema()
)

_SYSTEM_PROMPT = {
    ReviewCommand.SECURITY: SECURITY_SYSTEM_PROMPT,
    ReviewCommand.FIX: FIX_SYSTEM_PROMPT,
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

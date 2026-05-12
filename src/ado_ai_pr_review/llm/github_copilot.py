# src/ado_ai_pr_review/llm/github_copilot.py
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from openai import OpenAI
from pydantic import ValidationError

from ado_ai_pr_review.errors import CommandExecutionError, ModelOutputError
from ado_ai_pr_review.models import FixPlanResult, ReviewResult

_BASE_URL = "https://api.githubcopilot.com"
_DEPLOYMENT = "claude-sonnet-4.6"
# Required by GitHub Copilot API — requests without this header return 403.
_REQUIRED_HEADERS = {"Copilot-Integration-Id": "vscode-chat"}
_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)
_SCHEMA_SUFFIX = (
    "\n\nYou MUST return raw JSON (no markdown fences) matching this exact schema:\n"
    + json.dumps(ReviewResult.model_json_schema(), indent=2)
)
_FIX_PLAN_SCHEMA_SUFFIX = (
    "\n\nYou MUST return raw JSON (no markdown fences) matching this exact schema:\n"
    + json.dumps(FixPlanResult.model_json_schema(), indent=2)
)


def _extract_json(text: str) -> str:
    """Strip optional markdown code fences; Claude in Copilot may emit them."""
    m = _FENCE_RE.match(text.strip())
    return m.group(1) if m else text.strip()


class GitHubCopilotClient:
    def __init__(self) -> None:
        try:
            completed = subprocess.run(
                ["gh", "auth", "token"],
                check=True,
                capture_output=True,
                text=True,
            )
        except (subprocess.CalledProcessError, OSError) as exc:
            raise CommandExecutionError(
                f"gh auth token failed — run 'gh auth login' first: {exc}"
            ) from exc
        token = completed.stdout.strip()
        if not token:
            raise CommandExecutionError(
                "gh auth token returned empty output — run 'gh auth login' first"
            )
        self._client = OpenAI(api_key=token, base_url=_BASE_URL, default_headers=_REQUIRED_HEADERS)

    def review_json(self, system_prompt: str, user_prompt: str) -> ReviewResult:
        # The Copilot API does not honour response_format for Claude models.
        # Embed the schema in the system prompt and strip any markdown fences
        # from the response defensively.
        # If the caller already embedded a schema (detected by the JSON closing brace
        # at the end of the prompt), do NOT append the default suffix — it would
        # override any stricter field requirements (e.g. required suggested_code for FIX).
        suffix = "" if system_prompt.rstrip().endswith("}") else _SCHEMA_SUFFIX
        response = self._client.chat.completions.create(
            model=_DEPLOYMENT,
            messages=[
                {"role": "system", "content": system_prompt + suffix},
                {"role": "user", "content": user_prompt},
            ],
        )
        raw = response.choices[0].message.content or ""
        output_text = _extract_json(raw)
        try:
            return ReviewResult.model_validate(json.loads(output_text))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ModelOutputError(f"Model returned invalid review JSON: {exc}") from exc

    def fix_plan_json(self, system_prompt: str, user_prompt: str) -> FixPlanResult:
        # FIX_PLAN_SYSTEM_PROMPT embeds the schema and ends with "}"; suffix is empty.
        # _FIX_PLAN_SCHEMA_SUFFIX is a fallback for callers that provide a schema-free prompt.
        suffix = "" if system_prompt.rstrip().endswith("}") else _FIX_PLAN_SCHEMA_SUFFIX
        response = self._client.chat.completions.create(
            model=_DEPLOYMENT,
            messages=[
                {"role": "system", "content": system_prompt + suffix},
                {"role": "user", "content": user_prompt},
            ],
        )
        raw = response.choices[0].message.content or ""
        output_text = _extract_json(raw)
        try:
            return FixPlanResult.model_validate(json.loads(output_text))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ModelOutputError(f"Model returned invalid fix plan JSON: {exc}") from exc

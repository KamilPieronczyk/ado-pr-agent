# src/ado_ai_pr_review/llm/github_copilot.py
from __future__ import annotations

import json
from pathlib import Path

from openai import OpenAI
from pydantic import ValidationError

from ado_ai_pr_review.cli_runner import CliRunner
from ado_ai_pr_review.errors import CommandExecutionError, ModelOutputError
from ado_ai_pr_review.models import ReviewResult

_BASE_URL = "https://api.githubcopilot.com"
_DEPLOYMENT = "gpt-4o"


class GitHubCopilotClient:
    def __init__(self, runner: CliRunner) -> None:
        result = runner.run(["gh", "auth", "token"], cwd=Path("."))
        token = result.stdout.strip()
        if not token:
            raise CommandExecutionError(
                "gh auth token returned empty output — run 'gh auth login' first"
            )
        self._client = OpenAI(api_key=token, base_url=_BASE_URL)

    def review_json(self, system_prompt: str, user_prompt: str) -> ReviewResult:
        response = self._client.responses.create(
            model=_DEPLOYMENT,
            instructions=system_prompt,
            input=user_prompt,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "review_result",
                    "schema": ReviewResult.model_json_schema(),
                    "strict": True,
                }
            },
        )
        output_text = str(response.output_text)
        try:
            return ReviewResult.model_validate(json.loads(output_text))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ModelOutputError(f"Model returned invalid review JSON: {exc}") from exc

from __future__ import annotations

import os

from ado_ai_pr_review.llm.azure_openai import ModelClient, build_openai_client
from ado_ai_pr_review.ports import LLMPort


def build_llm(provider: str | None) -> LLMPort:
    if provider == "copilot":
        from ado_ai_pr_review.cli_runner import CliRunner
        from ado_ai_pr_review.llm.github_copilot import GitHubCopilotClient
        from ado_ai_pr_review.tool_policy import CommandPolicy

        runner = CliRunner(policy=CommandPolicy.default())
        return GitHubCopilotClient(runner=runner)
    return ModelClient(
        openai_client=build_openai_client(),  # type: ignore[arg-type]
        deployment=os.environ["AZURE_OPENAI_DEPLOYMENT"],
    )

# tests/test_github_copilot.py
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ado_ai_pr_review.tool_policy import CommandPolicy


def test_command_policy_allows_gh_auth_token() -> None:
    policy = CommandPolicy.default()
    policy.validate(["gh", "auth", "token"])  # must not raise


def test_command_policy_rejects_other_gh_commands() -> None:
    from ado_ai_pr_review.errors import CommandRejectedError
    policy = CommandPolicy.default()
    with pytest.raises(CommandRejectedError):
        policy.validate(["gh", "repo", "clone", "owner/repo"])


def test_github_copilot_client_fetches_token_and_calls_openai(mocker) -> None:  # type: ignore[no-untyped-def]
    from ado_ai_pr_review.cli_runner import CliRunner
    from ado_ai_pr_review.llm.github_copilot import GitHubCopilotClient

    runner = MagicMock(spec=CliRunner)
    runner.run.return_value = MagicMock(stdout="ghu_test_token_12345\n", returncode=0, stderr="", argv=["gh", "auth", "token"])

    openai_mock = mocker.patch("ado_ai_pr_review.llm.github_copilot.OpenAI")
    mock_message = MagicMock()
    mock_message.content = '{"summary":"ok","findings":[]}'
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    openai_mock.return_value.chat.completions.create.return_value.choices = [mock_choice]

    client = GitHubCopilotClient(runner=runner)
    result = client.review_json(system_prompt="system", user_prompt="user")

    assert result.summary == "ok"
    openai_mock.assert_called_once()
    call_kwargs = openai_mock.call_args
    assert call_kwargs.kwargs["api_key"] == "ghu_test_token_12345"
    assert call_kwargs.kwargs["default_headers"] == {"Copilot-Integration-Id": "vscode-chat"}

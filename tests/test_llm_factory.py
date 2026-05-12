import os
import pytest
from unittest.mock import patch, MagicMock


def test_build_llm_returns_azure_openai_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/")

    with patch("ado_ai_pr_review.llm.factory.build_openai_client", return_value=MagicMock()):
        from ado_ai_pr_review.llm.factory import build_llm
        from ado_ai_pr_review.llm.azure_openai import ModelClient
        result = build_llm(None)

    assert isinstance(result, ModelClient)


def test_build_llm_returns_copilot_client(monkeypatch: pytest.MonkeyPatch) -> None:
    with (
        patch("ado_ai_pr_review.cli_runner.CliRunner", return_value=MagicMock()),
        patch("ado_ai_pr_review.llm.github_copilot.GitHubCopilotClient", return_value=MagicMock()) as mock_cls,
    ):
        from ado_ai_pr_review.llm.factory import build_llm
        result = build_llm("copilot")

    mock_cls.assert_called_once()

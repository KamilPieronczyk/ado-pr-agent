from __future__ import annotations

from ado_ai_pr_review.llm import azure_openai


def test_build_openai_client_uses_api_key_when_present(monkeypatch, mocker) -> None:
    monkeypatch.setenv("AZURE_OPENAI_BASE_URL", "https://example.openai.azure.com/openai/v1/")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "api-key")
    openai_cls = mocker.patch("ado_ai_pr_review.llm.azure_openai.OpenAI")

    azure_openai.build_openai_client()

    openai_cls.assert_called_once_with(api_key="api-key", base_url="https://example.openai.azure.com/openai/v1/")


def test_build_openai_client_uses_default_azure_credential_without_api_key(monkeypatch, mocker) -> None:
    monkeypatch.setenv("AZURE_OPENAI_BASE_URL", "https://example.openai.azure.com/openai/v1/")
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    credential_cls = mocker.patch("ado_ai_pr_review.llm.azure_openai.DefaultAzureCredential")
    token_provider = mocker.patch("ado_ai_pr_review.llm.azure_openai.get_bearer_token_provider")
    token_provider.return_value.return_value = "entra-openai-token"
    openai_cls = mocker.patch("ado_ai_pr_review.llm.azure_openai.OpenAI")

    azure_openai.build_openai_client()

    credential_cls.assert_called_once()
    token_provider.assert_called_once_with(credential_cls.return_value, "https://cognitiveservices.azure.com/.default")
    openai_cls.assert_called_once_with(api_key="entra-openai-token", base_url="https://example.openai.azure.com/openai/v1/")

from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from ado_ai_pr_review.adapters.webhook_payload import AdoWebhookPayload
from ado_ai_pr_review.models import ReviewCommand
from ado_ai_pr_review.webhook_server import _process_sync, app

_PR_CREATED_PAYLOAD = {
    "eventType": "git.pullrequest.created",
    "resource": {
        "pullRequestId": 42,
        "sourceRefName": "refs/heads/feature/x",
        "targetRefName": "refs/heads/main",
        "repository": {
            "id": "repo-guid",
            "name": "MyRepo",
            "remoteUrl": "https://dev.azure.com/org/proj/_git/MyRepo",
            "project": {"name": "Proj"},
        },
    },
    "resourceContainers": {"collection": {"baseUrl": "https://dev.azure.com/org/"}},
}


def test_health_returns_ok() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_webhook_returns_accepted_immediately(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AZURE_OPENAI_BASE_URL", "https://example.com/")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "model")

    with patch("ado_ai_pr_review.webhook_server._process_sync"):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/webhook/ado", json=_PR_CREATED_PAYLOAD)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "accepted"
    assert body["request_id"]


def test_webhook_returns_400_on_invalid_payload() -> None:
    client = TestClient(app)
    response = client.post("/webhook/ado", json={"eventType": "unknown", "resource": {}, "resourceContainers": {"collection": {"baseUrl": "https://example.com/"}}})
    assert response.status_code == 422



def _basic_auth_header(username: str, password: str) -> str:
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return f"Basic {token}"


def test_webhook_auth_skipped_when_env_vars_not_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """No WEBHOOK_USERNAME/PASSWORD configured → endpoint passes through (gradual rollout)."""
    monkeypatch.setenv("AZURE_OPENAI_BASE_URL", "https://example.com/")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "model")
    monkeypatch.delenv("WEBHOOK_USERNAME", raising=False)
    monkeypatch.delenv("WEBHOOK_PASSWORD", raising=False)

    with patch("ado_ai_pr_review.webhook_server._process_sync"):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/webhook/ado", json=_PR_CREATED_PAYLOAD)

    assert response.status_code == 200


def test_webhook_auth_accepted_with_correct_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AZURE_OPENAI_BASE_URL", "https://example.com/")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "model")
    monkeypatch.setenv("WEBHOOK_USERNAME", "ado-ai")
    monkeypatch.setenv("WEBHOOK_PASSWORD", "s3cr3t")

    with patch("ado_ai_pr_review.webhook_server._process_sync"):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/webhook/ado",
            json=_PR_CREATED_PAYLOAD,
            headers={"Authorization": _basic_auth_header("ado-ai", "s3cr3t")},
        )

    assert response.status_code == 200


def test_webhook_auth_rejected_when_header_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEBHOOK_USERNAME", "ado-ai")
    monkeypatch.setenv("WEBHOOK_PASSWORD", "s3cr3t")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/webhook/ado", json=_PR_CREATED_PAYLOAD)

    assert response.status_code == 401


def test_webhook_auth_rejected_with_wrong_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEBHOOK_USERNAME", "ado-ai")
    monkeypatch.setenv("WEBHOOK_PASSWORD", "s3cr3t")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/webhook/ado",
        json=_PR_CREATED_PAYLOAD,
        headers={"Authorization": _basic_auth_header("ado-ai", "wrong")},
    )

    assert response.status_code == 401


def test_webhook_auth_rejected_with_wrong_username(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEBHOOK_USERNAME", "ado-ai")
    monkeypatch.setenv("WEBHOOK_PASSWORD", "s3cr3t")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/webhook/ado",
        json=_PR_CREATED_PAYLOAD,
        headers={"Authorization": _basic_auth_header("attacker", "s3cr3t")},
    )

    assert response.status_code == 401


def test_webhook_auth_rejected_with_malformed_base64(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEBHOOK_USERNAME", "ado-ai")
    monkeypatch.setenv("WEBHOOK_PASSWORD", "s3cr3t")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/webhook/ado",
        json=_PR_CREATED_PAYLOAD,
        headers={"Authorization": "Basic !!!not-valid-base64!!!"},
    )

    assert response.status_code == 401


def test_webhook_auth_accepted_with_colon_in_password(monkeypatch: pytest.MonkeyPatch) -> None:
    """partition(':') handles passwords that contain colons."""
    monkeypatch.setenv("AZURE_OPENAI_BASE_URL", "https://example.com/")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "model")
    monkeypatch.setenv("WEBHOOK_USERNAME", "user")
    monkeypatch.setenv("WEBHOOK_PASSWORD", "p:a:s:s")

    with patch("ado_ai_pr_review.webhook_server._process_sync"):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/webhook/ado",
            json=_PR_CREATED_PAYLOAD,
            headers={"Authorization": _basic_auth_header("user", "p:a:s:s")},
        )

    assert response.status_code == 200


def test_webhook_returns_and_passes_request_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AZURE_OPENAI_BASE_URL", "https://example.com/")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "model")

    with patch("ado_ai_pr_review.webhook_server._process_sync") as process:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/webhook/ado", json=_PR_CREATED_PAYLOAD, headers={"X-Request-ID": "external-req-1"})

    assert response.status_code == 200
    assert response.json() == {"status": "accepted", "request_id": "external-req-1"}
    assert process.call_args.args[1] == "external-req-1"


def test_webhook_no_longer_requires_ado_auth_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ADO_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("ADO_AUTH_MODE", raising=False)
    monkeypatch.setenv("AZURE_OPENAI_BASE_URL", "https://example.com/")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "model")

    with patch("ado_ai_pr_review.webhook_server._process_sync"):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/webhook/ado", json=_PR_CREATED_PAYLOAD)

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"


_PARSED_PAYLOAD = AdoWebhookPayload.model_validate(_PR_CREATED_PAYLOAD)


def _make_process_sync_mocks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, command: ReviewCommand
) -> MagicMock:
    """Patches all external dependencies of _process_sync; returns the adapter mock."""
    monkeypatch.setenv("AZURE_OPENAI_BASE_URL", "https://example.com/")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "model")

    adapter_mock = MagicMock()
    engine_mock = MagicMock()
    engine_mock.run.return_value = command

    tmp_mock = MagicMock()
    tmp_mock.return_value.__enter__.return_value = str(tmp_path)
    tmp_mock.return_value.__exit__.return_value = False

    import ado_ai_pr_review.webhook_server as _ws
    monkeypatch.setattr(_ws, "AdoWebhookAdapter", MagicMock(return_value=adapter_mock))
    monkeypatch.setattr(_ws, "ReviewEngine", MagicMock(return_value=engine_mock))
    monkeypatch.setattr(_ws, "build_ado_auth_strategy", MagicMock())
    monkeypatch.setattr(_ws, "build_llm", MagicMock())
    monkeypatch.setattr(_ws.tempfile, "TemporaryDirectory", tmp_mock)

    return adapter_mock


def test_process_sync_creates_config_pr_when_config_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    adapter_mock = _make_process_sync_mocks(monkeypatch, tmp_path, ReviewCommand.REVIEW)

    _process_sync(_PARSED_PAYLOAD, "req-1")

    adapter_mock.create_config_pr.assert_called_once()


def test_process_sync_skips_config_scaffold_when_config_present(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / ".ado-ai-review.yml").write_text("version: 1\n", encoding="utf-8")
    adapter_mock = _make_process_sync_mocks(monkeypatch, tmp_path, ReviewCommand.REVIEW)

    _process_sync(_PARSED_PAYLOAD, "req-1")

    adapter_mock.create_config_pr.assert_not_called()


def test_process_sync_skips_config_scaffold_for_onboarding(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    adapter_mock = _make_process_sync_mocks(monkeypatch, tmp_path, ReviewCommand.ONBOARDING)

    _process_sync(_PARSED_PAYLOAD, "req-1")

    adapter_mock.create_config_pr.assert_not_called()

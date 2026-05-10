from __future__ import annotations

import base64
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from ado_ai_pr_review.webhook_server import app

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
    monkeypatch.setenv("ADO_AUTH_TOKEN", "fake-token")
    monkeypatch.setenv("AZURE_OPENAI_BASE_URL", "https://example.com/")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "model")

    with patch("ado_ai_pr_review.webhook_server._process_sync"):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/webhook/ado", json=_PR_CREATED_PAYLOAD)

    assert response.status_code == 200
    assert response.json() == {"status": "accepted"}


def test_webhook_returns_400_on_invalid_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADO_AUTH_TOKEN", "fake-token")
    client = TestClient(app)
    response = client.post("/webhook/ado", json={"eventType": "unknown", "resource": {}, "resourceContainers": {"collection": {"baseUrl": "https://example.com/"}}})
    assert response.status_code == 422


def test_webhook_returns_401_without_auth_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ADO_AUTH_TOKEN", raising=False)
    client = TestClient(app)
    response = client.post("/webhook/ado", json=_PR_CREATED_PAYLOAD)
    assert response.status_code == 401


def _basic_auth_header(username: str, password: str) -> str:
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return f"Basic {token}"


def test_webhook_auth_skipped_when_env_vars_not_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """No WEBHOOK_USERNAME/PASSWORD configured → endpoint passes through (gradual rollout)."""
    monkeypatch.setenv("ADO_AUTH_TOKEN", "fake-token")
    monkeypatch.setenv("AZURE_OPENAI_BASE_URL", "https://example.com/")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "model")
    monkeypatch.delenv("WEBHOOK_USERNAME", raising=False)
    monkeypatch.delenv("WEBHOOK_PASSWORD", raising=False)

    with patch("ado_ai_pr_review.webhook_server._process_sync"):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/webhook/ado", json=_PR_CREATED_PAYLOAD)

    assert response.status_code == 200


def test_webhook_auth_accepted_with_correct_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADO_AUTH_TOKEN", "fake-token")
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
    monkeypatch.setenv("ADO_AUTH_TOKEN", "fake-token")
    monkeypatch.setenv("WEBHOOK_USERNAME", "ado-ai")
    monkeypatch.setenv("WEBHOOK_PASSWORD", "s3cr3t")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/webhook/ado", json=_PR_CREATED_PAYLOAD)

    assert response.status_code == 401


def test_webhook_auth_rejected_with_wrong_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADO_AUTH_TOKEN", "fake-token")
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
    monkeypatch.setenv("ADO_AUTH_TOKEN", "fake-token")
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
    monkeypatch.setenv("ADO_AUTH_TOKEN", "fake-token")
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
    monkeypatch.setenv("ADO_AUTH_TOKEN", "fake-token")
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

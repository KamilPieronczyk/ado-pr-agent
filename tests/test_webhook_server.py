from __future__ import annotations

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

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from ado_ai_pr_review.ado_rest import AdoRestClient


class FakeAuth:
    def authorization_header(self) -> tuple[str, str]:
        return ("Authorization", "Bearer entra-token")

    def git_env(self) -> dict[str, str]:
        return {}

    def secret_values(self) -> tuple[str, ...]:
        return ("entra-token",)


def test_rest_client_sets_authorization_header() -> None:
    client = AdoRestClient(auth=FakeAuth())
    captured = {}

    class FakeResponse:
        def read(self): return json.dumps({"ok": True}).encode()
        def __enter__(self): return self
        def __exit__(self, *_): pass

    def fake_urlopen(request, timeout):
        captured["headers"] = dict(request.headers)
        captured["method"] = request.method
        return FakeResponse()

    with patch("ado_ai_pr_review.ado_rest.urllib.request.urlopen", fake_urlopen):
        result = client.request_json(method="GET", url="https://dev.azure.com/acme/test")

    assert result == {"ok": True}
    assert captured["headers"].get("Authorization") == "Bearer entra-token"
    assert captured["method"] == "GET"


def test_rest_client_encodes_json_body() -> None:
    client = AdoRestClient(auth=FakeAuth())
    captured = {}

    class FakeResponse:
        def read(self): return b"{}"
        def __enter__(self): return self
        def __exit__(self, *_): pass

    def fake_urlopen(request, timeout):
        captured["data"] = request.data
        captured["headers"] = dict(request.headers)
        return FakeResponse()

    with patch("ado_ai_pr_review.ado_rest.urllib.request.urlopen", fake_urlopen):
        client.request_json(method="POST", url="https://dev.azure.com/acme/test", body={"key": "value"})

    assert json.loads(captured["data"]) == {"key": "value"}
    assert captured["headers"].get("Content-type") == "application/json"

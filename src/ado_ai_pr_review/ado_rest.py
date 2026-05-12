from __future__ import annotations

import json
import urllib.request
from collections.abc import Mapping
from typing import Any, cast

from ado_ai_pr_review.auth import AdoAuthStrategy


class AdoRestClient:
    def __init__(self, auth: AdoAuthStrategy, timeout_seconds: int = 15) -> None:
        self._auth = auth
        self._timeout_seconds = timeout_seconds

    def request_json(self, *, method: str, url: str, body: Mapping[str, object] | None = None) -> object:
        auth_name, auth_value = self._auth.authorization_header()
        headers = {"Accept": "application/json", auth_name: auth_value}
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
            return cast(Any, json.loads(response.read().decode("utf-8")))

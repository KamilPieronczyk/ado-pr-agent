from __future__ import annotations

import base64
import os
from collections.abc import Mapping
from typing import Protocol

from azure.core.credentials import TokenCredential
from azure.identity import DefaultAzureCredential

from ado_ai_pr_review.errors import ConfigurationError

AZURE_DEVOPS_SCOPE = "499b84ac-1321-427f-aa17-267ca6975798/.default"


class AdoAuthStrategy(Protocol):
    def authorization_header(self) -> tuple[str, str]: ...
    def git_env(self) -> dict[str, str]: ...
    def secret_values(self) -> tuple[str, ...]: ...


class EntraAdoAuthStrategy:
    def __init__(self, credential: TokenCredential | None = None) -> None:
        self._credential = credential or DefaultAzureCredential()

    def _token(self) -> str:
        return self._credential.get_token(AZURE_DEVOPS_SCOPE).token

    def authorization_header(self) -> tuple[str, str]:
        token = self._token()
        return ("Authorization", f"Bearer {token}")

    def git_env(self) -> dict[str, str]:
        token = self._token()
        return {
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "http.extraheader",
            "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: bearer {token}",
        }

    def secret_values(self) -> tuple[str, ...]:
        return (self._token(),)


class PatAdoAuthStrategy:
    def __init__(self, token: str) -> None:
        if not token.strip():
            raise ConfigurationError("ADO_PAT must be set when ADO_AUTH_MODE=pat")
        self._pat = token.strip()

    def _encoded_credential(self) -> str:
        return base64.b64encode(f":{self._pat}".encode("utf-8")).decode("ascii")

    def authorization_header(self) -> tuple[str, str]:
        return ("Authorization", f"Basic {self._encoded_credential()}")

    def git_env(self) -> dict[str, str]:
        return {
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "http.extraheader",
            "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {self._encoded_credential()}",
        }

    def secret_values(self) -> tuple[str, ...]:
        return (self._pat,)


def build_ado_auth_strategy(env: Mapping[str, str] | None = None, credential: TokenCredential | None = None) -> AdoAuthStrategy:
    source = env if env is not None else os.environ
    mode = source.get("ADO_AUTH_MODE", "entra").strip().lower()
    if mode == "entra":
        return EntraAdoAuthStrategy(credential=credential)
    if mode == "pat":
        return PatAdoAuthStrategy(source.get("ADO_PAT", ""))
    raise ConfigurationError("ADO_AUTH_MODE must be one of: entra, pat")

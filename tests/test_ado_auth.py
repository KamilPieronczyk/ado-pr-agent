from __future__ import annotations

import pytest

from ado_ai_pr_review.auth.ado import EntraAdoAuthStrategy, PatAdoAuthStrategy, build_ado_auth_strategy
from ado_ai_pr_review.errors import ConfigurationError


class FakeCredential:
    def get_token(self, scope: str):
        assert scope == "499b84ac-1321-427f-aa17-267ca6975798/.default"

        class Token:
            token = "entra-token"

        return Token()


def test_default_auth_strategy_is_entra() -> None:
    strategy = build_ado_auth_strategy(env={}, credential=FakeCredential())

    assert isinstance(strategy, EntraAdoAuthStrategy)
    assert strategy.authorization_header() == ("Authorization", "Bearer entra-token")
    assert strategy.git_env()["GIT_CONFIG_VALUE_0"] == "AUTHORIZATION: bearer entra-token"


def test_pat_requires_explicit_mode() -> None:
    strategy = build_ado_auth_strategy(env={"ADO_AUTH_MODE": "pat", "ADO_PAT": "pat-token"}, credential=FakeCredential())

    assert isinstance(strategy, PatAdoAuthStrategy)
    assert strategy.authorization_header()[1].startswith("Basic ")
    assert strategy.secret_values() == ("pat-token",)


def test_pat_token_is_ignored_without_explicit_mode() -> None:
    strategy = build_ado_auth_strategy(env={"ADO_PAT": "pat-token"}, credential=FakeCredential())

    assert isinstance(strategy, EntraAdoAuthStrategy)


def test_explicit_pat_mode_requires_token() -> None:
    with pytest.raises(ConfigurationError, match="ADO_PAT"):
        build_ado_auth_strategy(env={"ADO_AUTH_MODE": "pat"}, credential=FakeCredential())


def test_unknown_auth_mode_is_rejected() -> None:
    with pytest.raises(ConfigurationError, match="ADO_AUTH_MODE"):
        build_ado_auth_strategy(env={"ADO_AUTH_MODE": "password"}, credential=FakeCredential())

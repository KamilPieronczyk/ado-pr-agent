from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from ado_ai_pr_review.git_toolset import GitToolset


class FakeAuth:
    def authorization_header(self) -> tuple[str, str]:
        return ("Authorization", "Bearer entra-token")

    def git_env(self) -> dict[str, str]:
        return {
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "http.extraheader",
            "GIT_CONFIG_VALUE_0": "AUTHORIZATION: bearer entra-token",
        }

    def secret_values(self) -> tuple[str, ...]:
        return ("entra-token",)


def test_clone_uses_git_extraheader_env_not_token_url(tmp_path: Path) -> None:
    runner = MagicMock()
    toolset = GitToolset(runner=runner, repo_root=tmp_path)
    destination = tmp_path / "work"

    toolset.clone(
        remote_url="https://dev.azure.com/acme/Payments/_git/payments-api",
        branch="feature/auth",
        destination=destination,
        auth_strategy=FakeAuth(),
    )

    argv = runner.run.call_args.args[0]
    env = runner.run.call_args.kwargs["env"]
    assert "entra-token" not in " ".join(argv)
    assert env["GIT_CONFIG_KEY_0"] == "http.extraheader"
    assert env["GIT_CONFIG_VALUE_0"] == "AUTHORIZATION: bearer entra-token"

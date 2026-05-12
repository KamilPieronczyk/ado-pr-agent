from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from pytest_mock import MockerFixture

from ado_ai_pr_review.adapters.webhook import AdoWebhookAdapter
from ado_ai_pr_review.adapters.webhook_payload import AdoWebhookPayload

_PR_CREATED_PAYLOAD = {
    "eventType": "git.pullrequest.created",
    "resource": {
        "pullRequestId": 42,
        "sourceRefName": "refs/heads/feature/my-branch",
        "targetRefName": "refs/heads/main",
        "repository": {
            "id": "repo-guid",
            "name": "MyRepo",
            "remoteUrl": "https://dev.azure.com/org/project/_git/MyRepo",
            "project": {"name": "MyProject"},
        },
    },
    "resourceContainers": {"collection": {"baseUrl": "https://dev.azure.com/org/"}},
}

_COMMENT_PAYLOAD = {
    "eventType": "ms.vss-code.git-pullrequest-comment-event",
    "resource": {
        "pullRequest": {
            "pullRequestId": 42,
            "sourceRefName": "refs/heads/feature/my-branch",
            "targetRefName": "refs/heads/main",
            "repository": {
                "id": "repo-guid",
                "name": "MyRepo",
                "remoteUrl": "https://dev.azure.com/org/project/_git/MyRepo",
                "project": {"name": "MyProject"},
            },
        },
        "comment": {"content": "/ai review"},
    },
    "resourceContainers": {"collection": {"baseUrl": "https://dev.azure.com/org/"}},
}


def test_parse_pr_created_payload() -> None:
    payload = AdoWebhookPayload.model_validate(_PR_CREATED_PAYLOAD)

    assert payload.event_type == "git.pullrequest.created"
    assert payload.pull_request_id == 42
    assert payload.source_ref_name == "refs/heads/feature/my-branch"
    assert payload.target_ref_name == "refs/heads/main"
    assert payload.repository_name == "MyRepo"
    assert payload.remote_url == "https://dev.azure.com/org/project/_git/MyRepo"
    assert payload.project_name == "MyProject"
    assert payload.organization_url == "https://dev.azure.com/org/"
    assert payload.inline_command is None


def test_parse_comment_payload() -> None:
    payload = AdoWebhookPayload.model_validate(_COMMENT_PAYLOAD)

    assert payload.event_type == "ms.vss-code.git-pullrequest-comment-event"
    assert payload.pull_request_id == 42
    assert payload.inline_command == "/ai review"


def test_payload_rejects_missing_pull_request_id() -> None:
    from pydantic import ValidationError

    resource: dict[str, Any] = _PR_CREATED_PAYLOAD["resource"]  # type: ignore[assignment]
    broken = {**_PR_CREATED_PAYLOAD, "resource": {"repository": resource["repository"]}}
    with pytest.raises(ValidationError):
        AdoWebhookPayload.model_validate(broken)


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


def test_webhook_adapter_load_request_clones_with_auth_strategy(mocker: MockerFixture, tmp_path: Path) -> None:
    payload = AdoWebhookPayload.model_validate(_PR_CREATED_PAYLOAD)
    runner_cls = mocker.patch("ado_ai_pr_review.adapters.webhook.CliRunner")
    git_cls = mocker.patch("ado_ai_pr_review.adapters.webhook.GitToolset")
    ado_cls = mocker.patch("ado_ai_pr_review.adapters.webhook.AdoToolset")
    mocker.patch("ado_ai_pr_review.adapters.webhook.AdoRestClient")
    mocker.patch("ado_ai_pr_review.adapters.webhook.SuggestionPublisher")
    git_cls.return_value.diff.return_value = ""
    ado_instance = ado_cls.return_value
    ado_instance.list_pr_threads.return_value = {"value": []}

    adapter = AdoWebhookAdapter(payload=payload, auth_strategy=FakeAuth(), temp_dir=tmp_path)

    # Constructor must be cheap — no clone yet.
    git_cls.return_value.clone.assert_not_called()

    adapter.load_request()

    runner_cls.assert_called_once()
    assert runner_cls.call_args.kwargs["secrets"] == ["entra-token"]
    git_cls.return_value.clone.assert_called_once()
    clone_kwargs = git_cls.return_value.clone.call_args.kwargs
    assert clone_kwargs["remote_url"] == "https://dev.azure.com/org/project/_git/MyRepo"
    assert "entra-token" not in clone_kwargs["remote_url"]


def test_create_config_pr_creates_branch_commits_and_opens_pr(tmp_path: Path) -> None:
    payload = AdoWebhookPayload.model_validate(_PR_CREATED_PAYLOAD)
    adapter = AdoWebhookAdapter(payload=payload, auth_strategy=FakeAuth(), temp_dir=tmp_path)
    git_mock = MagicMock()
    ado_mock = MagicMock()
    adapter._git = git_mock
    adapter._ado = ado_mock
    adapter._target_ref = "refs/heads/main"

    with patch("ado_ai_pr_review.bootstrap.Bootstrapper") as bootstrap_cls:
        bootstrap_cls.return_value.create_missing_files.return_value = [
            ".ado-ai-review.yml",
            ".ado-ai-review/instructions/reviewer.md",
        ]
        result = adapter.create_config_pr()

    assert result is True
    git_mock.checkout_new_branch.assert_called_once_with("ai-config/setup")
    git_mock.add.assert_called_once_with([
        ".ado-ai-review.yml",
        ".ado-ai-review/instructions/reviewer.md",
    ])
    git_mock.commit.assert_called_once()
    git_mock.push.assert_called_once_with("origin", "ai-config/setup")
    pr_call = ado_mock.create_pr.call_args.kwargs
    assert pr_call["source_branch"] == "ai-config/setup"
    assert pr_call["target_branch"] == "main"


def test_create_config_pr_returns_false_before_load_request(tmp_path: Path) -> None:
    payload = AdoWebhookPayload.model_validate(_PR_CREATED_PAYLOAD)
    adapter = AdoWebhookAdapter(payload=payload, auth_strategy=FakeAuth(), temp_dir=tmp_path)

    result = adapter.create_config_pr()

    assert result is False


def test_create_config_pr_returns_false_when_no_files_created(tmp_path: Path) -> None:
    payload = AdoWebhookPayload.model_validate(_PR_CREATED_PAYLOAD)
    adapter = AdoWebhookAdapter(payload=payload, auth_strategy=FakeAuth(), temp_dir=tmp_path)
    adapter._git = MagicMock()
    adapter._ado = MagicMock()
    adapter._target_ref = "refs/heads/main"

    with patch("ado_ai_pr_review.bootstrap.Bootstrapper") as bootstrap_cls:
        bootstrap_cls.return_value.create_missing_files.return_value = []
        result = adapter.create_config_pr()

    assert result is False
    adapter._git.checkout_new_branch.assert_not_called()


def test_create_config_pr_returns_true_when_ado_pr_creation_fails(tmp_path: Path) -> None:
    payload = AdoWebhookPayload.model_validate(_PR_CREATED_PAYLOAD)
    adapter = AdoWebhookAdapter(payload=payload, auth_strategy=FakeAuth(), temp_dir=tmp_path)
    git_mock = MagicMock()
    ado_mock = MagicMock()
    ado_mock.create_pr.side_effect = RuntimeError("TF401349: PR already exists")
    adapter._git = git_mock
    adapter._ado = ado_mock
    adapter._target_ref = "refs/heads/main"

    with patch("ado_ai_pr_review.bootstrap.Bootstrapper") as bootstrap_cls:
        bootstrap_cls.return_value.create_missing_files.return_value = [".ado-ai-review.yml"]
        result = adapter.create_config_pr()

    assert result is True
    git_mock.push.assert_called_once()
    ado_mock.create_pr.assert_called_once()

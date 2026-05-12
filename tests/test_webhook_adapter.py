from __future__ import annotations

from pathlib import Path
from typing import Any

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

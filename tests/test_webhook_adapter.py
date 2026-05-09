from __future__ import annotations

from typing import Any

import pytest

from ado_ai_pr_review.adapters.webhook import AdoWebhookPayload

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

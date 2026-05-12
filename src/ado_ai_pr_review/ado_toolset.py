from __future__ import annotations

import urllib.parse
from collections.abc import Mapping
from typing import Any

from ado_ai_pr_review.ado_context import AdoContext


class AdoToolset:
    def __init__(self, rest_client: Any, context: AdoContext) -> None:
        self._rest = rest_client
        self._context = context

    def _base_pr_url(self) -> str:
        org = self._context.organization_url.rstrip("/")
        project = urllib.parse.quote(self._context.project, safe="")
        repo_id = urllib.parse.quote(self._context.repository_id, safe="")
        pr_id = self._context.pull_request_id
        return f"{org}/{project}/_apis/git/repositories/{repo_id}/pullRequests/{pr_id}"

    def show_pr(self) -> object:
        url = f"{self._base_pr_url()}?api-version=7.1"
        return self._rest.request_json(method="GET", url=url)

    def create_pr(
        self,
        source_branch: str,
        target_branch: str,
        title: str,
        description: str,
    ) -> object:
        org = self._context.organization_url.rstrip("/")
        project = urllib.parse.quote(self._context.project, safe="")
        repo_id = urllib.parse.quote(self._context.repository_id, safe="")
        url = f"{org}/{project}/_apis/git/repositories/{repo_id}/pullRequests?api-version=7.1"
        body = {
            "sourceRefName": f"refs/heads/{source_branch}",
            "targetRefName": f"refs/heads/{target_branch}",
            "title": title,
            "description": description,
        }
        return self._rest.request_json(method="POST", url=url, body=body)

    def list_pr_threads(self) -> object:
        url = f"{self._base_pr_url()}/threads?api-version=7.1"
        return self._rest.request_json(method="GET", url=url)

    def list_iterations(self) -> object:
        url = f"{self._base_pr_url()}/iterations?api-version=7.1"
        return self._rest.request_json(method="GET", url=url)

    def list_iteration_changes(self, iteration_id: int, compare_to: int | None = None) -> object:
        params = {"$top": "5000", "api-version": "7.1"}
        if compare_to is not None:
            params["$compareTo"] = str(compare_to)
        qs = urllib.parse.urlencode(params)
        url = f"{self._base_pr_url()}/iterations/{iteration_id}/changes?{qs}"
        return self._rest.request_json(method="GET", url=url)

    def create_pr_thread(self, body: Mapping[str, object]) -> object:
        url = f"{self._base_pr_url()}/threads?api-version=7.1"
        return self._rest.request_json(method="POST", url=url, body=body)

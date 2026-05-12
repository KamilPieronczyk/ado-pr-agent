from pathlib import Path

from ado_ai_pr_review.ado_context import AdoContext
from ado_ai_pr_review.ado_toolset import AdoToolset


class FakeRest:
    def __init__(self) -> None:
        self.calls = []

    def request_json(self, *, method: str, url: str, body=None):
        self.calls.append((method, url, body))
        return {"ok": True}


def _context(tmp_path: Path) -> AdoContext:
    return AdoContext(
        repo_root=tmp_path,
        organization_url="https://dev.azure.com/acme/",
        project="Payments",
        repository_id="repo-guid",
        repository_name="payments-api",
        pull_request_id=42,
        source_branch="refs/heads/feature",
        target_branch="refs/heads/main",
        is_fork=False,
        run_id="webhook",
    )


def test_ado_toolset_lists_threads_with_rest(tmp_path: Path) -> None:
    rest = FakeRest()
    toolset = AdoToolset(rest_client=rest, context=_context(tmp_path))

    assert toolset.list_pr_threads() == {"ok": True}
    method, url, body = rest.calls[0]
    assert method == "GET"
    assert body is None
    assert url == "https://dev.azure.com/acme/Payments/_apis/git/repositories/repo-guid/pullRequests/42/threads?api-version=7.1"


def test_ado_toolset_creates_thread_via_rest(tmp_path: Path) -> None:
    rest = FakeRest()
    toolset = AdoToolset(rest_client=rest, context=_context(tmp_path))
    thread_body = {"comments": [{"content": "ok"}]}

    toolset.create_pr_thread(body=thread_body)

    method, url, body = rest.calls[0]
    assert method == "POST"
    assert "threads" in url
    assert body == thread_body


def test_ado_toolset_list_iterations(tmp_path: Path) -> None:
    rest = FakeRest()
    toolset = AdoToolset(rest_client=rest, context=_context(tmp_path))

    toolset.list_iterations()

    method, url, _body = rest.calls[0]
    assert method == "GET"
    assert "iterations" in url
    assert "api-version=7.1" in url


def test_ado_toolset_list_iteration_changes(tmp_path: Path) -> None:
    rest = FakeRest()
    toolset = AdoToolset(rest_client=rest, context=_context(tmp_path))

    toolset.list_iteration_changes(iteration_id=3)

    method, url, _body = rest.calls[0]
    assert method == "GET"
    assert "/3/changes" in url
    assert "api-version=7.1" in url


def test_ado_toolset_show_pr(tmp_path: Path) -> None:
    rest = FakeRest()
    toolset = AdoToolset(rest_client=rest, context=_context(tmp_path))

    toolset.show_pr()

    method, url, _body = rest.calls[0]
    assert method == "GET"
    assert "pullRequests/42" in url
    assert "api-version=7.1" in url

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

from pytest_mock import MockerFixture

from ado_ai_pr_review.ado_toolset import AdoToolset
from ado_ai_pr_review.cli_runner import CommandResult
from ado_ai_pr_review.models import Finding, FindingSeverity, FindingType, ReviewResult
from ado_ai_pr_review.publisher import SuggestionPublisher
from ado_ai_pr_review.runtime import RuntimeContext
from ado_ai_pr_review.tool_policy import CommandPolicy


def _context(tmp_path: Path) -> RuntimeContext:
    return RuntimeContext(
        repo_root=tmp_path,
        organization_url="https://dev.azure.com/example-org/",
        project="example-project",
        repository_id="repo123",
        repository_name="example-repo",
        pull_request_id=42,
        source_branch="refs/heads/feature",
        target_branch="refs/heads/main",
        is_fork=False,
        build_id="1001",
        system_access_token="token",
    )


def _result(argv: list[str], stdout: str = '{"ok": true}') -> CommandResult:
    return CommandResult(argv=argv, returncode=0, stdout=stdout, stderr="")


def _called_argv(runner: Mock) -> list[str]:
    argv = runner.run.call_args.args[0]
    assert isinstance(argv, list)
    assert all(isinstance(arg, str) for arg in argv)
    return argv


def test_ado_toolset_lists_threads_with_az_devops_invoke(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    runner = mocker.Mock()
    runner.run.side_effect = lambda argv, **_: _result(argv, '{"count": 1}')
    toolset = AdoToolset(runner=runner, context=_context(tmp_path))

    result = toolset.list_pr_threads()

    argv = _called_argv(runner)
    assert result == {"count": 1}
    assert argv[:5] == ["az", "devops", "invoke", "--area", "git"]
    assert "pullRequestThreads" in argv


def test_ado_toolset_creates_thread_from_json_body(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    runner = mocker.Mock()
    runner.run.side_effect = lambda argv, **_: _result(argv, '{"id": 9}')
    toolset = AdoToolset(runner=runner, context=_context(tmp_path))

    result = toolset.create_pr_thread(body={"comments": [{"content": "Looks good"}]})

    argv = _called_argv(runner)
    assert result == {"id": 9}
    assert "--http-method" in argv
    assert "POST" in argv
    assert "--in-file" in argv


def test_ado_toolset_argv_passes_default_policy_for_list_threads(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    runner = mocker.Mock()
    runner.run.side_effect = lambda argv, **_: _result(argv)
    toolset = AdoToolset(runner=runner, context=_context(tmp_path))

    toolset.list_pr_threads()

    CommandPolicy.default().validate(_called_argv(runner))


def test_ado_toolset_argv_passes_default_policy_for_create_thread(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    runner = mocker.Mock()
    runner.run.side_effect = lambda argv, **_: _result(argv)
    toolset = AdoToolset(runner=runner, context=_context(tmp_path))

    toolset.create_pr_thread(body={"comments": [{"content": "Looks good"}]})

    CommandPolicy.default().validate(_called_argv(runner))


def test_ado_toolset_argv_passes_default_policy_for_show_pr(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    runner = mocker.Mock()
    runner.run.side_effect = lambda argv, **_: _result(argv)
    toolset = AdoToolset(runner=runner, context=_context(tmp_path))

    toolset.show_pr()

    CommandPolicy.default().validate(_called_argv(runner))


def test_ado_toolset_argv_passes_default_policy_for_create_pr(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    runner = mocker.Mock()
    runner.run.side_effect = lambda argv, **_: _result(argv)
    toolset = AdoToolset(runner=runner, context=_context(tmp_path))

    toolset.create_pr(
        source_branch="feature",
        target_branch="main",
        title="Review changes",
        description="Created by test",
    )

    CommandPolicy.default().validate(_called_argv(runner))


def test_ado_toolset_argv_passes_default_policy_for_list_iteration_changes(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    runner = mocker.Mock()
    runner.run.side_effect = lambda argv, **_: _result(argv)
    toolset = AdoToolset(runner=runner, context=_context(tmp_path))

    toolset.list_iteration_changes(iteration_id=3, compare_to=2)

    CommandPolicy.default().validate(_called_argv(runner))


def test_ado_toolset_create_thread_removes_temp_body_file(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    runner = mocker.Mock()
    runner.run.side_effect = lambda argv, **_: _result(argv)
    toolset = AdoToolset(runner=runner, context=_context(tmp_path))

    toolset.create_pr_thread(body={"comments": [{"content": "Looks good"}]})

    argv = _called_argv(runner)
    body_path = Path(argv[argv.index("--in-file") + 1])
    assert not body_path.exists()


def test_publisher_creates_inline_suggestion_thread(mocker: MockerFixture, tmp_path: Path) -> None:
    ado = mocker.Mock()
    publisher = SuggestionPublisher(ado_toolset=ado)
    result = ReviewResult(
        summary="One issue.",
        findings=[
            Finding(
                type=FindingType.BUG_RISK,
                severity=FindingSeverity.HIGH,
                title="Guard missing value",
                body="Handle None before formatting.",
                file_path="src/app.py",
                line_start=10,
                line_end=10,
                suggested_code="if value is None:\n    return None",
            )
        ],
    )

    publisher.publish_review(result)

    body = ado.create_pr_thread.call_args.kwargs["body"]
    assert body["threadContext"]["filePath"] == "src/app.py"
    assert "```suggestion" in body["comments"][0]["content"]

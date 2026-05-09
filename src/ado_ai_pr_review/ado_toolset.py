from __future__ import annotations

import json
import tempfile
from collections.abc import Mapping
from pathlib import Path

from ado_ai_pr_review.cli_runner import CliRunner, CommandResult
from ado_ai_pr_review.runtime import RuntimeContext


class AdoToolset:
    def __init__(self, runner: CliRunner, context: RuntimeContext) -> None:
        self._runner = runner
        self._context = context

    def configure_defaults(self) -> CommandResult:
        return self._runner.run(
            [
                "az",
                "devops",
                "configure",
                "--defaults",
                f"organization={self._context.organization_url}",
                f"project={self._context.project}",
            ],
            cwd=self._context.repo_root,
        )

    def ensure_extension(self) -> CommandResult:
        return self._runner.run(
            ["az", "extension", "add", "--name", "azure-devops", "--only-show-errors"],
            cwd=self._context.repo_root,
            check=False,
        )

    def show_pr(self) -> object:
        return self._run_json(
            [
                "az",
                "repos",
                "pr",
                "show",
                "--id",
                str(self._context.pull_request_id),
                "--organization",
                self._context.organization_url,
                "--project",
                self._context.project,
                "--output",
                "json",
            ],
        )

    def create_pr(
        self,
        source_branch: str,
        target_branch: str,
        title: str,
        description: str,
    ) -> object:
        return self._run_json(
            [
                "az",
                "repos",
                "pr",
                "create",
                "--source-branch",
                source_branch,
                "--target-branch",
                target_branch,
                "--title",
                title,
                "--description",
                description,
                "--repository",
                self._context.repository_id,
                "--organization",
                self._context.organization_url,
                "--project",
                self._context.project,
                "--output",
                "json",
            ],
        )

    def list_pr_threads(self) -> object:
        return self._run_json(self._invoke_args(resource="pullRequestThreads", http_method="GET"))

    def list_iterations(self) -> object:
        return self._run_json(self._invoke_args(resource="pullRequestIterations", http_method="GET"))

    def list_iteration_changes(self, iteration_id: int, compare_to: int | None = None) -> object:
        query_parameters = {"$top": "5000"}
        if compare_to is not None:
            query_parameters["$compareTo"] = str(compare_to)

        return self._run_json(
            self._invoke_args(
                resource="pullRequestIterationChanges",
                http_method="GET",
                route_parameters={"iterationId": str(iteration_id)},
                query_parameters=query_parameters,
            ),
        )

    def create_pr_thread(self, body: Mapping[str, object]) -> object:
        body_path = self._write_temp_body(body)
        try:
            return self._run_json(
                self._invoke_args(
                    resource="pullRequestThreads",
                    http_method="POST",
                    in_file=body_path,
                ),
            )
        finally:
            body_path.unlink(missing_ok=True)

    def _invoke_args(
        self,
        *,
        resource: str,
        http_method: str,
        route_parameters: Mapping[str, str] | None = None,
        query_parameters: Mapping[str, str] | None = None,
        in_file: Path | None = None,
    ) -> list[str]:
        routes = {
            "project": self._context.project,
            "repositoryId": self._context.repository_id,
            "pullRequestId": str(self._context.pull_request_id),
        }
        if route_parameters is not None:
            routes.update(route_parameters)

        argv = [
            "az",
            "devops",
            "invoke",
            "--area",
            "git",
            "--resource",
            resource,
            "--route-parameters",
            *[f"{key}={value}" for key, value in routes.items()],
            "--http-method",
            http_method,
            "--api-version",
            "7.1",
            "--organization",
            self._context.organization_url,
            "--output",
            "json",
        ]

        if query_parameters is not None:
            argv.extend(
                ["--query-parameters", *[f"{key}={value}" for key, value in query_parameters.items()]],
            )
        if in_file is not None:
            argv.extend(["--in-file", str(in_file)])

        return argv

    def _run_json(self, argv: list[str]) -> object:
        result = self._runner.run(argv, cwd=self._context.repo_root)
        return json.loads(result.stdout)

    def _write_temp_body(self, body: Mapping[str, object]) -> Path:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".json",
            prefix=".ado_thread_",
            dir=self._context.repo_root,
            delete=False,
        ) as temp_file:
            json.dump(body, temp_file)
            temp_file.write("\n")
            return Path(temp_file.name)

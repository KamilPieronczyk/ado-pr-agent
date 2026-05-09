from __future__ import annotations

import re
from dataclasses import dataclass

from ado_ai_pr_review.errors import CommandRejectedError

_REMOTE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_SAFE_BRANCH_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*")
_SAFE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_SAFE_REF_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*(?:\.\.\.?[A-Za-z0-9][A-Za-z0-9._/-]*)?")
_INVOKE_RESOURCES = {
    "pullRequestThreads",
    "pullRequestIterations",
    "pullRequestIterationChanges",
}
_INVOKE_ROUTE_KEYS = {"project", "repositoryId", "pullRequestId", "iterationId"}
_INVOKE_QUERY_KEYS = {"$top", "$compareTo"}


def _matches_shape(argv: list[str], shape: tuple[str, ...]) -> bool:
    return len(argv) >= len(shape) and tuple(argv[: len(shape)]) == shape


def _matches_exact(argv: list[str], shape: tuple[str, ...]) -> bool:
    return tuple(argv) == shape


def _is_safe_remote(value: str) -> bool:
    return _REMOTE_RE.fullmatch(value) is not None


def _is_safe_branch(value: str) -> bool:
    return (
        _SAFE_BRANCH_RE.fullmatch(value) is not None
        and not value.startswith(("-", "/"))
        and ".." not in value
        and "://" not in value
        and "\\" not in value
    )


def _is_safe_relative_path(value: str) -> bool:
    return bool(value) and not value.startswith(("/", "-")) and ".." not in value and "\\" not in value


def _is_safe_local_path(value: str) -> bool:
    return bool(value) and not value.startswith("-") and ".." not in value and "\\" not in value


def _is_safe_ref_or_range(value: str) -> bool:
    return (
        _SAFE_REF_RE.fullmatch(value) is not None
        and not value.startswith("-")
        and "://" not in value
        and "\\" not in value
    )


def _is_safe_organization_url(value: str) -> bool:
    return value.startswith(("https://dev.azure.com/", "http://localhost")) and not value.startswith("-")


def _is_nonempty_cli_value(value: str) -> bool:
    return bool(value) and not value.startswith("-")


@dataclass(frozen=True)
class CommandPolicy:
    @classmethod
    def default(cls) -> CommandPolicy:
        return cls()

    def validate(self, argv: list[str]) -> None:
        if not argv:
            raise CommandRejectedError("Command is empty")

        if argv[0] not in {"git", "az"}:
            raise CommandRejectedError("Binary is not allowlisted")

        if argv[0] == "git" and self._is_allowed_git(argv):
            return
        if argv[0] == "az" and self._is_allowed_az(argv):
            return

        raise CommandRejectedError("Command shape is not allowlisted")

    def _is_allowed_git(self, argv: list[str]) -> bool:
        if _matches_exact(argv, ("git", "status")):
            return True
        if _matches_exact(argv, ("git", "status", "--short")):
            return True
        if _matches_shape(argv, ("git", "diff")):
            return _is_allowed_git_diff(argv)
        if len(argv) == 4 and _matches_shape(argv, ("git", "fetch")):
            return _is_safe_remote(argv[2]) and argv[3] == "--prune"
        if len(argv) == 4 and _matches_shape(argv, ("git", "checkout", "-B")):
            return _is_safe_branch(argv[3])
        if len(argv) >= 3 and _matches_shape(argv, ("git", "add")):
            return all(_is_safe_relative_path(path) for path in argv[2:])
        if len(argv) == 4 and _matches_shape(argv, ("git", "commit", "-m")):
            return bool(argv[3])
        if _matches_exact(argv, ("git", "rev-parse", "HEAD")):
            return True
        if len(argv) == 3 and _matches_shape(argv, ("git", "show")):
            return _is_safe_ref_or_range(argv[2])
        if len(argv) == 4 and _matches_shape(argv, ("git", "push")):
            return _is_safe_remote(argv[2]) and _is_safe_branch(argv[3])
        return False

    def _is_allowed_az(self, argv: list[str]) -> bool:
        if _matches_exact(
            argv,
            ("az", "extension", "add", "--name", "azure-devops", "--only-show-errors"),
        ):
            return True
        if _matches_shape(argv, ("az", "devops", "configure", "--defaults")):
            return _is_allowed_az_devops_configure(argv)
        if _matches_shape(argv, ("az", "devops", "invoke")):
            return _is_allowed_az_devops_invoke(argv)
        if _matches_shape(argv, ("az", "repos", "pr")):
            return _is_allowed_az_repos_pr(argv)
        return False


def _is_allowed_git_diff(argv: list[str]) -> bool:
    if len(argv) == 2:
        return True

    for arg in argv[2:]:
        if arg.startswith(("-c", "--config")):
            return False
        if arg.startswith("-"):
            if arg.startswith("--unified=") and arg.removeprefix("--unified=").isdigit():
                continue
            if arg == "--name-status":
                continue
            return False
        if not _is_safe_ref_or_range(arg):
            return False

    return True


def _is_allowed_az_devops_configure(argv: list[str]) -> bool:
    if len(argv) != 6:
        return False

    defaults: dict[str, str] = {}
    for arg in argv[4:]:
        key, separator, value = arg.partition("=")
        if separator != "=" or key in defaults:
            return False
        defaults[key] = value

    return (
        set(defaults) == {"organization", "project"}
        and _is_safe_organization_url(defaults["organization"])
        and _is_nonempty_cli_value(defaults["project"])
    )


def _is_allowed_az_devops_invoke(argv: list[str]) -> bool:
    parsed = _parse_az_devops_invoke(argv[3:])
    if parsed is None:
        return False

    required_flags = {"--area", "--resource", "--route-parameters", "--http-method", "--api-version", "--organization", "--output"}
    if not required_flags.issubset(parsed):
        return False

    resource = parsed["--resource"][0]
    method = parsed["--http-method"][0]
    route_parameters = _parse_key_value_args(parsed["--route-parameters"], _INVOKE_ROUTE_KEYS)
    if route_parameters is None:
        return False

    required_route_keys = {"project", "repositoryId", "pullRequestId"}
    if resource == "pullRequestIterationChanges":
        required_route_keys.add("iterationId")

    if not required_route_keys.issubset(route_parameters):
        return False

    if "--query-parameters" in parsed:
        query_parameters = _parse_key_value_args(parsed["--query-parameters"], _INVOKE_QUERY_KEYS)
        if query_parameters is None or not all(value.isdigit() for value in query_parameters.values()):
            return False

    if "--in-file" in parsed and (
        resource != "pullRequestThreads" or method != "POST" or not _is_safe_local_path(parsed["--in-file"][0])
    ):
        return False

    return (
        parsed["--area"] == ["git"]
        and resource in _INVOKE_RESOURCES
        and method in {"GET", "POST"}
        and (method == "GET" or resource == "pullRequestThreads")
        and parsed["--api-version"] == ["7.1"]
        and _is_safe_organization_url(parsed["--organization"][0])
        and parsed["--output"] == ["json"]
    )


def _parse_az_devops_invoke(argv: list[str]) -> dict[str, list[str]] | None:
    parsed: dict[str, list[str]] = {}
    value_flags = {"--area", "--resource", "--http-method", "--api-version", "--organization", "--output", "--in-file"}
    list_flags = {"--route-parameters", "--query-parameters"}
    index = 0

    while index < len(argv):
        flag = argv[index]
        if flag not in value_flags | list_flags or flag in parsed:
            return None
        index += 1

        values: list[str] = []
        if flag in value_flags:
            if index >= len(argv) or argv[index].startswith("-"):
                return None
            values.append(argv[index])
            index += 1
        else:
            while index < len(argv) and not argv[index].startswith("--"):
                values.append(argv[index])
                index += 1
            if not values:
                return None

        parsed[flag] = values

    return parsed


def _parse_key_value_args(argv: list[str], allowed_keys: set[str]) -> dict[str, str] | None:
    parsed: dict[str, str] = {}
    for arg in argv:
        key, separator, value = arg.partition("=")
        if (
            separator != "="
            or key not in allowed_keys
            or key in parsed
            or not value
            or value.startswith("-")
            or ".." in value
        ):
            return None
        parsed[key] = value
    return parsed


def _is_allowed_az_repos_pr(argv: list[str]) -> bool:
    if len(argv) < 4:
        return False

    if argv[3] == "show":
        return _is_allowed_az_repos_pr_show(argv[4:])
    if argv[3] == "create":
        return _is_allowed_az_repos_pr_create(argv[4:])
    return False


def _parse_single_value_flags(argv: list[str], allowed_flags: set[str]) -> dict[str, str] | None:
    if len(argv) % 2 != 0:
        return None

    parsed: dict[str, str] = {}
    for index in range(0, len(argv), 2):
        flag = argv[index]
        value = argv[index + 1]
        if flag not in allowed_flags or flag in parsed or not _is_nonempty_cli_value(value):
            return None
        parsed[flag] = value

    return parsed


def _is_allowed_az_repos_pr_show(argv: list[str]) -> bool:
    parsed = _parse_single_value_flags(argv, {"--id", "--organization", "--project", "--output"})
    if parsed is None or set(parsed) != {"--id", "--organization", "--project", "--output"}:
        return False

    return (
        parsed["--id"].isdigit()
        and _is_safe_organization_url(parsed["--organization"])
        and parsed["--output"] == "json"
    )


def _is_allowed_az_repos_pr_create(argv: list[str]) -> bool:
    required_flags = {
        "--source-branch",
        "--target-branch",
        "--title",
        "--description",
        "--repository",
        "--organization",
        "--project",
        "--output",
    }
    parsed = _parse_single_value_flags(argv, required_flags)
    if parsed is None or set(parsed) != required_flags:
        return False

    return (
        _is_safe_branch(parsed["--source-branch"])
        and _is_safe_branch(parsed["--target-branch"])
        and _is_nonempty_cli_value(parsed["--title"])
        and _is_nonempty_cli_value(parsed["--description"])
        and _SAFE_ID_RE.fullmatch(parsed["--repository"]) is not None
        and _is_safe_organization_url(parsed["--organization"])
        and parsed["--output"] == "json"
    )

from __future__ import annotations

import re
from dataclasses import dataclass

from ado_ai_pr_review.errors import CommandRejectedError

_REMOTE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_SAFE_BRANCH_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*")
_SAFE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_SAFE_REF_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*(?:\.\.\.?[A-Za-z0-9][A-Za-z0-9._/-]*)?")
_VISUALSTUDIO_RE = re.compile(r"https://[A-Za-z0-9][A-Za-z0-9-]*\.visualstudio\.com/")
_ADO_ORG_PREFIX_RE = re.compile(r"https://[A-Za-z0-9][A-Za-z0-9._-]*@dev\.azure\.com/")
# Matches embedded credentials of the form user:pass@ or :token@ — always unsafe.
_CREDENTIALS_RE = re.compile(r"://[^/]*:[^/]*@")


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


def _is_safe_ado_url(value: str) -> bool:
    if _CREDENTIALS_RE.search(value):
        return False
    return (
        value.startswith("https://dev.azure.com/")
        or bool(_ADO_ORG_PREFIX_RE.match(value))
        or bool(_VISUALSTUDIO_RE.match(value))
    )


def _is_safe_ref_or_range(value: str) -> bool:
    return (
        _SAFE_REF_RE.fullmatch(value) is not None
        and not value.startswith("-")
        and "://" not in value
        and "\\" not in value
    )


@dataclass(frozen=True)
class CommandPolicy:
    @classmethod
    def default(cls) -> CommandPolicy:
        return cls()

    def validate(self, argv: list[str]) -> None:
        if not argv:
            raise CommandRejectedError("Command is empty")

        if argv[0] not in {"git", "gh"}:
            raise CommandRejectedError("Binary is not allowlisted")

        if argv[0] == "git" and self._is_allowed_git(argv):
            return
        if argv[0] == "gh" and self._is_allowed_gh(argv):
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
            return _is_safe_remote(argv[2]) and (argv[3] == "--prune" or _is_safe_branch(argv[3]))
        if len(argv) == 4 and _matches_shape(argv, ("git", "checkout", "-B")):
            return _is_safe_branch(argv[3])
        if len(argv) == 5 and _matches_shape(argv, ("git", "checkout", "-B")):
            return _is_safe_branch(argv[3]) and _is_safe_branch(argv[4])
        if len(argv) >= 3 and _matches_shape(argv, ("git", "add")):
            return all(_is_safe_relative_path(path) for path in argv[2:])
        if len(argv) == 4 and _matches_shape(argv, ("git", "commit", "-m")):
            return bool(argv[3])
        if _matches_exact(argv, ("git", "rev-parse", "HEAD")):
            return True
        if _matches_exact(argv, ("git", "rev-parse", "--abbrev-ref", "HEAD")):
            return True
        if len(argv) == 3 and _matches_shape(argv, ("git", "show")):
            return _is_safe_ref_or_range(argv[2])
        if len(argv) == 4 and _matches_shape(argv, ("git", "push")):
            return _is_safe_remote(argv[2]) and _is_safe_branch(argv[3])
        if len(argv) == 8 and _matches_shape(argv, ("git", "clone", "--depth")):
            return (
                argv[3].isdigit()
                and argv[4] == "--branch"
                and _is_safe_branch(argv[5])
                and _is_safe_ado_url(argv[6])
                and _is_safe_local_path(argv[7])
            )
        return False

    def _is_allowed_gh(self, argv: list[str]) -> bool:
        return _matches_exact(argv, ("gh", "auth", "token"))


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

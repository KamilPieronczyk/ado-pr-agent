import pytest

from ado_ai_pr_review.errors import CommandRejectedError
from ado_ai_pr_review.tool_policy import CommandPolicy


def test_command_policy_rejects_az_devops_invoke_after_rest_refactor() -> None:
    with pytest.raises(CommandRejectedError):
        CommandPolicy.default().validate(["az", "devops", "invoke"])


def test_command_policy_allows_known_git_command() -> None:
    policy = CommandPolicy.default()

    policy.validate(["git", "diff", "--unified=0", "origin/main...HEAD"])


def test_command_policy_rejects_unknown_binary() -> None:
    policy = CommandPolicy.default()

    with pytest.raises(CommandRejectedError, match="Binary is not allowlisted"):
        policy.validate(["bash", "-lc", "echo unsafe"])


@pytest.mark.parametrize(
    "argv",
    [
        ["git", "status"],
        ["git", "status", "--short"],
        ["git", "diff", "--name-status", "origin/main...HEAD"],
        ["git", "fetch", "origin", "--prune"],
        ["git", "checkout", "-B", "review/branch-1"],
        ["git", "add", "src/file.py", "tests/test_file.py"],
        ["git", "commit", "-m", "review changes"],
        ["git", "rev-parse", "HEAD"],
        ["git", "show", "abc1234"],
        ["git", "push", "origin", "review/branch-1"],
    ],
)
def test_command_policy_allows_narrow_command_shapes(argv: list[str]) -> None:
    CommandPolicy.default().validate(argv)


@pytest.mark.parametrize(
    "argv",
    [
        ["git", "status", "--porcelain"],
        ["git", "diff", "-c", "core.sshCommand=ssh -i key", "HEAD"],
        ["git", "diff", "--config=core.sshCommand=unsafe", "HEAD"],
        ["git", "diff", "-U0", "HEAD"],
        ["git", "fetch", "https://example.com/repo.git", "--prune"],
        ["git", "fetch", "origin", "--tags"],
        ["git", "checkout", "main"],
        ["git", "checkout", "-B", "../escape"],
        ["git", "add", "/etc/passwd"],
        ["git", "add", "../outside"],
        ["git", "add", "-A"],
        ["git", "commit", "--amend", "-m", "x"],
        ["git", "push", "origin", "--all"],
        ["git", "rev-parse", "--show-toplevel"],
        ["git", "show", "--format=%x00"],
        ["git", "show", "HEAD:/etc/passwd"],
        ["git", "diff", "HEAD:/etc/passwd"],
        ["git", "config", "user.name"],
        ["git", "switch", "main"],
        ["git", "branch", "--delete", "main"],
    ],
)
def test_command_policy_rejects_unsafe_or_unplanned_shapes(argv: list[str]) -> None:
    with pytest.raises(CommandRejectedError, match="Command shape is not allowlisted"):
        CommandPolicy.default().validate(argv)


def test_command_policy_allows_plain_https_git_clone() -> None:
    CommandPolicy.default().validate([
        "git",
        "clone",
        "--depth",
        "50",
        "--branch",
        "feature/auth",
        "https://dev.azure.com/acme/Payments/_git/payments-api",
        "/tmp/work",
    ])


def test_command_policy_rejects_credential_embedded_clone_url() -> None:
    with pytest.raises(CommandRejectedError):
        CommandPolicy.default().validate([
            "git",
            "clone",
            "--depth",
            "50",
            "--branch",
            "feature/auth",
            "https://:secret@dev.azure.com/acme/Payments/_git/payments-api",
            "/tmp/work",
        ])

import pytest

from ado_ai_pr_review.errors import CommandRejectedError
from ado_ai_pr_review.tool_policy import CommandPolicy

PLANNED_INVOKE_GET_THREADS = [
    "az",
    "devops",
    "invoke",
    "--area",
    "git",
    "--resource",
    "pullRequestThreads",
    "--route-parameters",
    "project=Payments",
    "repositoryId=repo-123",
    "pullRequestId=42",
    "--http-method",
    "GET",
    "--api-version",
    "7.1",
    "--organization",
    "https://dev.azure.com/acme/",
    "--output",
    "json",
]

PLANNED_INVOKE_POST_THREADS = [
    "az",
    "devops",
    "invoke",
    "--area",
    "git",
    "--resource",
    "pullRequestThreads",
    "--route-parameters",
    "project=Payments",
    "repositoryId=repo-123",
    "pullRequestId=42",
    "--http-method",
    "POST",
    "--api-version",
    "7.1",
    "--organization",
    "https://dev.azure.com/acme/",
    "--output",
    "json",
    "--in-file",
    "build/thread-comment.json",
]

PLANNED_PR_SHOW = [
    "az",
    "repos",
    "pr",
    "show",
    "--id",
    "42",
    "--organization",
    "https://dev.azure.com/acme/",
    "--project",
    "Payments",
    "--output",
    "json",
]

PLANNED_PR_CREATE = [
    "az",
    "repos",
    "pr",
    "create",
    "--source-branch",
    "review/branch-1",
    "--target-branch",
    "main",
    "--title",
    "AI review",
    "--description",
    "Automated review changes",
    "--repository",
    "repo-123",
    "--organization",
    "https://dev.azure.com/acme/",
    "--project",
    "Payments",
    "--output",
    "json",
]


def test_command_policy_allows_known_git_command() -> None:
    policy = CommandPolicy.default()

    policy.validate(["git", "diff", "--unified=0", "origin/main...HEAD"])


def test_command_policy_rejects_unknown_binary() -> None:
    policy = CommandPolicy.default()

    with pytest.raises(CommandRejectedError, match="Binary is not allowlisted"):
        policy.validate(["bash", "-lc", "echo unsafe"])


def test_command_policy_rejects_unlisted_az_shape() -> None:
    policy = CommandPolicy.default()

    with pytest.raises(CommandRejectedError, match="Command shape is not allowlisted"):
        policy.validate(["az", "account", "show"])


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
        ["az", "extension", "add", "--name", "azure-devops", "--only-show-errors"],
        [
            "az",
            "devops",
            "configure",
            "--defaults",
            "organization=https://dev.azure.com/acme/",
            "project=Payments",
        ],
        PLANNED_INVOKE_GET_THREADS,
        PLANNED_INVOKE_POST_THREADS,
        PLANNED_PR_SHOW,
        PLANNED_PR_CREATE,
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
        ["az", "extension", "add", "--name", "azure-devops"],
        ["az", "devops", "configure", "--defaults", "organization=https://dev.azure.com/acme/"],
        ["az", "repos", "pr", "delete", "--id", "42"],
        [
            "az",
            "devops",
            "invoke",
            "--area",
            "git",
            "--resource",
            "pullRequestThreads",
            "--route-parameters",
            "project=Payments",
            "repositoryId=repo-123",
            "pullRequestId=42",
            "--http-method",
            "DELETE",
            "--api-version",
            "7.1",
            "--organization",
            "https://dev.azure.com/acme/",
            "--output",
            "json",
        ],
        [
            "az",
            "devops",
            "invoke",
            "--area",
            "git",
            "--resource",
            "repositories",
            "--route-parameters",
            "project=Payments",
            "repositoryId=repo-123",
            "pullRequestId=42",
            "--http-method",
            "GET",
            "--api-version",
            "7.1",
            "--organization",
            "https://dev.azure.com/acme/",
            "--output",
            "json",
        ],
        ["az", "repos", "pr", "update", "--status", "abandoned"],
    ],
)
def test_command_policy_rejects_unsafe_or_unplanned_shapes(argv: list[str]) -> None:
    with pytest.raises(CommandRejectedError, match="Command shape is not allowlisted"):
        CommandPolicy.default().validate(argv)

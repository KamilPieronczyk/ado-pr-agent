from __future__ import annotations

import contextlib
import logging
from pathlib import Path
from typing import Any, cast

from ado_ai_pr_review.ado_context import AdoContext
from ado_ai_pr_review.ado_rest import AdoRestClient
from ado_ai_pr_review.ado_toolset import AdoToolset
from ado_ai_pr_review.adapters.webhook_payload import AdoWebhookPayload
from ado_ai_pr_review.auth import AdoAuthStrategy
from ado_ai_pr_review.cli_runner import CliRunner
from ado_ai_pr_review.commands import CommandRouter
from ado_ai_pr_review.git_toolset import GitToolset
from ado_ai_pr_review.models import FixCandidate, FixPlanResult, ReviewCommand, ReviewResult
from ado_ai_pr_review.publisher import _BOT_MARKER
from ado_ai_pr_review.ports import PRContext, ReviewRequest
from ado_ai_pr_review.publisher import SuggestionPublisher
from ado_ai_pr_review.security import SecurityScanner
from ado_ai_pr_review.tool_policy import CommandPolicy

logger = logging.getLogger(__name__)


class AdoWebhookAdapter:
    def __init__(
        self,
        payload: AdoWebhookPayload,
        auth_strategy: AdoAuthStrategy,
        temp_dir: Path,
        request_id: str = "unknown",
    ) -> None:
        self._payload = payload
        self._auth_strategy = auth_strategy
        self._temp_dir = temp_dir
        self._request_id = request_id
        # These two are cheap (no I/O).
        self._runner = CliRunner(policy=CommandPolicy.default(), secrets=list(auth_strategy.secret_values()))
        self._rest_client = AdoRestClient(auth=auth_strategy)
        # Set after load_request() is called.
        self._git: GitToolset | None = None
        self._ado: AdoToolset | None = None
        self._publisher: SuggestionPublisher | None = None
        self._source_ref: str = ""
        self._target_ref: str = ""

    def load_request(self) -> ReviewRequest:
        payload = self._payload

        # For flat-comment events, fetch PR details to get repo/branch info.
        if payload.is_flat_comment_event:
            org = payload.organization_url.rstrip("/")
            if payload.repository_id:
                url = f"{org}/_apis/git/repositories/{payload.repository_id}/pullRequests/{payload.pull_request_id}?api-version=7.0"
            else:
                url = f"{org}/_apis/git/pullRequests/{payload.pull_request_id}?api-version=7.0"
            try:
                pr_details = cast(dict[str, Any], self._rest_client.request_json(method="GET", url=url))
            except Exception as exc:
                logger.error("Failed to fetch PR details: %s", exc, exc_info=True)
                pr_details = {}
        else:
            pr_details = {}

        self._source_ref = payload.source_ref_name or pr_details.get("sourceRefName", "")
        self._target_ref = payload.target_ref_name or pr_details.get("targetRefName", "")
        repo_info: dict[str, Any] = pr_details.get("repository", {})
        remote_url = payload.remote_url or repo_info.get("remoteUrl", "")
        repo_name = payload.repository_name or repo_info.get("name", "")
        repo_id = payload.repository_id or repo_info.get("id", "")
        project_name = payload.project_name or repo_info.get("project", {}).get("name", "")

        # Clone the source branch.
        source_branch = self._source_ref.removeprefix("refs/heads/")
        self._git = GitToolset(runner=self._runner, repo_root=self._temp_dir)
        self._git.clone(
            remote_url=remote_url,
            branch=source_branch,
            destination=self._temp_dir,
            auth_strategy=self._auth_strategy,
        )

        # Wire up ADO toolset and publisher.
        context = AdoContext(
            repo_root=self._temp_dir,
            organization_url=payload.organization_url,
            project=project_name,
            repository_id=repo_id,
            repository_name=repo_name,
            pull_request_id=payload.pull_request_id,
            source_branch=self._source_ref,
            target_branch=self._target_ref,
            is_fork=False,
            run_id="webhook",
        )
        self._ado = AdoToolset(rest_client=self._rest_client, context=context)
        self._publisher = SuggestionPublisher(ado_toolset=self._ado)

        # Detect command from inline comment or PR threads.
        if payload.inline_command is not None:
            command = CommandRouter.detect_command(payload.inline_command)
            if command is None:
                command = ReviewCommand.SKIP
        else:
            threads = cast(dict[str, Any], self._ado.list_pr_threads())
            decision = CommandRouter().route(threads)
            command = decision.command

        if command in (ReviewCommand.ONBOARDING, ReviewCommand.SKIP):
            return ReviewRequest(
                repo_root=self._temp_dir,
                diff_text="",
                local_findings=(),
                command=command,
                pr_context=self._make_pr_context(),
            )

        target_ref = self._target_ref.removeprefix("refs/heads/")
        # --depth clone uses --single-branch so origin/<target_ref> is absent.
        # Fetch sets FETCH_HEAD to the target tip; use that for the diff range.
        self._git.fetch_branch("origin", target_ref)
        diff_text = self._git.diff("FETCH_HEAD...HEAD", unified=0)
        local_findings, redacted_diff = SecurityScanner().scan_diff(diff_text)

        return ReviewRequest(
            repo_root=self._temp_dir,
            diff_text=redacted_diff,
            local_findings=tuple(local_findings),
            command=command,
            pr_context=self._make_pr_context(),
        )

    def publish_onboarding(self) -> None:
        if self._publisher is not None:
            self._publisher.publish_onboarding()

    def publish_review(self, result: ReviewResult) -> None:
        if self._publisher is not None:
            self._publisher.publish_review(result)

    def publish_fix_result(self, result: FixPlanResult) -> None:
        if self._publisher is not None:
            self._publisher.publish_fix_result(result)

    def publish_error(self, exc: BaseException) -> None:
        logger.error("webhook review failed: %s", exc, exc_info=True)
        if self._ado is not None:
            with contextlib.suppress(Exception):
                self._ado.create_pr_thread(body={
                    "comments": [{
                        "parentCommentId": 0,
                        "content": f"ADO AI review failed: {type(exc).__name__}. Check webhook logs for details.\n\n{_BOT_MARKER}",
                        "commentType": "text",
                    }],
                    "status": "active",
                    "properties": {"adoAiReview.kind": {"$type": "System.String", "$value": "error"}},
                })

    def create_fix_branch(
        self,
        candidates: list[FixCandidate],
        branch_name: str,
        target_branch: str,
    ) -> bool:
        if self._git is None or self._ado is None:
            logger.warning("create_fix_branch called before load_request(); skipping")
            return False
        from ado_ai_pr_review.fixer import MechanicalFixer, MechanicalFixPolicy

        policy = MechanicalFixPolicy()
        fixer = MechanicalFixer(git=self._git, repo_root=self._temp_dir)
        try:
            shas = fixer.apply_commits(candidates, branch_name, policy)
        except RuntimeError as exc:
            logger.warning("fix branch not created: %s", exc)
            return False
        self._git.push("origin", branch_name)
        description = "Mechanical AI fix branch.\n\nCherry-pick commits:\n" + "\n".join(
            f"- `git cherry-pick {sha}`" for sha in shas
        )
        try:
            self._ado.create_pr(
                source_branch=branch_name,
                target_branch=target_branch,
                title="AI mechanical fixes",
                description=description,
            )
        except Exception as exc:
            logger.warning("fix branch pushed but PR creation failed: %s", exc)
        return True

    def create_config_pr(self) -> bool:
        if self._git is None or self._ado is None:
            logger.warning("create_config_pr called before load_request(); skipping")
            return False
        from ado_ai_pr_review.bootstrap import Bootstrapper

        created = Bootstrapper().create_missing_files(self._temp_dir)
        if not created:
            return False

        branch_name = "ai-config/setup"
        source_branch = self._source_ref.removeprefix("refs/heads/")
        target_branch = self._target_ref.removeprefix("refs/heads/")
        self._git.checkout_new_branch(branch_name, start_point=source_branch)
        self._git.add(created)
        self._git.commit("chore: add ADO AI review configuration")
        self._git.push("origin", branch_name)
        description = (
            "This PR adds the ADO AI review configuration (`.ado-ai-review.yml`) "
            "and default instruction and guideline files.\n\n"
            "Generated automatically: an `/ai review` command was received "
            "but no configuration was found in the repository.\n\n"
            "Review and customise the settings before merging."
        )
        try:
            self._ado.create_pr(
                source_branch=branch_name,
                target_branch=target_branch,
                title="chore: add ADO AI review configuration",
                description=description,
            )
        except Exception as exc:
            logger.warning("config branch pushed but PR creation failed: %s", exc)
        return True

    def _make_pr_context(self) -> PRContext:
        return PRContext(
            pr_id=self._payload.pull_request_id,
            source_branch=self._source_ref,
            target_branch=self._target_ref,
            is_fork=False,
            run_id="webhook",
            request_id=self._request_id,
        )

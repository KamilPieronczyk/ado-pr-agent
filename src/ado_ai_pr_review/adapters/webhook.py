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
from ado_ai_pr_review.models import FixCandidate, ReviewCommand, ReviewResult
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
        self._temp_dir = temp_dir
        self._request_id = request_id

        self._runner = CliRunner(policy=CommandPolicy.default(), secrets=list(auth_strategy.secret_values()))
        rest_client = AdoRestClient(auth=auth_strategy)

        # For flat-comment events the payload lacks repo/branch info; fetch via REST.
        if payload.is_flat_comment_event:
            org = payload.organization_url.rstrip("/")
            if payload.repository_id:
                url = f"{org}/_apis/git/repositories/{payload.repository_id}/pullRequests/{payload.pull_request_id}?api-version=7.0"
            else:
                url = f"{org}/_apis/git/pullRequests/{payload.pull_request_id}?api-version=7.0"
            try:
                pr_details = cast(dict[str, Any], rest_client.request_json(method="GET", url=url))
            except Exception as exc:
                logger.error("Failed to fetch PR details: %s", exc, exc_info=True)
                pr_details = {}
        else:
            pr_details = {}

        self._source_ref = payload.source_ref_name or pr_details.get("sourceRefName", "")
        self._target_ref = payload.target_ref_name or pr_details.get("targetRefName", "")
        repo_info: dict[str, Any] = pr_details.get("repository", {})
        self._remote_url = payload.remote_url or repo_info.get("remoteUrl", "")
        self._repo_name = payload.repository_name or repo_info.get("name", "")
        self._repo_id = payload.repository_id or repo_info.get("id", "")
        self._project_name = payload.project_name or repo_info.get("project", {}).get("name", "")

        # Clone the repo branch into temp_dir
        source_branch = self._source_ref.removeprefix("refs/heads/")
        self._git = GitToolset(runner=self._runner, repo_root=temp_dir)
        self._git.clone(
            remote_url=self._remote_url,
            branch=source_branch,
            destination=temp_dir,
            auth_strategy=auth_strategy,
        )

        context = AdoContext(
            repo_root=temp_dir,
            organization_url=payload.organization_url,
            project=self._project_name,
            repository_id=self._repo_id,
            repository_name=self._repo_name,
            pull_request_id=payload.pull_request_id,
            source_branch=self._source_ref,
            target_branch=self._target_ref,
            is_fork=False,
            run_id="webhook",
        )
        self._ado = AdoToolset(rest_client=rest_client, context=context)
        self._publisher = SuggestionPublisher(ado_toolset=self._ado)

    def load_request(self) -> ReviewRequest:
        if self._payload.inline_command is not None:
            command = CommandRouter.detect_command(self._payload.inline_command)
            if command is None:
                # Unrecognised comment (e.g. agent's own reply) — skip silently.
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
        diff_text = self._git.diff(f"origin/{target_ref}...HEAD", unified=0)
        local_findings, redacted_diff = SecurityScanner().scan_diff(diff_text)

        return ReviewRequest(
            repo_root=self._temp_dir,
            diff_text=redacted_diff,
            local_findings=tuple(local_findings),
            command=command,
            pr_context=self._make_pr_context(),
        )

    def publish_onboarding(self) -> None:
        self._publisher.publish_onboarding()

    def publish_review(self, result: ReviewResult) -> None:
        self._publisher.publish_review(result)

    def publish_error(self, exc: BaseException) -> None:
        logger.error("webhook review failed: %s", exc, exc_info=True)
        with contextlib.suppress(Exception):
            self._ado.create_pr_thread(body={
                "comments": [{
                    "parentCommentId": 0,
                    "content": f"ADO AI review failed: {type(exc).__name__}. Check webhook logs for details.",
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
        self._ado.create_pr(
            source_branch=branch_name,
            target_branch=target_branch,
            title="AI mechanical fixes",
            description=description,
        )
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

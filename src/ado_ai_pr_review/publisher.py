from __future__ import annotations

from ado_ai_pr_review.ado_toolset import AdoToolset
from ado_ai_pr_review.models import Finding, FixPlanResult, InlineSuggestion, ReviewResult

_BOT_MARKER = "<!-- ado-ai-pr-review -->"


class SuggestionPublisher:
    def __init__(self, ado_toolset: AdoToolset) -> None:
        self._ado = ado_toolset

    def publish_onboarding(self) -> None:
        self._ado.create_pr_thread(
            body={
                "comments": [
                    {
                        "parentCommentId": 0,
                        "content": f"ADO AI review is available. Comment `/ai review`, `/ai security`, or `/ai fix` to run it.\n\n{_BOT_MARKER}",
                        "commentType": "text",
                    }
                ],
                "status": "active",
                "properties": {"adoAiReview.kind": {"$type": "System.String", "$value": "onboarding"}},
            }
        )

    def publish_review(self, result: ReviewResult) -> None:
        self._ado.create_pr_thread(
            body={
                "comments": [
                    {
                        "parentCommentId": 0,
                        "content": f"ADO AI review summary:\n\n{result.summary}\n\n{_BOT_MARKER}",
                        "commentType": "text",
                    }
                ],
                "status": "active",
                "properties": {"adoAiReview.kind": {"$type": "System.String", "$value": "summary"}},
            }
        )
        for finding in result.findings:
            self._publish_finding(finding)

    def _publish_finding(self, finding: Finding) -> None:
        content = f"**{finding.severity.value.upper()}: {finding.title}**\n\n{finding.body}"

        is_inline = bool(finding.file_path and finding.line_start)
        if finding.suggested_code:
            content = f"{content}\n\n```\n{finding.suggested_code}\n```"
        content = f"{content}\n\n{_BOT_MARKER}"

        comment_type = "codeChange" if is_inline and finding.suggested_code else "text"
        body: dict[str, object] = {
            "comments": [{"parentCommentId": 0, "content": content, "commentType": comment_type}],
            "status": "active",
            "properties": {"adoAiReview.kind": {"$type": "System.String", "$value": "finding"}},
        }
        if is_inline:
            line_end = finding.line_end or finding.line_start
            file_path = finding.file_path if finding.file_path.startswith("/") else f"/{finding.file_path}"
            body["threadContext"] = {
                "filePath": file_path,
                "rightFileStart": {"line": finding.line_start, "offset": 1},
                "rightFileEnd": {"line": line_end, "offset": 1},
            }
        self._ado.create_pr_thread(body=body)

    def publish_fix_result(self, result: FixPlanResult) -> None:
        self._ado.create_pr_thread(
            body={
                "comments": [
                    {
                        "parentCommentId": 0,
                        "content": f"ADO AI fix summary:\n\n{result.summary}\n\n{_BOT_MARKER}",
                        "commentType": "text",
                    }
                ],
                "status": "active",
                "properties": {"adoAiReview.kind": {"$type": "System.String", "$value": "fix-summary"}},
            }
        )
        for suggestion in result.inline_suggestions:
            self._publish_inline_suggestion(suggestion)

    def _publish_inline_suggestion(self, suggestion: InlineSuggestion) -> None:
        content = (
            f"**{suggestion.severity.value.upper()}: {suggestion.title}**\n\n"
            f"{suggestion.body}\n\n"
            f"```\n{suggestion.replacement_lines}\n```\n\n"
            f"{_BOT_MARKER}"
        )
        self._ado.create_pr_thread(
            body={
                "comments": [{"parentCommentId": 0, "content": content, "commentType": "codeChange"}],
                "status": "active",
                "properties": {"adoAiReview.kind": {"$type": "System.String", "$value": "fix-suggestion"}},
                "threadContext": {
                    "filePath": suggestion.file_path if suggestion.file_path.startswith("/") else f"/{suggestion.file_path}",
                    "rightFileStart": {"line": suggestion.line_start, "offset": 1},
                    "rightFileEnd": {"line": suggestion.line_end, "offset": 1},
                },
            }
        )

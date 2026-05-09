from __future__ import annotations

from ado_ai_pr_review.ado_toolset import AdoToolset
from ado_ai_pr_review.models import Finding, ReviewResult


class SuggestionPublisher:
    def __init__(self, ado_toolset: AdoToolset) -> None:
        self._ado = ado_toolset

    def publish_onboarding(self) -> None:
        self._ado.create_pr_thread(
            body={
                "comments": [
                    {
                        "parentCommentId": 0,
                        "content": "ADO AI review is available. Comment `/ai review`, `/ai security`, or `/ai fix` to run it.",
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
                        "content": f"ADO AI review summary:\n\n{result.summary}",
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
        if finding.suggested_code:
            content = f"{content}\n\n```suggestion\n{finding.suggested_code}\n```"

        body: dict[str, object] = {
            "comments": [{"parentCommentId": 0, "content": content, "commentType": "text"}],
            "status": "active",
            "properties": {"adoAiReview.kind": {"$type": "System.String", "$value": "finding"}},
        }
        if finding.file_path and finding.line_start:
            line_end = finding.line_end or finding.line_start
            body["threadContext"] = {
                "filePath": finding.file_path,
                "rightFileStart": {"line": finding.line_start, "offset": 1},
                "rightFileEnd": {"line": line_end, "offset": 1},
            }
        self._ado.create_pr_thread(body=body)

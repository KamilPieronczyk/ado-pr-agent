from __future__ import annotations

import re

from ado_ai_pr_review.models import (
    Finding,
    FindingSeverity,
    FindingType,
)

SECRET_PATTERNS = [
    re.compile(r"(?P<name>api[_-]?key|secret|token|password)\s*=\s*['\"](?P<value>[^'\"]{12,})['\"]", re.IGNORECASE),
    re.compile(r"(?P<value>sk-[A-Za-z0-9_-]{16,})"),
]


class SecurityScanner:
    def scan_diff(self, diff_text: str) -> tuple[list[Finding], str]:
        findings: list[Finding] = []
        redacted = diff_text
        for pattern in SECRET_PATTERNS:
            for match in pattern.finditer(diff_text):
                value = match.groupdict().get("value") or match.group(0)
                redacted = redacted.replace(value, "[REDACTED_SECRET]")
                findings.append(
                    Finding(
                        type=FindingType.SECURITY,
                        severity=FindingSeverity.CRITICAL,
                        title="Possible secret committed",
                        body="A value matching a secret pattern appears in the diff. Remove it from the branch and rotate the credential if it was valid.",
                    )
                )
        return findings, redacted

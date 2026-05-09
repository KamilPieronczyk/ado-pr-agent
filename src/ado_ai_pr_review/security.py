from __future__ import annotations

import re

from ado_ai_pr_review.models import (
    Finding,
    FindingSeverity,
    FindingType,
)

SECRET_PATTERNS = [
    # Generic assignment: api_key = "value", password = "value", etc.
    re.compile(r"(?P<name>api[_-]?key|secret|password|credential)\s*=\s*['\"](?P<value>[^'\"]{12,})['\"]", re.IGNORECASE),
    # OpenAI-style tokens
    re.compile(r"(?P<value>sk-[A-Za-z0-9_-]{16,})"),
    # AWS access key IDs
    re.compile(r"(?P<value>AKIA[0-9A-Z]{16})"),
    # AWS secret access keys (40-char base64)
    re.compile(r"(?P<value>[A-Za-z0-9+/]{40})(?![A-Za-z0-9+/=])"),
    # GitHub PATs (classic and fine-grained)
    re.compile(r"(?P<value>gh[pousr]_[A-Za-z0-9_]{36,})"),
    re.compile(r"(?P<value>github_pat_[A-Za-z0-9_]{82})"),
    # PEM private keys
    re.compile(r"(?P<value>-----BEGIN [A-Z ]+PRIVATE KEY-----)", re.MULTILINE),
    # Azure connection strings / SAS tokens
    re.compile(r"(?P<value>DefaultEndpointsProtocol=https;AccountName=[^;]+;AccountKey=[A-Za-z0-9+/=]{40,})"),
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

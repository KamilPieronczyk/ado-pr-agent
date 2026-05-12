from __future__ import annotations

import re
from collections.abc import Iterable

_DEFAULT_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{36,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{82}"),
    re.compile(r"DefaultEndpointsProtocol=https;AccountName=[^;]+;AccountKey=[A-Za-z0-9+/=]{40,}"),
    re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----", re.MULTILINE),
)


class SecretRedactor:
    def __init__(self, secrets: Iterable[str] = ()) -> None:
        self._secrets = tuple(secret.strip() for secret in secrets if secret and secret.strip())

    def redact(self, value: object) -> str:
        redacted = "" if value is None else str(value)
        for secret in self._secrets:
            redacted = redacted.replace(secret, "[REDACTED]")
        for pattern in _DEFAULT_PATTERNS:
            redacted = pattern.sub("[REDACTED]", redacted)
        return redacted

from __future__ import annotations

import json
import logging
import sys
import traceback
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from typing import TextIO

from ado_ai_pr_review.log_context import RequestContextFilter
from ado_ai_pr_review.redaction import SecretRedactor

_STANDARD_LOG_RECORD_FIELDS = frozenset(
    logging.LogRecord(
        name="",
        level=0,
        pathname="",
        lineno=0,
        msg="",
        args=(),
        exc_info=None,
    ).__dict__
)
_RESERVED_PAYLOAD_FIELDS = frozenset(
    {
        "timestamp",
        "level",
        "logger",
        "message",
        "request_id",
        "exc_type",
        "traceback",
    }
)
_ALLOWED_EXTRA_FIELDS = frozenset(
    {
        "pr_id",
        "repository",
        "repository_id",
        "repository_name",
        "event_type",
        "command",
        "findings_count",
        "inline_suggestions_count",
        "fix_pr_created",
        "error",
        "errors",
        "body_excerpt",
        "request",
        "data",
    }
)


class JsonLogFormatter(logging.Formatter):
    def __init__(self, *, redactor: SecretRedactor) -> None:
        super().__init__()
        self._redactor = redactor

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": self._redactor.redact(record.getMessage()),
            "request_id": getattr(record, "request_id", "unknown"),
        }
        payload.update(self._extra_fields(record))

        if record.exc_info:
            exc_type = record.exc_info[0]
            if exc_type is not None:
                payload["exc_type"] = exc_type.__name__
            payload["traceback"] = self._redactor.redact(
                "".join(traceback.format_exception(*record.exc_info))
            )

        return json.dumps(payload, ensure_ascii=False)

    def _extra_fields(self, record: logging.LogRecord) -> dict[str, object]:
        fields: dict[str, object] = {}
        for key, value in record.__dict__.items():
            if (
                key in _STANDARD_LOG_RECORD_FIELDS
                or key in _RESERVED_PAYLOAD_FIELDS
                or key not in _ALLOWED_EXTRA_FIELDS
            ):
                continue
            fields[key] = self._sanitize_value(value)
        return fields

    def _sanitize_value(self, value: object) -> object:
        if isinstance(value, str):
            return self._redactor.redact(value)
        if value is None or isinstance(value, bool | int | float):
            return value
        if isinstance(value, Mapping):
            return {
                self._redactor.redact(key): self._sanitize_value(nested_value)
                for key, nested_value in value.items()
            }
        if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
            return [self._sanitize_value(item) for item in value]
        return self._redactor.redact(value)


def configure_logging(
    verbose: bool = False,
    *,
    stream: TextIO | None = None,
    secrets: Iterable[str] = (),
    force: bool = False,
) -> None:
    root = logging.getLogger()
    if root.handlers and not force:
        return
    if force:
        root.handlers.clear()

    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(JsonLogFormatter(redactor=SecretRedactor(secrets)))
    handler.addFilter(RequestContextFilter())

    root.handlers[:] = [handler]
    root.setLevel(logging.DEBUG if verbose else logging.INFO)

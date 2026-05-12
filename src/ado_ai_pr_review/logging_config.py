from __future__ import annotations

import json
import logging
import sys
import traceback
from collections.abc import Iterable
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
            if key in _STANDARD_LOG_RECORD_FIELDS or key == "request_id":
                continue
            fields[key] = self._format_extra_value(value)
        return fields

    def _format_extra_value(self, value: object) -> object:
        if isinstance(value, str):
            return self._redactor.redact(value)
        try:
            json.dumps(value)
        except TypeError:
            return self._redactor.redact(value)
        return value


def configure_logging(
    verbose: bool = False,
    *,
    stream: TextIO | None = None,
    secrets: Iterable[str] = (),
    force: bool = False,
) -> None:
    root = logging.getLogger()
    if force:
        root.handlers.clear()

    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(JsonLogFormatter(redactor=SecretRedactor(secrets)))
    handler.addFilter(RequestContextFilter())

    root.handlers[:] = [handler]
    root.setLevel(logging.DEBUG if verbose else logging.INFO)

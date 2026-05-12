from __future__ import annotations

import contextlib
import contextvars
import logging
from collections.abc import Iterator

_request_id: contextvars.ContextVar[str] = contextvars.ContextVar("ado_ai_request_id", default="unknown")


def current_request_id() -> str:
    return _request_id.get()


@contextlib.contextmanager
def bind_request_context(request_id: str) -> Iterator[None]:
    token = _request_id.set(request_id or "unknown")
    try:
        yield
    finally:
        _request_id.reset(token)


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = current_request_id()
        return True

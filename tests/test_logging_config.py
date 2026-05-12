from __future__ import annotations

import json
import logging
from io import StringIO

from ado_ai_pr_review.log_context import bind_request_context
from ado_ai_pr_review.logging_config import configure_logging


def test_configure_logging_emits_json_with_request_id() -> None:
    stream = StringIO()
    configure_logging(verbose=False, stream=stream, secrets=["abc123"], force=True)

    logger = logging.getLogger("ado_ai_pr_review.test")
    with bind_request_context(request_id="req-123"):
        logger.info("processed token abc123", extra={"pr_id": 42})

    payload = json.loads(stream.getvalue())

    assert payload["level"] == "INFO"
    assert payload["logger"] == "ado_ai_pr_review.test"
    assert payload["request_id"] == "req-123"
    assert payload["message"] == "processed token [REDACTED]"
    assert payload["pr_id"] == 42
    assert "abc123" not in stream.getvalue()


def test_configure_logging_includes_exception_type() -> None:
    stream = StringIO()
    configure_logging(verbose=True, stream=stream, force=True)

    logger = logging.getLogger("ado_ai_pr_review.test")
    with bind_request_context(request_id="req-err"):
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            logger.exception("failed")

    payload = json.loads(stream.getvalue())

    assert payload["level"] == "ERROR"
    assert payload["request_id"] == "req-err"
    assert payload["exc_type"] == "RuntimeError"
    assert "traceback" in payload


def test_configure_logging_redacts_nested_extra_values() -> None:
    stream = StringIO()
    configure_logging(verbose=False, stream=stream, secrets=["abc123"], force=True)

    logger = logging.getLogger("ado_ai_pr_review.test")
    logger.info(
        "processed",
        extra={
            "data": {
                "token": "abc123",
                "tokens": ["safe", "abc123"],
                "enabled": True,
                "count": 3,
                "missing": None,
            }
        },
    )

    payload = json.loads(stream.getvalue())

    assert payload["data"] == {
        "token": "[REDACTED]",
        "tokens": ["safe", "[REDACTED]"],
        "enabled": True,
        "count": 3,
        "missing": None,
    }
    assert "abc123" not in stream.getvalue()


def test_configure_logging_reserved_schema_fields_are_not_overwritten() -> None:
    stream = StringIO()
    configure_logging(verbose=False, stream=stream, force=True)

    logger = logging.getLogger("ado_ai_pr_review.test")
    with bind_request_context(request_id="req-owned"):
        logger.info(
            "processed",
            extra={
                "level": "DEBUG",
                "logger": "wrong",
                "timestamp": "wrong",
                "request_id": "wrong",
                "exc_type": "WrongError",
                "traceback": "wrong",
                "pr_id": 42,
            },
        )

    payload = json.loads(stream.getvalue())

    assert payload["level"] == "INFO"
    assert payload["logger"] == "ado_ai_pr_review.test"
    assert payload["timestamp"] != "wrong"
    assert payload["request_id"] == "req-owned"
    assert payload["pr_id"] == 42
    assert "exc_type" not in payload
    assert "traceback" not in payload


def test_configure_logging_omits_unapproved_extra_fields() -> None:
    stream = StringIO()
    configure_logging(verbose=False, stream=stream, force=True)

    logger = logging.getLogger("ado_ai_pr_review.test")
    logger.info("processed", extra={"pr_id": 42, "unexpected": "value"})

    payload = json.loads(stream.getvalue())

    assert payload["pr_id"] == 42
    assert "unexpected" not in payload


def test_configure_logging_force_false_keeps_existing_root_handler() -> None:
    root = logging.getLogger()
    existing_stream = StringIO()
    existing_handler = logging.StreamHandler(existing_stream)
    new_stream = StringIO()
    root.handlers[:] = [existing_handler]

    try:
        configure_logging(verbose=False, stream=new_stream, force=False)

        assert root.handlers == [existing_handler]
    finally:
        root.handlers.clear()


def test_configure_logging_redacts_unsupported_nested_objects() -> None:
    class UnsupportedSecret:
        def __str__(self) -> str:
            return "unsupported abc123"

    stream = StringIO()
    configure_logging(verbose=False, stream=stream, secrets=["abc123"], force=True)

    logger = logging.getLogger("ado_ai_pr_review.test")
    logger.info(
        "processed",
        extra={"data": {"items": [UnsupportedSecret(), {"token": "abc123"}]}},
    )

    payload = json.loads(stream.getvalue())

    assert payload["data"] == {
        "items": ["unsupported [REDACTED]", {"token": "[REDACTED]"}]
    }
    assert "abc123" not in stream.getvalue()

from __future__ import annotations

import json
import logging
import math
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
            "errors": {
                "token": "abc123",
                "tokens": ["safe", "abc123"],
                "enabled": True,
                "count": 3,
                "missing": None,
            }
        },
    )

    payload = json.loads(stream.getvalue())

    assert payload["errors"] == {
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


def test_configure_logging_omits_generic_request_and_data_extras() -> None:
    stream = StringIO()
    configure_logging(verbose=False, stream=stream, force=True)

    logger = logging.getLogger("ado_ai_pr_review.test")
    logger.info(
        "processed",
        extra={"request": {"id": "req"}, "data": {"token": "abc123"}, "pr_id": 42},
    )

    payload = json.loads(stream.getvalue())

    assert payload["pr_id"] == 42
    assert "request" not in payload
    assert "data" not in payload


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
        extra={"errors": {"items": [UnsupportedSecret(), {"token": "abc123"}]}},
    )

    payload = json.loads(stream.getvalue())

    assert payload["errors"] == {
        "items": ["unsupported [REDACTED]", {"token": "[REDACTED]"}]
    }
    assert "abc123" not in stream.getvalue()


def test_configure_logging_sanitizes_non_finite_float_extras() -> None:
    stream = StringIO()
    configure_logging(verbose=False, stream=stream, force=True)

    logger = logging.getLogger("ado_ai_pr_review.test")
    logger.info(
        "processed",
        extra={"errors": [float("nan"), float("inf"), float("-inf"), 1.5]},
    )

    output = stream.getvalue()
    payload = json.loads(output)

    assert "NaN" not in output
    assert "Infinity" not in output
    assert payload["errors"][:3] == [None, None, None]
    assert math.isclose(payload["errors"][3], 1.5)

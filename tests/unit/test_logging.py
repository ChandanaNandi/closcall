"""Unit tests for structured JSON logging."""

import json
import logging

import pytest

from closcall.observability.logging import configure_logging


def _last_json_line(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert lines, "expected at least one log line on stdout"
    return json.loads(lines[-1])  # type: ignore[no-any-return]


def test_emits_single_json_line_with_required_fields(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("INFO")
    logging.getLogger("closcall.test").info("hello")
    payload = _last_json_line(capsys)
    assert payload["level"] == "INFO"
    assert payload["logger"] == "closcall.test"
    assert payload["message"] == "hello"
    # UTC, timezone-aware (Bible §6)
    assert str(payload["timestamp"]).endswith("+00:00")


def test_extra_fields_are_included(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO")
    logging.getLogger("closcall.test").info("evt", extra={"incident_key": "INC-1"})
    payload = _last_json_line(capsys)
    assert payload["incident_key"] == "INC-1"


def test_level_filtering(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("WARNING")
    logging.getLogger("closcall.test").info("should not appear")
    assert capsys.readouterr().out == ""


def test_reconfigure_is_idempotent(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO")
    configure_logging("INFO")
    logging.getLogger("closcall.test").info("once")
    out = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert len(out) == 1, "duplicate handlers would emit duplicate lines"


def test_exception_is_captured(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO")
    try:
        raise ValueError("boom")
    except ValueError:
        logging.getLogger("closcall.test").exception("failed")
    payload = _last_json_line(capsys)
    assert "ValueError: boom" in str(payload["exception"])

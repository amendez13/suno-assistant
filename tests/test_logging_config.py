"""Tests for structured logging helpers."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from tests.module_loader import import_source_module

logging_config = import_source_module("logging_config")
JSONFormatter = logging_config.JSONFormatter
configure_logging = logging_config.configure_logging
get_log_context = logging_config.get_log_context
set_log_context = logging_config.set_log_context


class TestLogContext:
    def test_default_context_is_empty(self) -> None:
        set_log_context()
        context = get_log_context()

        assert context.session_id == ""
        assert context.task_id == ""
        assert context.phase == ""

    def test_set_and_get_context(self) -> None:
        set_log_context(session_id="run-1", task_id="job-42", phase="fetch")
        context = get_log_context()

        assert context.session_id == "run-1"
        assert context.task_id == "job-42"
        assert context.phase == "fetch"


class TestJSONFormatter:
    def setup_method(self) -> None:
        set_log_context()

    @staticmethod
    def _make_record() -> logging.LogRecord:
        logger = logging.getLogger("test.logger")
        return logger.makeRecord(
            name="test.logger",
            level=logging.INFO,
            fn="test.py",
            lno=1,
            msg="hello",
            args=(),
            exc_info=None,
        )

    def test_includes_correlation_fields(self) -> None:
        set_log_context(session_id="run-1", task_id="job-42", phase="fetch")

        payload = json.loads(JSONFormatter().format(self._make_record()))

        assert payload["session_id"] == "run-1"
        assert payload["task_id"] == "job-42"
        assert payload["phase"] == "fetch"

    def test_includes_extra_fields(self) -> None:
        record = self._make_record()
        record.event = "task_started"  # type: ignore[attr-defined]
        record.queue = "default"  # type: ignore[attr-defined]

        payload = json.loads(JSONFormatter().format(record))

        assert payload["event"] == "task_started"
        assert payload["queue"] == "default"

    def test_includes_exception_details(self) -> None:
        logger = logging.getLogger("test.exc")
        try:
            raise ValueError("boom")
        except ValueError:
            import sys

            record = logger.makeRecord(
                name="test.exc",
                level=logging.ERROR,
                fn="test.py",
                lno=1,
                msg="failed",
                args=(),
                exc_info=sys.exc_info(),
            )

        payload = json.loads(JSONFormatter().format(record))

        assert "exception" in payload
        assert "ValueError: boom" in payload["exception"]


class TestConfigureLogging:
    def setup_method(self) -> None:
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
            handler.close()

    def test_returns_none_without_jsonl_path(self) -> None:
        handler = configure_logging()

        assert handler is None

    def test_writes_jsonl_when_path_is_provided(self, tmp_path: Path) -> None:
        log_path = tmp_path / "logs" / "worker.jsonl"
        handler = configure_logging(jsonl_path=str(log_path))
        logger = logging.getLogger("test.write")
        try:
            set_log_context(session_id="run-1", task_id="job-42", phase="write")
            logger.info("Structured line", extra={"event": "write"})
        finally:
            if handler is not None:
                logging.getLogger().removeHandler(handler)
                handler.close()

        lines = log_path.read_text(encoding="utf-8").splitlines()
        payload = json.loads(lines[-1])

        assert payload["msg"] == "Structured line"
        assert payload["event"] == "write"
        assert payload["session_id"] == "run-1"

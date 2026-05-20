"""Structured logging helpers with optional JSONL output."""

from __future__ import annotations

import contextvars
import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class LogContext:
    """Correlation fields carried across a task or session."""

    session_id: str = ""
    task_id: str = ""
    phase: str = ""


_LOG_CONTEXT: contextvars.ContextVar[LogContext] = contextvars.ContextVar(
    "log_context",
    default=LogContext(),
)

_RESERVED_LOG_RECORD_FIELDS = frozenset(vars(logging.makeLogRecord({})))


def get_log_context() -> LogContext:
    """Return the current logging correlation context."""
    return _LOG_CONTEXT.get()


def set_log_context(*, session_id: str = "", task_id: str = "", phase: str = "") -> None:
    """Set the correlation fields for subsequent log records."""
    _LOG_CONTEXT.set(
        LogContext(
            session_id=session_id,
            task_id=task_id,
            phase=phase,
        )
    )


def get_log_context_payload() -> dict[str, str | None]:
    """Return the current correlation fields as a JSON-friendly payload."""
    context = asdict(get_log_context())
    return {key: value or None for key, value in context.items()}


class JSONFormatter(logging.Formatter):
    """Emit one JSON object per log record."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            **get_log_context_payload(),
        }

        for key, value in record.__dict__.items():
            if key in _RESERVED_LOG_RECORD_FIELDS:
                continue
            if key in payload:
                continue
            payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def configure_logging(
    *,
    level: int = logging.INFO,
    jsonl_path: str | None = None,
) -> logging.Handler | None:
    """Configure stderr logging and optional JSONL file logging."""
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        handler.close()

    stderr_handler = logging.StreamHandler()
    stderr_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
    root_logger.addHandler(stderr_handler)

    if not jsonl_path:
        return None

    jsonl_file = Path(jsonl_path)
    jsonl_file.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(jsonl_file, encoding="utf-8")
    file_handler.setFormatter(JSONFormatter())
    root_logger.addHandler(file_handler)
    return file_handler

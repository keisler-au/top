"""Structured, content-safe process logging."""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any


class JsonFormatter(logging.Formatter):
    """Emit a small fixed event envelope and omit request or model payloads."""

    def format(self, record: logging.LogRecord) -> str:
        fields: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for name in ("event", "method", "path", "status_code", "duration_ms"):
            value = getattr(record, name, None)
            if value is not None:
                fields[name] = value
        if record.exc_info is not None:
            fields["exception_type"] = record.exc_info[0].__name__
        return json.dumps(fields, separators=(",", ":"), default=str)


def configure_logging() -> None:
    """Set an application-owned JSON handler without mutating Uvicorn handlers."""
    logger = logging.getLogger("triage_processor")
    if logger.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
    logger.propagate = False

"""Logging with a per-request correlation id.

Plain text for local development, one JSON object per line when ``LOG_JSON=true`` (what log
aggregators on Render, Fly, Azure Container Apps etc. want). The request id is carried in a
contextvar, so every line emitted while serving a request (even from worker threads) includes it.
"""
from __future__ import annotations

import contextvars
import json
import logging
import sys

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

LOGGER_NAME = "az900"
_RESERVED = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime", "request_id"}


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        payload.update({k: v for k, v in record.__dict__.items() if k not in _RESERVED})
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO", json_logs: bool = False) -> None:
    """Idempotent: safe to call on every startup (and from tests)."""
    logger = logging.getLogger(LOGGER_NAME)
    for handler in list(logger.handlers):
        if getattr(handler, "_az900", False):
            logger.removeHandler(handler)
    handler = logging.StreamHandler(sys.stderr)
    handler._az900 = True  # type: ignore[attr-defined]
    handler.addFilter(_RequestIdFilter())
    handler.setFormatter(
        _JsonFormatter() if json_logs
        else logging.Formatter("%(asctime)s %(levelname)-7s [%(request_id)s] %(name)s: %(message)s")
    )
    logger.addHandler(handler)
    logger.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"{LOGGER_NAME}.{name}")

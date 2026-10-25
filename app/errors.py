"""Consistent JSON errors.

Validation and ``HTTPException`` responses keep FastAPI's ``{"detail": ...}`` shape, which the
frontend already understands. Database contention becomes a retryable 503. Anything unexpected is
turned into a generic 500 by ``middleware.RequestContextMiddleware`` carrying only a request id, so
stack traces and internals never reach the client but can be found in the logs.
"""
from __future__ import annotations

import json
import sqlite3

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .logging_config import get_logger, request_id_var

log = get_logger("errors")

INTERNAL_ERROR_DETAIL = "Something went wrong on our side. Please try again."


def internal_error_body(request_id: str) -> bytes:
    return json.dumps({"detail": INTERNAL_ERROR_DETAIL, "request_id": request_id}).encode()


async def _database_unavailable(_: Request, exc: sqlite3.OperationalError) -> JSONResponse:
    log.error("database error: %s", exc)
    return JSONResponse(
        status_code=503,
        content={"detail": "The database is busy or unavailable. Please retry in a moment.",
                 "request_id": request_id_var.get()},
        headers={"Retry-After": "2"},
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(sqlite3.OperationalError, _database_unavailable)

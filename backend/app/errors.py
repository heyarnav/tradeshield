"""API errors and PostgreSQL SQLSTATE -> HTTP mapping.

Raw PostgreSQL messages, SQLSTATEs, stack traces and credentials are never sent
to a client: every database failure becomes a canned, human-readable message.
The real error is logged server-side only.
"""

from __future__ import annotations

import logging

import psycopg

log = logging.getLogger("tradeshield.api")

# Application SQLSTATEs raised by the Phase-1 triggers/functions (TS001..TS006)
# plus the PostgreSQL integrity classes we care about.
SQLSTATE_MAP: dict[str, tuple[int, str, str]] = {
    "TS001": (403, "ORDER_BLOCKED", "Order blocked by security screening."),
    "TS002": (422, "INSUFFICIENT_FUNDS", "Insufficient funds for this order."),
    "TS003": (422, "INSUFFICIENT_HOLDINGS", "Insufficient holdings for this order."),
    "TS004": (422, "INVALID_ORDER", "The order data is invalid."),
    "TS005": (422, "ENTITY_INACTIVE", "This account or instrument is not active."),
    "TS006": (422, "LIMIT_PRICE_RULE",
              "MARKET orders take no limit price; LIMIT orders require one."),
    "23505": (409, "CONFLICT", "That record already exists."),
    "23503": (409, "CONFLICT", "A referenced record does not exist."),
    "23514": (422, "VALIDATION_ERROR", "A database validation rule rejected this request."),
    "23502": (422, "VALIDATION_ERROR", "A required field was missing."),
    "23500": (409, "CONFLICT", "That record already exists."),
    "22003": (422, "VALIDATION_ERROR", "A numeric value is out of range."),
    "22007": (422, "VALIDATION_ERROR", "A date or address value is malformed."),
    "22P02": (422, "VALIDATION_ERROR", "A value has the wrong format."),
    "40001": (409, "CONFLICT", "The record was modified concurrently, please retry."),
    "40P01": (409, "CONFLICT", "The record was modified concurrently, please retry."),
}

DEFAULT_ERROR = (500, "INTERNAL_ERROR", "Something went wrong. Please try again later.")


class ApiError(Exception):
    """Controlled, JSON-serialisable API error."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message}}


def translate_db_error(exc: psycopg.errors.DatabaseError) -> ApiError:
    """Map a database exception to a safe ApiError (logging the details)."""
    state = getattr(exc, "sqlstate", None)
    status, code, message = SQLSTATE_MAP.get(state, DEFAULT_ERROR)
    log.warning("database error sqlstate=%s mapped_to=%s %s: %s",
                state, status, code, getattr(exc, "diag", None) and exc.diag.message_primary)
    if state is None and status == 500:
        log.exception("unmapped database error")
    return ApiError(status, code, message)


def is_sqlstate(exc: Exception, code: str) -> bool:
    return isinstance(exc, psycopg.errors.DatabaseError) and exc.sqlstate == code

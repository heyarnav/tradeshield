"""psycopg3 data access.

One connection per request context, autocommit mode, and explicit
``with conn.transaction():`` blocks for anything multi-statement -- which gives
us exactly the database-side BEGIN/COMMIT/ROLLBACK semantics Phase 1 relies on.

No ORM: every query in this project is hand-written, parameterized SQL.
"""

from __future__ import annotations

import psycopg
from flask import current_app, g
from psycopg.rows import dict_row
from psycopg.types.json import Json

__all__ = ["get_db", "fetch_all", "fetch_one", "run", "transaction", "Json"]


def get_db() -> psycopg.Connection:
    """Return the connection for this request, creating it on first use."""
    if "db_conn" not in g:
        dsn = current_app.config.get("DATABASE_URL")
        if not dsn:
            raise RuntimeError("DATABASE_URL is not configured")
        g.db_conn = psycopg.connect(dsn, row_factory=dict_row, autocommit=True)
    return g.db_conn


def close_db(_exc: BaseException | None = None) -> None:
    conn = g.pop("db_conn", None)
    if conn is not None:
        try:
            conn.close()
        except Exception:  # noqa: BLE001 - teardown must never mask an error
            pass


def fetch_all(sql: str, params: tuple | list | dict = ()) -> list[dict]:
    return get_db().execute(sql, params).fetchall()


def fetch_one(sql: str, params: tuple | list | dict = ()) -> dict | None:
    return get_db().execute(sql, params).fetchone()


def run(sql: str, params: tuple | list | dict = ()):
    """Execute a statement (caller is responsible for the transaction)."""
    return get_db().execute(sql, params)


def transaction():
    """Explicit BEGIN..COMMIT/ROLLBACK block on the request connection."""
    return get_db().transaction()

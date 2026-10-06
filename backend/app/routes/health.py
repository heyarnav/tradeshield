"""Liveness / database connectivity check."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify

from ..db import fetch_one

bp = Blueprint("health", __name__, url_prefix="/api")


@bp.get("/health")
def health():
    try:
        fetch_one("SELECT 1 AS ok")
        database = True
    except Exception:  # noqa: BLE001 - health must never 500
        current_app.logger.exception("health check: database unreachable")
        database = False
    status = "ok" if database else "degraded"
    return jsonify({"data": {"status": status, "database": database}}), (
        200 if database else 503
    )

"""Security / admin endpoints (role = admin only).

All heavy lifting stays in PostgreSQL: dashboards come from views, indicator
lookup from fn_lookup_threat(), blocked orders from vw_blocked_orders.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import psycopg
from flask import Blueprint, g, jsonify, request

from ..db import fetch_all, fetch_one, run, transaction
from ..errors import ApiError, translate_db_error
from ..schemas import IndicatorIn, IndicatorPatch, SourceIn, parse
from ..security import admin_required, client_ip, json_body

bp = Blueprint("security", __name__, url_prefix="/api/security")


def _audit(action: str, entity_type: str, entity_id) -> None:
    run(
        """INSERT INTO audit_logs
              (actor_user_id, actor_role, action, entity_type, entity_id,
               ip_address, status)
           VALUES (%s, %s, %s, %s, %s, %s, 'success')""",
        (g.user["user_id"], g.user["role"], action, entity_type, str(entity_id),
         client_ip()),
    )


def _paging(max_limit: int = 200) -> tuple[int, int]:
    try:
        limit = int(request.args.get("limit", 50))
        offset = int(request.args.get("offset", 0))
    except ValueError as exc:
        raise ApiError(422, "VALIDATION_ERROR",
                       "limit and offset must be integers.") from exc
    if not (1 <= limit <= max_limit) or offset < 0:
        raise ApiError(422, "VALIDATION_ERROR",
                       f"limit must be 1..{max_limit} and offset must be >= 0.")
    return limit, offset


# --------------------------------------------------------------------------
# dashboard
# --------------------------------------------------------------------------
@bp.get("/dashboard")
@admin_required
def dashboard():
    row = fetch_one("SELECT * FROM vw_security_dashboard")
    return jsonify({"data": row}), 200


# --------------------------------------------------------------------------
# threat indicators
# --------------------------------------------------------------------------
@bp.get("/indicators")
@admin_required
def list_indicators():
    where: list[str] = []
    params: list = []

    kind = request.args.get("type") or request.args.get("indicator_type")
    if kind:
        if kind not in ("ip", "domain", "url", "file_hash"):
            raise ApiError(422, "VALIDATION_ERROR",
                           "type must be ip, domain, url or file_hash.")
        where.append("i.indicator_type = %s")
        params.append(kind)

    active = request.args.get("active")
    if active is not None:
        if active.lower() in ("true", "1", "yes"):
            where.append("i.is_active")
        elif active.lower() in ("false", "0", "no"):
            where.append("NOT i.is_active")

    search = request.args.get("q", "").strip()
    if search:
        where.append("(i.value ILIKE %s OR i.threat_category ILIKE %s "
                     "OR s.name ILIKE %s)")
        pattern = f"%{search}%"
        params.extend([pattern, pattern, pattern])

    limit, offset = _paging()
    sql = """SELECT i.indicator_id, i.indicator_type, i.value, i.threat_category,
                    i.confidence, i.first_seen, i.last_seen, i.expires_at,
                    i.is_active, i.notes, i.created_at,
                    i.source_id, s.name AS source_name, s.reliability,
                    (i.is_active AND (i.expires_at IS NULL OR i.expires_at > now()))
                        AS currently_screening
             FROM threat_indicators i
             JOIN threat_sources s ON s.source_id = i.source_id"""
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY i.is_active DESC, i.confidence DESC, i.last_seen DESC " \
           "LIMIT %s OFFSET %s"
    params.extend([limit, offset])

    rows = fetch_all(sql, tuple(params))
    total = fetch_one(
        "SELECT count(*) AS n FROM threat_indicators i "
        "JOIN threat_sources s ON s.source_id = i.source_id"
        + (" WHERE " + " AND ".join(where) if where else ""),
        tuple(params[:-2]),
    )["n"]
    return jsonify({"data": {"items": rows, "total": total}}), 200


@bp.post("/indicators")
@admin_required
def create_indicator():
    payload = parse(IndicatorIn, json_body())
    now = datetime.now(timezone.utc)
    first_seen = payload.first_seen or now
    last_seen = payload.last_seen or first_seen

    try:
        with transaction():
            if payload.source_id:
                source = fetch_one(
                    "SELECT source_id, name FROM threat_sources WHERE source_id = %s",
                    (payload.source_id,),
                )
                if not source:
                    raise ApiError(404, "SOURCE_NOT_FOUND", "Threat source not found.")
            else:
                source_name = payload.source_name or "Manual Entry"
                # upsert by name: repeated manual entries reuse one source
                source = fetch_one(
                    """INSERT INTO threat_sources (name)
                       VALUES (%s)
                       ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
                       RETURNING source_id, name""",
                    (source_name,),
                )

            row = fetch_one(
                """INSERT INTO threat_indicators
                      (source_id, indicator_type, value, threat_category, confidence,
                       first_seen, last_seen, expires_at, is_active, notes)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   RETURNING *""",
                (source["source_id"], payload.indicator_type, payload.value,
                 payload.threat_category, payload.confidence, first_seen, last_seen,
                 payload.expires_at, payload.is_active, payload.notes),
            )
            _audit("THREAT_CREATE", "threat_indicator", row["indicator_id"])
    except psycopg.errors.DatabaseError as exc:
        if exc.sqlstate == "23505":
            raise ApiError(409, "INDICATOR_EXISTS",
                           "An indicator with this type and value already exists.") from None
        raise translate_db_error(exc) from None

    return jsonify({"data": row}), 201


@bp.patch("/indicators/<uuid:indicator_id>")
@admin_required
def update_indicator(indicator_id):
    payload = parse(IndicatorPatch, json_body())
    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        raise ApiError(422, "NO_CHANGES", "Provide at least one field to update.")

    allowed = {"threat_category", "confidence", "first_seen", "last_seen",
               "expires_at", "is_active", "notes"}
    unknown = set(fields) - allowed
    if unknown:
        raise ApiError(422, "VALIDATION_ERROR",
                       f"Fields may not be updated: {', '.join(sorted(unknown))}.")

    sets = ", ".join(f"{column} = %s" for column in fields)
    params = list(fields.values()) + [indicator_id]

    try:
        with transaction():
            row = fetch_one(
                f"UPDATE threat_indicators SET {sets} "
                f"WHERE indicator_id = %s RETURNING *",
                tuple(params),
            )
            if not row:
                raise ApiError(404, "INDICATOR_NOT_FOUND",
                               "Threat indicator not found.")
            action = ("THREAT_DISABLE" if fields.get("is_active") is False
                      else "THREAT_UPDATE")
            _audit(action, "threat_indicator", indicator_id)
    except psycopg.errors.DatabaseError as exc:
        raise translate_db_error(exc) from None

    return jsonify({"data": row}), 200


@bp.get("/indicators/active")
@admin_required
def active_indicators():
    """vw_active_threats -- the exact set the screening trigger consults."""
    rows = fetch_all("SELECT * FROM vw_active_threats")
    return jsonify({"data": rows}), 200


# --------------------------------------------------------------------------
# threat sources
# --------------------------------------------------------------------------
@bp.get("/sources")
@admin_required
def list_sources():
    rows = fetch_all(
        """SELECT s.source_id, s.name, s.description, s.contact_url, s.reliability,
                  s.is_active, s.created_at,
                  count(i.indicator_id) AS indicator_count,
                  count(i.indicator_id) FILTER (WHERE i.is_active) AS active_indicators
           FROM threat_sources s
           LEFT JOIN threat_indicators i ON i.source_id = s.source_id
           GROUP BY s.source_id
           ORDER BY s.name"""
    )
    return jsonify({"data": rows}), 200


@bp.post("/sources")
@admin_required
def create_source():
    payload = parse(SourceIn, json_body())
    try:
        with transaction():
            row = fetch_one(
                """INSERT INTO threat_sources (name, description, contact_url, reliability)
                   VALUES (%s, %s, %s, %s) RETURNING *""",
                (payload.name, payload.description, payload.contact_url,
                 payload.reliability),
            )
            _audit("SOURCE_CREATE", "threat_source", row["source_id"])
    except psycopg.errors.DatabaseError as exc:
        if exc.sqlstate == "23505":
            raise ApiError(409, "SOURCE_EXISTS",
                           "A threat source with that name already exists.") from None
        raise translate_db_error(exc) from None
    return jsonify({"data": row}), 201


# --------------------------------------------------------------------------
# blocked orders, events, audit
# --------------------------------------------------------------------------
@bp.get("/blocked-orders")
@admin_required
def blocked_orders():
    limit, offset = _paging()
    rows = fetch_all(
        "SELECT * FROM vw_blocked_orders LIMIT %s OFFSET %s", (limit, offset)
    )
    total = fetch_one(
        """SELECT count(*) AS n FROM security_events
           WHERE event_type IN ('ORDER_BLOCKED', 'ORDER_FLAGGED')"""
    )["n"]
    return jsonify({"data": {"items": rows, "total": total}}), 200


@bp.get("/events")
@admin_required
def security_events():
    where: list[str] = []
    params: list = []
    event_type = request.args.get("event_type")
    if event_type:
        where.append("e.event_type = %s")
        params.append(event_type)
    limit, offset = _paging()
    sql = """SELECT e.event_id, e.event_type, e.severity, e.indicator_id,
                    e.order_id, e.account_id, e.details, e.created_at,
                    i.value AS indicator_value, i.indicator_type, i.confidence
             FROM security_events e
             LEFT JOIN threat_indicators i ON i.indicator_id = e.indicator_id"""
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY e.created_at DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])
    rows = fetch_all(sql, tuple(params))
    return jsonify({"data": rows}), 200


@bp.get("/audit-logs")
@admin_required
def audit_logs():
    where: list[str] = []
    params: list = []
    action = request.args.get("action")
    if action:
        where.append("a.action = %s")
        params.append(action)
    status = request.args.get("status")
    if status:
        if status not in ("success", "failure"):
            raise ApiError(422, "VALIDATION_ERROR", "status must be success or failure.")
        where.append("a.status = %s")
        params.append(status)
    limit, offset = _paging()
    sql = """SELECT a.audit_id, a.actor_user_id, a.actor_role, a.action,
                    a.entity_type, a.entity_id, a.ip_address::text AS ip_address,
                    a.status, a.created_at, u.email AS actor_email
             FROM audit_logs a
             LEFT JOIN users u ON u.user_id = a.actor_user_id"""
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY a.created_at DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])
    rows = fetch_all(sql, tuple(params))
    return jsonify({"data": rows}), 200


# --------------------------------------------------------------------------
# indicator lookup (tests a value against the intel store)
# --------------------------------------------------------------------------
@bp.get("/lookup")
@admin_required
def lookup():
    kind = request.args.get("type")
    value = request.args.get("value", "").strip()
    if kind not in ("ip", "domain", "url", "file_hash"):
        raise ApiError(422, "VALIDATION_ERROR",
                       "type must be ip, domain, url or file_hash.")
    if not value:
        raise ApiError(422, "VALIDATION_ERROR", "value is required.")

    rows = fetch_all("SELECT * FROM fn_lookup_threat(%s, %s)", (kind, value))
    return jsonify({
        "data": {"type": kind, "value": value, "matched": bool(rows),
                 "indicators": rows}
    }), 200

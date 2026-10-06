"""Orders: place (with database-side screening), list, detail.

The whole trading path stays in PostgreSQL:
  INSERT INTO orders  ->  BEFORE INSERT triggers (screening + financial rules)
                       ->  fn_execute_order() (atomic execution, row locks)
Flask only validates payload shape, resolves IDs, and -- when the trigger
rejects with TS001 -- records the security event/audit in a SEPARATE
transaction after the order transaction has rolled back.
"""

from __future__ import annotations

import json

import psycopg
from flask import Blueprint, current_app, g, jsonify, request

from ..db import fetch_all, fetch_one, run, transaction
from ..errors import ApiError, translate_db_error
from ..schemas import OrderIn, OrderQuery, parse
from ..security import auth_required, current_account, json_body, resolve_origin_ip

bp = Blueprint("orders", __name__, url_prefix="/api/orders")

ORDER_SELECT = """SELECT o.order_id, o.account_id, o.instrument_id, i.symbol,
                         i.name AS instrument_name, o.side, o.order_type,
                         o.quantity, o.limit_price, o.status, o.risk_status,
                         o.security_note, o.threat_indicator_id, o.execution_price,
                         o.origin_ip, o.referrer_domain, o.referrer_url,
                         o.placed_at, o.updated_at,
                         e.execution_id, e.quantity AS executed_quantity,
                         e.price AS executed_price, e.gross_amount, e.executed_at
                  FROM orders o
                  JOIN instruments i ON i.instrument_id = o.instrument_id
                  LEFT JOIN trade_executions e ON e.order_id = o.order_id"""


def _resolve_instrument(key: str) -> dict:
    try:
        from uuid import UUID

        UUID(key)
    except ValueError:
        row = fetch_one(
            """SELECT instrument_id, symbol, current_price, is_active
               FROM instruments WHERE upper(symbol) = upper(%s)""", (key,))
    else:
        row = fetch_one(
            """SELECT instrument_id, symbol, current_price, is_active
               FROM instruments WHERE instrument_id = %s""", (key,))
    if not row:
        raise ApiError(404, "INSTRUMENT_NOT_FOUND", "Instrument not found.")
    return row


def _record_blocked_order(exc: psycopg.errors.DatabaseError,
                          account_id, order: OrderIn, origin_ip: str) -> None:
    """Runs AFTER the order transaction rolled back: the order row is gone,
    but the security event and audit trail must survive permanently."""
    detail: dict = {}
    try:
        if exc.diag and exc.diag.message_detail:
            detail = json.loads(exc.diag.message_detail)
    except (ValueError, TypeError):
        detail = {}

    event_details = {
        "side": order.side,
        "order_type": order.order_type,
        "quantity": str(order.quantity),
        "limit_price": str(order.limit_price) if order.limit_price is not None else None,
        "instrument": order.instrument,
        "origin_ip": origin_ip,
        "referrer_domain": order.referrer_domain,
        "referrer_url": order.referrer_url,
        "indicator_value": detail.get("value"),
        "threat_category": detail.get("category"),
        "confidence": detail.get("confidence"),
        "reason": "Critical threat indicator matched during order screening",
        "rejected_by": "BEFORE INSERT trigger t1_orders_security_screen",
    }
    indicator_id = detail.get("indicator_id")

    with transaction():   # separate transaction, committed on its own
        run(
            """INSERT INTO security_events
                  (event_type, severity, indicator_id, account_id, details)
               VALUES ('ORDER_BLOCKED', 'critical', %s, %s, %s)""",
            (indicator_id, account_id, json.dumps(event_details)),
        )
        run(
            """INSERT INTO audit_logs
                  (actor_user_id, actor_role, action, entity_type, entity_id,
                   ip_address, status)
               VALUES (%s, %s, 'ORDER_BLOCKED', 'order', NULL, %s::inet, 'failure')""",
            (g.user["user_id"], g.user["role"], origin_ip),
        )


@bp.post("")
@auth_required
def create_order():
    order = parse(OrderIn, json_body())

    # MARKET/LIMIT price rules (database backstop: trigger t2 raises TS006)
    if order.order_type == "LIMIT" and order.limit_price is None:
        raise ApiError(422, "LIMIT_PRICE_REQUIRED",
                       "LIMIT orders require a limit price.")
    if order.order_type == "MARKET" and order.limit_price is not None:
        raise ApiError(422, "LIMIT_PRICE_NOT_ALLOWED",
                       "MARKET orders must not include a limit price.")

    account = current_account()
    instrument = _resolve_instrument(order.instrument)
    origin_ip = resolve_origin_ip(order.origin_ip)

    try:
        with transaction():
            created = fetch_one(
                """INSERT INTO orders
                      (account_id, instrument_id, side, order_type, quantity,
                       limit_price, origin_ip, referrer_domain, referrer_url)
                   VALUES (%s, %s, %s, %s, %s, %s, %s::inet, %s, %s)
                   RETURNING order_id, status, risk_status, security_note,
                             threat_indicator_id, placed_at""",
                (account["account_id"], instrument["instrument_id"], order.side,
                 order.order_type, order.quantity, order.limit_price,
                 origin_ip, order.referrer_domain, order.referrer_url),
            )
            execution = fetch_one(
                "SELECT fn_execute_order(%s) AS execution", (created["order_id"],)
            )["execution"]
    except psycopg.errors.DatabaseError as exc:
        if exc.sqlstate == "TS001":
            # Phase-1 contract: rollback already happened inside transaction(), so
            # the order row does not exist. Persist the evidence in a SEPARATE
            # transaction -- but a failure there must not turn a correct 403 into a
            # 500 (the block itself is already enforced by the database).
            try:
                _record_blocked_order(exc, account["account_id"], order, origin_ip)
            except psycopg.errors.DatabaseError:
                current_app.logger.exception(
                    "ORDER_BLOCKED: could not persist the security event/audit row "
                    "for user %s; the order is still blocked but the evidence is lost",
                    g.user["user_id"],
                )
            raise ApiError(403, "ORDER_BLOCKED",
                           "Order blocked by security screening.") from None
        raise translate_db_error(exc) from None

    final = fetch_one(
        ORDER_SELECT + " WHERE o.order_id = %s AND o.account_id = %s",
        (created["order_id"], account["account_id"]),
    )
    return jsonify({"data": {"order": final, "execution": execution}}), 201


@bp.get("")
@auth_required
def list_orders():
    """Own orders only (account resolved from the verified token)."""
    query = parse(OrderQuery, request.args.to_dict())
    account = current_account()

    where = ["o.account_id = %s"]
    params: list = [account["account_id"]]
    if query.status:
        where.append("o.status = %s")
        params.append(query.status)
    if query.risk_status:
        where.append("o.risk_status = %s")
        params.append(query.risk_status)

    sql = (ORDER_SELECT + " WHERE " + " AND ".join(where)
           + " ORDER BY o.placed_at DESC LIMIT %s OFFSET %s")
    params.extend([query.limit, query.offset])
    return jsonify({"data": fetch_all(sql, tuple(params))}), 200


@bp.get("/<uuid:order_id>")
@auth_required
def order_detail(order_id):
    account = current_account()
    row = fetch_one(ORDER_SELECT + " WHERE o.order_id = %s AND o.account_id = %s",
                    (order_id, account["account_id"]))
    if not row:
        # 404 (not 403) so another user's order id is not confirmed as existing
        raise ApiError(404, "ORDER_NOT_FOUND", "Order not found.")
    transactions = fetch_all(
        """SELECT t.transaction_id, t.cash_delta, t.balance_after, t.created_at,
                  e.quantity, e.price, e.gross_amount
           FROM transactions t
           JOIN trade_executions e ON e.execution_id = t.execution_id
           WHERE e.order_id = %s
           ORDER BY t.created_at""",
        (order_id,),
    )
    return jsonify({"data": {"order": row, "transactions": transactions}}), 200

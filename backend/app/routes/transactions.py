"""Cash ledger history (own account only) -- vw_transaction_history."""

from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from ..db import fetch_all
from ..errors import ApiError
from ..security import auth_required

bp = Blueprint("transactions", __name__, url_prefix="/api/transactions")


@bp.get("")
@auth_required
def transaction_history():
    limit = request.args.get("limit", "50")
    offset = request.args.get("offset", "0")
    try:
        limit, offset = int(limit), int(offset)
    except ValueError as exc:
        raise ApiError(422, "VALIDATION_ERROR",
                       "limit and offset must be integers.") from exc
    if not (1 <= limit <= 200) or offset < 0:
        raise ApiError(422, "VALIDATION_ERROR",
                       "limit must be 1..200 and offset must be >= 0.")

    rows = fetch_all(
        """SELECT t.transaction_id, t.execution_id, o.order_id, o.side,
                  o.order_type, i.symbol, ex.quantity, ex.price, t.cash_delta,
                  t.balance_after, t.created_at
           FROM transactions t
           JOIN trade_executions ex ON ex.execution_id = t.execution_id
           JOIN orders o            ON o.order_id = ex.order_id
           JOIN instruments i       ON i.instrument_id = o.instrument_id
           WHERE o.account_id = (
                     SELECT account_id FROM trading_accounts WHERE user_id = %s
                 )
           ORDER BY t.created_at DESC
           LIMIT %s OFFSET %s""",
        (g.user["user_id"], limit, offset),
    )
    return jsonify({"data": rows}), 200

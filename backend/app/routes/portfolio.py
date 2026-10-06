"""Portfolio summary and holdings (own account only)."""

from __future__ import annotations

from flask import Blueprint, g, jsonify

from ..db import fetch_all, fetch_one
from ..errors import ApiError
from ..security import auth_required

bp = Blueprint("portfolio", __name__, url_prefix="/api/portfolio")


@bp.get("")
@auth_required
def portfolio_summary():
    """Cash + market value + unrealized P&L from vw_portfolio_summary."""
    row = fetch_one(
        """SELECT account_id, account_number, cash_balance, holdings_count,
                  market_value, cost_basis, unrealized_pnl, total_equity,
                  account_status
           FROM vw_portfolio_summary WHERE user_id = %s""",
        (g.user["user_id"],),
    )
    if not row:
        raise ApiError(404, "ACCOUNT_NOT_FOUND",
                       "No trading account is associated with this user.")
    return jsonify({"data": row}), 200


@bp.get("/holdings")
@auth_required
def portfolio_holdings():
    rows = fetch_all(
        """SELECT h.holding_id, i.instrument_id, i.symbol, i.name, i.asset_type,
                  i.current_price, h.quantity, h.avg_buy_price,
                  round(h.quantity * i.current_price, 2)  AS market_value,
                  round(h.quantity * h.avg_buy_price, 2)  AS cost_basis,
                  round(h.quantity * (i.current_price - h.avg_buy_price), 2)
                                                          AS unrealized_pnl,
                  h.opened_at
           FROM portfolio_holdings h
           JOIN portfolios p   ON p.portfolio_id = h.portfolio_id
           JOIN instruments i  ON i.instrument_id = h.instrument_id
           WHERE p.account_id = (
                     SELECT account_id FROM trading_accounts WHERE user_id = %s
                 )
             AND h.quantity > 0
           ORDER BY market_value DESC""",
        (g.user["user_id"],),
    )
    return jsonify({"data": rows}), 200

"""Current user's trading account."""

from __future__ import annotations

from flask import Blueprint, g, jsonify

from ..db import fetch_one
from ..errors import ApiError
from ..security import auth_required

bp = Blueprint("account", __name__, url_prefix="/api/account")


@bp.get("")
@auth_required
def account_detail():
    """Account + balance + live valuation (own account only)."""
    row = fetch_one(
        """SELECT s.account_id, s.account_number, s.cash_balance, s.account_status,
                  s.holdings_count, s.market_value, s.cost_basis, s.unrealized_pnl,
                  s.total_equity, u.email, u.full_name, u.role,
                  a.currency, a.created_at
           FROM vw_portfolio_summary s
           JOIN users u ON u.user_id = s.user_id
           JOIN trading_accounts a ON a.account_id = s.account_id
           WHERE s.user_id = %s""",
        (g.user["user_id"],),
    )
    if not row:
        raise ApiError(404, "ACCOUNT_NOT_FOUND",
                       "No trading account is associated with this user.")
    return jsonify({"data": row}), 200

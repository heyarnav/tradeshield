"""Portfolio valuation and transaction history."""

from __future__ import annotations

import pytest


def _headers(user):
    return {"Authorization": f"Bearer {user['token']}"}


def test_portfolio_summary_reflects_holdings(client, register_user):
    user = register_user()
    headers = _headers(user)

    res = client.post("/api/orders", headers=headers,
                      json={"instrument": "ACME", "side": "BUY",
                            "order_type": "MARKET", "quantity": 6})
    assert res.status_code == 201

    res = client.get("/api/portfolio", headers=headers)
    assert res.status_code == 200
    summary = res.get_json()["data"]
    assert summary["holdings_count"] == 1
    assert summary["market_value"] == pytest.approx(6 * 175.40)
    assert summary["cost_basis"] == pytest.approx(6 * 175.40)
    assert summary["unrealized_pnl"] == pytest.approx(0.0, abs=0.01)
    assert summary["cash_balance"] == pytest.approx(100000 - 6 * 175.40)
    assert summary["total_equity"] == pytest.approx(
        summary["cash_balance"] + summary["market_value"]
    )


def test_holdings_include_live_valuation(client, register_user):
    user = register_user()
    headers = _headers(user)

    client.post("/api/orders", headers=headers,
                json={"instrument": "GLD", "side": "BUY", "order_type": "MARKET",
                      "quantity": 2})
    res = client.get("/api/portfolio/holdings", headers=headers)
    assert res.status_code == 200
    holdings = res.get_json()["data"]
    assert len(holdings) == 1
    row = holdings[0]
    assert row["symbol"] == "GLD"
    assert float(row["quantity"]) == 2.0
    assert row["market_value"] == pytest.approx(2 * 402.10)
    assert row["cost_basis"] == pytest.approx(2 * 402.10)


def test_portfolio_is_empty_for_a_new_user(client, register_user):
    user = register_user()
    headers = _headers(user)
    res = client.get("/api/portfolio", headers=headers)
    assert res.status_code == 200
    summary = res.get_json()["data"]
    assert summary["holdings_count"] == 0
    assert summary["market_value"] == 0.0
    assert summary["cash_balance"] == pytest.approx(100000.0)


def test_transaction_history_after_buy_and_sell(client, register_user):
    user = register_user()
    headers = _headers(user)

    assert client.post("/api/orders", headers=headers,
                       json={"instrument": "ACME", "side": "BUY",
                             "order_type": "MARKET", "quantity": 5}
                       ).status_code == 201
    assert client.post("/api/orders", headers=headers,
                       json={"instrument": "ACME", "side": "SELL",
                             "order_type": "MARKET", "quantity": 2}
                       ).status_code == 201

    res = client.get("/api/transactions", headers=headers)
    assert res.status_code == 200
    rows = res.get_json()["data"]
    assert len(rows) == 2

    # newest first
    assert rows[0]["side"] == "SELL" and rows[1]["side"] == "BUY"
    assert rows[0]["cash_delta"] > 0
    assert rows[1]["cash_delta"] < 0
    assert rows[0]["symbol"] == "ACME"
    assert float(rows[1]["quantity"]) == 5.0

    account = client.get("/api/account", headers=headers).get_json()["data"]
    assert rows[0]["balance_after"] == pytest.approx(account["cash_balance"])


def test_transaction_history_is_empty_for_new_user(client, register_user):
    user = register_user()
    res = client.get("/api/transactions", headers=_headers(user))
    assert res.status_code == 200
    assert res.get_json()["data"] == []


def test_transaction_history_pagination(client, register_user):
    user = register_user()
    headers = _headers(user)
    for _ in range(3):
        assert client.post("/api/orders", headers=headers,
                           json={"instrument": "ECHO", "side": "BUY",
                                 "order_type": "MARKET", "quantity": 1}
                           ).status_code == 201

    res = client.get("/api/transactions?limit=2", headers=headers)
    assert len(res.get_json()["data"]) == 2
    res = client.get("/api/transactions?limit=999", headers=headers)
    assert res.status_code == 422
    res = client.get("/api/transactions?limit=abc", headers=headers)
    assert res.status_code == 422

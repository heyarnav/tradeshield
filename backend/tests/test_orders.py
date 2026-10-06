"""Order placement: validation, execution, screening, and error mapping."""

from __future__ import annotations

import pytest

BLOCKED_IP = "198.51.100.66"          # seed: confidence 95 -> BLOCK
FLAGGED_DOMAIN = "promo-trades.io"    # seed: confidence 68 -> FLAG
LOW_CONFIDENCE_IP = "203.0.113.24"    # seed: confidence 45 -> ALLOW
EXPIRED_IP = "192.0.2.99"             # seed: confidence 99 but expired
INACTIVE_DOMAIN = "disabled-legacy.example"  # seed: confidence 95, disabled


def place(client, headers, **overrides):
    body = {"instrument": "ACME", "side": "BUY", "order_type": "MARKET",
            "quantity": 1}
    body.update(overrides)
    return client.post("/api/orders", headers=headers, json=body)


def error_body(res) -> dict:
    body = res.get_json()
    assert set(body) == {"error"}, body
    assert set(body["error"]) == {"code", "message"}, body["error"]
    return body["error"]


# --------------------------------------------------------------------------
# successful trading
# --------------------------------------------------------------------------
def test_successful_market_buy(client, register_user, auth_headers, db):
    user = register_user()
    headers = auth_headers(user["token"])
    uid = user["user"]["user_id"]

    before = client.get("/api/account", headers=headers).get_json()["data"]
    res = place(client, headers, quantity=5)
    assert res.status_code == 201, res.get_data(as_text=True)

    data = res.get_json()["data"]
    order, execution = data["order"], data["execution"]
    assert order["status"] == "EXECUTED"
    assert order["risk_status"] == "CLEAR"
    assert float(order["execution_price"]) == 175.40
    assert execution["executed"] is True

    after = client.get("/api/account", headers=headers).get_json()["data"]
    assert after["cash_balance"] == pytest.approx(before["cash_balance"] - 5 * 175.40)

    rows = db.execute(
        """SELECT h.quantity FROM portfolio_holdings h
           JOIN portfolios p ON p.portfolio_id = h.portfolio_id
           JOIN instruments i ON i.instrument_id = h.instrument_id
           WHERE p.account_id = %s AND i.symbol = 'ACME'""",
        (order["account_id"],),
    ).fetchall()
    assert len(rows) == 1 and float(rows[0]["quantity"]) == 5.0

    counts = db.execute(
        """SELECT (SELECT count(*) FROM orders o
                   JOIN trading_accounts a ON a.account_id = o.account_id
                   WHERE a.user_id = %s) AS orders,
                  (SELECT count(*) FROM trade_executions ex
                   JOIN orders o ON o.order_id = ex.order_id
                   JOIN trading_accounts a ON a.account_id = o.account_id
                   WHERE a.user_id = %s) AS executions,
                  (SELECT count(*) FROM transactions t
                   JOIN trade_executions ex ON ex.execution_id = t.execution_id
                   JOIN orders o ON o.order_id = ex.order_id
                   JOIN trading_accounts a ON a.account_id = o.account_id
                   WHERE a.user_id = %s) AS transactions""",
        (uid, uid, uid),
    ).fetchone()
    assert counts == {"orders": 1, "executions": 1, "transactions": 1}


def test_successful_sell(client, register_user, auth_headers, db):
    user = register_user()
    headers = auth_headers(user["token"])

    assert place(client, headers, quantity=10).status_code == 201
    cash_after_buy = client.get("/api/account", headers=headers).get_json()["data"]["cash_balance"]

    res = place(client, headers, side="SELL", quantity=4)
    assert res.status_code == 201, res.get_data(as_text=True)
    order = res.get_json()["data"]["order"]
    assert order["status"] == "EXECUTED"

    cash_after_sell = client.get("/api/account", headers=headers).get_json()["data"]["cash_balance"]
    assert cash_after_sell == pytest.approx(cash_after_buy + 4 * 175.40)

    holdings = client.get("/api/portfolio/holdings", headers=headers).get_json()["data"]
    acme = [h for h in holdings if h["symbol"] == "ACME"]
    assert len(acme) == 1 and float(acme[0]["quantity"]) == 6.0
    assert float(acme[0]["avg_buy_price"]) == pytest.approx(175.40)


def test_weighted_average_buy_price(client, register_user, auth_headers, db):
    user = register_user()
    headers = auth_headers(user["token"])

    db.execute("UPDATE instruments SET current_price = 100.00 WHERE symbol = 'DYN'")
    try:
        assert place(client, headers, instrument="DYN", quantity=10).status_code == 201
        db.execute("UPDATE instruments SET current_price = 150.00 WHERE symbol = 'DYN'")
        assert place(client, headers, instrument="DYN", quantity=10).status_code == 201

        holdings = client.get("/api/portfolio/holdings", headers=headers).get_json()["data"]
        dyn = [h for h in holdings if h["symbol"] == "DYN"][0]
        assert float(dyn["quantity"]) == 20.0
        assert float(dyn["avg_buy_price"]) == pytest.approx(125.00)
    finally:
        db.execute("UPDATE instruments SET current_price = 310.00 WHERE symbol = 'DYN'")


# --------------------------------------------------------------------------
# financial validation (database rules -> HTTP)
# --------------------------------------------------------------------------
def test_insufficient_funds_is_rejected(client, register_user, auth_headers, db):
    user = register_user()
    headers = auth_headers(user["token"])

    res = place(client, headers, instrument="BTC", quantity=100)  # ~6.7M > 100k
    assert res.status_code == 422
    err = error_body(res)
    assert err["code"] == "INSUFFICIENT_FUNDS"
    assert "psycopg" not in res.get_data(as_text=True)
    assert "TS002" not in res.get_data(as_text=True)

    row = db.execute(
        """SELECT count(*) AS n FROM orders o
           JOIN trading_accounts a ON a.account_id = o.account_id
           WHERE a.user_id = %s""",
        (user["user"]["user_id"],),
    ).fetchone()
    assert row["n"] == 0, "rolled back order must not be persisted"


def test_insufficient_holdings_is_rejected(client, register_user, auth_headers, db):
    user = register_user()
    headers = auth_headers(user["token"])

    res = place(client, headers, side="SELL", instrument="VOLT", quantity=5)
    assert res.status_code == 422
    assert error_body(res)["code"] == "INSUFFICIENT_HOLDINGS"

    row = db.execute(
        """SELECT count(*) AS n FROM orders o
           JOIN trading_accounts a ON a.account_id = o.account_id
           WHERE a.user_id = %s""",
        (user["user"]["user_id"],),
    ).fetchone()
    assert row["n"] == 0


def test_inactive_account_is_rejected(client, register_user, auth_headers, db):
    user = register_user()
    headers = auth_headers(user["token"])
    db.execute(
        """UPDATE trading_accounts SET status = 'suspended'
           WHERE user_id = %s""",
        (user["user"]["user_id"],),
    )
    try:
        res = place(client, headers, quantity=1)
        assert res.status_code == 422
        assert error_body(res)["code"] == "ENTITY_INACTIVE"
    finally:
        db.execute("UPDATE trading_accounts SET status = 'active' WHERE user_id = %s",
                   (user["user"]["user_id"],))


def test_inactive_instrument_is_rejected(client, register_user, auth_headers):
    user = register_user()
    res = place(client, auth_headers(user["token"]), instrument="OLD", quantity=1)
    assert res.status_code == 422
    assert error_body(res)["code"] == "ENTITY_INACTIVE"


def test_unknown_instrument_is_rejected(client, register_user, auth_headers):
    user = register_user()
    res = place(client, auth_headers(user["token"]), instrument="NOSUCH", quantity=1)
    assert res.status_code == 404
    assert error_body(res)["code"] == "INSTRUMENT_NOT_FOUND"


# --------------------------------------------------------------------------
# MARKET / LIMIT price rules
# --------------------------------------------------------------------------
def test_limit_order_requires_limit_price(client, register_user, auth_headers, db):
    user = register_user()
    headers = auth_headers(user["token"])

    res = place(client, headers, order_type="LIMIT", quantity=1)
    assert res.status_code == 422
    assert error_body(res)["code"] == "LIMIT_PRICE_REQUIRED"

    row = db.execute(
        """SELECT count(*) AS n FROM orders o
           JOIN trading_accounts a ON a.account_id = o.account_id
           WHERE a.user_id = %s""",
        (user["user"]["user_id"],),
    ).fetchone()
    assert row["n"] == 0


def test_market_order_rejects_limit_price(client, register_user, auth_headers):
    user = register_user()
    res = place(client, auth_headers(user["token"]), order_type="MARKET",
                limit_price=100)
    assert res.status_code == 422
    assert error_body(res)["code"] == "LIMIT_PRICE_NOT_ALLOWED"


def test_limit_order_waits_when_price_not_met(client, register_user, auth_headers, db):
    user = register_user()
    headers = auth_headers(user["token"])

    res = place(client, headers, order_type="LIMIT", limit_price=1.00, quantity=2)
    assert res.status_code == 201, res.get_data(as_text=True)
    data = res.get_json()["data"]
    assert data["order"]["status"] == "PENDING"
    assert data["execution"]["executed"] is False
    assert data["execution"]["status"] == "PENDING"

    tx = client.get("/api/transactions", headers=headers).get_json()["data"]
    assert tx == [], "a pending order must not create a transaction"


def test_limit_order_fills_when_price_is_favourable(client, register_user, auth_headers):
    user = register_user()
    headers = auth_headers(user["token"])

    res = place(client, headers, instrument="ECHO", order_type="LIMIT",
                limit_price=25.00, quantity=3)   # market 19.75 <= 25 -> fill now
    assert res.status_code == 201, res.get_data(as_text=True)
    data = res.get_json()["data"]
    assert data["order"]["status"] == "EXECUTED"
    assert float(data["order"]["execution_price"]) == pytest.approx(19.75)


# --------------------------------------------------------------------------
# order payload validation
# --------------------------------------------------------------------------
@pytest.mark.parametrize("overrides,expected_code", [
    ({"quantity": 0}, "VALIDATION_ERROR"),
    ({"quantity": -5}, "VALIDATION_ERROR"),
    ({"side": "HOLD"}, "VALIDATION_ERROR"),
    ({"order_type": "STOP"}, "VALIDATION_ERROR"),
    ({"instrument": ""}, "VALIDATION_ERROR"),
])
def test_order_payload_validation(client, register_user, auth_headers,
                                  overrides, expected_code):
    user = register_user()
    res = place(client, auth_headers(user["token"]), **overrides)
    assert res.status_code == 422
    assert error_body(res)["code"] == expected_code


def test_unknown_fields_are_ignored(client, register_user, auth_headers):
    user = register_user()
    res = place(client, auth_headers(user["token"]), role="admin", account_id="x")
    assert res.status_code == 201


# --------------------------------------------------------------------------
# security screening: BLOCK / FLAG / ALLOW
# --------------------------------------------------------------------------
def test_blocked_order_never_becomes_an_order(client, register_user,
                                               auth_headers, db):
    user = register_user()
    headers = auth_headers(user["token"])
    uid = user["user"]["user_id"]

    res = place(client, headers, quantity=2, origin_ip=BLOCKED_IP)
    assert res.status_code == 403, res.get_data(as_text=True)
    err = error_body(res)
    assert err["code"] == "ORDER_BLOCKED"
    assert err["message"] == "Order blocked by security screening."

    text = res.get_data(as_text=True)
    for leaked in ("psycopg", "TS001", "plpgsql", "t1_orders", "ORDER_BLOCKED:"):
        assert leaked not in text, f"database internals leaked: {leaked}"

    counts = db.execute(
        """SELECT (SELECT count(*) FROM orders o
                   JOIN trading_accounts a ON a.account_id = o.account_id
                   WHERE a.user_id = %s) AS orders,
                  (SELECT count(*) FROM security_events e
                   JOIN trading_accounts a ON a.account_id = e.account_id
                   WHERE a.user_id = %s
                     AND e.event_type = 'ORDER_BLOCKED') AS events,
                  (SELECT count(*) FROM audit_logs
                   WHERE actor_user_id = %s AND action = 'ORDER_BLOCKED'
                     AND status = 'failure') AS audits""",
        (uid, uid, uid),
    ).fetchone()
    assert counts["orders"] == 0, "blocked order must not be persisted"
    assert counts["events"] == 1, "security event must survive the rollback"
    assert counts["audits"] == 1, "audit row must survive the rollback"

    event = db.execute(
        """SELECT e.details, e.severity, i.confidence, i.value
           FROM security_events e
           JOIN trading_accounts a ON a.account_id = e.account_id
           LEFT JOIN threat_indicators i ON i.indicator_id = e.indicator_id
           WHERE a.user_id = %s AND e.event_type = 'ORDER_BLOCKED'""",
        (uid,),
    ).fetchone()
    assert event["severity"] == "critical"
    assert event["value"] == BLOCKED_IP
    assert event["confidence"] == 95
    assert event["details"]["origin_ip"] == BLOCKED_IP
    assert event["details"]["quantity"] == "2"


def test_flagged_order_is_created_and_recorded(client, register_user,
                                                auth_headers, db):
    user = register_user()
    headers = auth_headers(user["token"])

    res = place(client, headers, quantity=1, referrer_domain=FLAGGED_DOMAIN)
    assert res.status_code == 201, res.get_data(as_text=True)
    order = res.get_json()["data"]["order"]
    assert order["risk_status"] == "FLAGGED"
    assert order["threat_indicator_id"]
    assert "flagged:" in order["security_note"]
    assert order["status"] == "EXECUTED", "a flagged order still trades"

    event = db.execute(
        """SELECT count(*) AS n FROM security_events
           WHERE event_type = 'ORDER_FLAGGED' AND order_id = %s""",
        (order["order_id"],),
    ).fetchone()
    assert event["n"] == 1


@pytest.mark.parametrize("ip", [LOW_CONFIDENCE_IP, EXPIRED_IP])
def test_low_confidence_and_expired_indicators_are_allowed(
        client, register_user, auth_headers, ip):
    user = register_user()
    res = place(client, auth_headers(user["token"]), quantity=1, origin_ip=ip)
    assert res.status_code == 201, res.get_data(as_text=True)
    assert res.get_json()["data"]["order"]["risk_status"] == "CLEAR"


def test_disabled_indicator_is_not_screened(client, register_user, auth_headers):
    user = register_user()
    res = place(client, auth_headers(user["token"]), quantity=1,
                referrer_domain=INACTIVE_DOMAIN)
    assert res.status_code == 201, res.get_data(as_text=True)
    assert res.get_json()["data"]["order"]["risk_status"] == "CLEAR"


# --------------------------------------------------------------------------
# listing / detail
# --------------------------------------------------------------------------
def test_order_list_and_detail(client, register_user, auth_headers):
    user = register_user()
    headers = auth_headers(user["token"])

    assert place(client, headers, quantity=1).status_code == 201
    assert place(client, headers, order_type="LIMIT", limit_price=0.50,
                 quantity=1).status_code == 201

    res = client.get("/api/orders", headers=headers)
    assert res.status_code == 200
    orders = res.get_json()["data"]
    assert len(orders) == 2
    assert {o["symbol"] for o in orders} == {"ACME"}

    res = client.get("/api/orders?status=PENDING", headers=headers)
    pending = res.get_json()["data"]
    assert len(pending) == 1 and pending[0]["status"] == "PENDING"

    res = client.get(f"/api/orders/{orders[0]['order_id']}", headers=headers)
    assert res.status_code == 200
    payload = res.get_json()["data"]
    assert payload["order"]["order_id"] == orders[0]["order_id"]
    assert isinstance(payload["transactions"], list)

    res = client.get("/api/orders/00000000-0000-4000-8000-000000000000",
                     headers=headers)
    assert res.status_code == 404


def test_instruments_endpoints(client, register_user, auth_headers):
    user = register_user()
    headers = auth_headers(user["token"])

    res = client.get("/api/instruments", headers=headers)
    assert res.status_code == 200
    instruments = res.get_json()["data"]
    assert len(instruments) >= 10
    assert all("current_price" in i for i in instruments)

    res = client.get("/api/instruments?asset_type=crypto", headers=headers)
    assert {i["asset_type"] for i in res.get_json()["data"]} == {"crypto"}

    res = client.get("/api/instruments/ACME", headers=headers)
    assert res.status_code == 200
    assert res.get_json()["data"]["symbol"] == "ACME"

    res = client.get("/api/instruments/NOSUCH", headers=headers)
    assert res.status_code == 404

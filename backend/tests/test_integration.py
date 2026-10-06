"""Phase 4 integration hardening tests.

Each test covers a seam that was found while auditing the frontend -> Flask ->
PostgreSQL path, and each one fails against the pre-hardening code:

- a client-supplied source IP must only be screened when the API is explicitly
  configured to trust it (otherwise order screening is trivially evadable),
- a failure while persisting the blocked-order audit must not turn a correct
  403 into a 500 (the block is enforced by the database either way),
- two concurrent BUY orders must never overspend the account.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import psycopg
import pytest

from app import create_app
from app.routes import orders as orders_module

TEST_SECRET = "pytest-secret-key-long-enough-for-hs256-32bytes"
BLOCKED_IP = "198.51.100.66"  # seeded C2 indicator, confidence 95 -> BLOCK


def test_client_supplied_origin_ip_is_ignored_unless_trusted(app, register_user):
    """Default config: the screened IP is the real socket address, never the body's."""
    register_user()  # create the user while the shared session app is usable

    strict = create_app({"TESTING": True, "JWT_SECRET": TEST_SECRET,
                         "TRUST_CLIENT_IP_HEADER": False})
    with strict.test_client() as client:
        res = client.post("/api/auth/login",
                          json={"email": "client@tradeshield.dev",
                                "password": "Client@123"})
        assert res.status_code == 200
        token = res.get_json()["data"]["token"]

        res = client.post(
            "/api/orders",
            json={"instrument": "ACME", "side": "BUY", "order_type": "MARKET",
                  "quantity": 1, "origin_ip": BLOCKED_IP},
            headers={"Authorization": f"Bearer {token}"},
        )
        # The same payload *is* blocked when the flag is on (see test_orders.py);
        # here it must trade normally because the body may not pick the IP.
        assert res.status_code == 201, res.get_data(as_text=True)
        assert res.get_json()["data"]["order"]["risk_status"] == "CLEAR"


def test_blocked_order_still_returns_403_when_audit_write_fails(
    client, register_user, auth_headers, monkeypatch, caplog
):
    """TS001 -> rollback -> audit in a separate transaction.

    If that separate write explodes, the client must still get the 403 rather
    than a 500 (the order was blocked regardless), and the loss must be logged.
    """
    user = register_user()

    def boom(*_args, **_kwargs):
        raise psycopg.errors.DatabaseError("audit store unavailable")

    monkeypatch.setattr(orders_module, "run", boom)
    with caplog.at_level("ERROR"):
        res = client.post(
            "/api/orders",
            json={"instrument": "ACME", "side": "BUY", "order_type": "MARKET",
                  "quantity": 1, "origin_ip": BLOCKED_IP},
            headers=auth_headers(user["token"]),
        )

    assert res.status_code == 403, res.get_data(as_text=True)
    assert res.get_json()["error"]["code"] == "ORDER_BLOCKED"
    assert "could not persist the security event" in caplog.text


def test_concurrent_buys_cannot_overspend(app, register_user, auth_headers, db):
    """Two simultaneous BUYs must not both succeed against the same cash balance.

    ``fn_execute_order`` locks the account row (FOR UPDATE) before checking
    funds, so exactly one order can spend the balance.
    """
    user = register_user()
    price = float(
        db.execute("SELECT current_price FROM instruments WHERE symbol = 'BTC'")
        .fetchone()["current_price"]
    )
    # One unit must fit in the 100,000 opening balance but two must not.
    assert 50_000 < price < 100_000, f"seeded BTC price {price} breaks the fixture"

    barrier = threading.Barrier(2)

    def place_order(_: int):
        with app.test_client() as client:
            barrier.wait(timeout=10)  # maximise the chance of a real race
            res = client.post(
                "/api/orders",
                json={"instrument": "BTC", "side": "BUY", "order_type": "MARKET",
                      "quantity": 1},
                headers=auth_headers(user["token"]),
            )
            return res.status_code, res.get_json()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(place_order, range(2)))

    statuses = sorted(code for code, _ in results)
    assert statuses == [201, 422], results
    rejected = [body for code, body in results if code == 422][0]
    assert rejected["error"]["code"] == "INSUFFICIENT_FUNDS"

    row = db.execute(
        """SELECT t.balance, count(o.order_id) AS orders
           FROM trading_accounts t
           LEFT JOIN orders o ON o.account_id = t.account_id
           WHERE t.account_id = %s
           GROUP BY t.balance""",
        (user["account"]["account_id"],),
    ).fetchone()
    assert row["orders"] == 1
    assert float(row["balance"]) == pytest.approx(100_000 - round(price, 2), abs=0.01)
    assert float(row["balance"]) >= 0
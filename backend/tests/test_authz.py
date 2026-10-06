"""RBAC and row-level ownership enforcement (implemented in Flask)."""

from __future__ import annotations

import pytest

SECURITY_ENDPOINTS = [
    ("GET", "/api/security/dashboard"),
    ("GET", "/api/security/indicators"),
    ("POST", "/api/security/indicators"),
    ("PATCH", "/api/security/indicators/00000000-0000-4000-8000-000000000000"),
    ("GET", "/api/security/sources"),
    ("POST", "/api/security/sources"),
    ("GET", "/api/security/blocked-orders"),
    ("GET", "/api/security/events"),
    ("GET", "/api/security/audit-logs"),
    ("GET", "/api/security/lookup?type=ip&value=1.2.3.4"),
]


@pytest.mark.parametrize("method,path", SECURITY_ENDPOINTS)
def test_client_cannot_reach_admin_endpoints(client, register_user, auth_headers,
                                             method, path):
    user = register_user()
    res = client.open(path, method=method, headers=auth_headers(user["token"]),
                      json={} if method == "POST" else None)
    assert res.status_code == 403, res.get_data(as_text=True)
    assert res.get_json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.parametrize("method,path", SECURITY_ENDPOINTS)
def test_admin_endpoints_require_authentication(client, method, path):
    res = client.open(path, method=method,
                      json={} if method == "POST" else None)
    assert res.status_code == 401
    assert res.get_json()["error"]["code"] == "AUTH_REQUIRED"


def test_admin_can_use_security_endpoints(client, admin_token, auth_headers):
    res = client.get("/api/security/dashboard", headers=auth_headers(admin_token))
    assert res.status_code == 200
    keys = set(res.get_json()["data"])
    assert {"active_threats", "blocked_orders_total", "flagged_orders_total",
            "threat_sources", "audit_entries"} <= keys

    res = client.get("/api/security/indicators", headers=auth_headers(admin_token))
    assert res.status_code == 200
    assert "items" in res.get_json()["data"]


def test_account_endpoint_returns_own_account_only(client, register_user,
                                                    auth_headers):
    a = register_user()
    b = register_user()

    res_a = client.get("/api/account", headers=auth_headers(a["token"]))
    res_b = client.get("/api/account", headers=auth_headers(b["token"]))
    assert res_a.status_code == 200 and res_b.status_code == 200

    acct_a = res_a.get_json()["data"]
    acct_b = res_b.get_json()["data"]
    assert acct_a["account_number"] == a["account"]["account_number"]
    assert acct_a["account_number"] != acct_b["account_number"]
    assert acct_a["account_id"] == a["account"]["account_id"]


def test_client_cannot_read_another_clients_order(client, register_user,
                                                   auth_headers, db):
    owner = register_user()
    intruder = register_user()

    res = client.post("/api/orders", headers=auth_headers(owner["token"]),
                      json={"instrument": "ACME", "side": "BUY",
                            "order_type": "MARKET", "quantity": 1})
    assert res.status_code == 201, res.get_data(as_text=True)
    order_id = res.get_json()["data"]["order"]["order_id"]

    # owner sees it
    res = client.get(f"/api/orders/{order_id}", headers=auth_headers(owner["token"]))
    assert res.status_code == 200

    # intruder gets 404 (existence is not confirmed)
    res = client.get(f"/api/orders/{order_id}", headers=auth_headers(intruder["token"]))
    assert res.status_code == 404
    assert res.get_json()["error"]["code"] == "ORDER_NOT_FOUND"

    # order lists never overlap
    res = client.get("/api/orders", headers=auth_headers(intruder["token"]))
    listed = [o["order_id"] for o in res.get_json()["data"]]
    assert order_id not in listed


def test_client_never_sees_another_clients_financials(client, register_user,
                                                       auth_headers):
    owner = register_user()
    other = register_user()

    for path in ("/api/orders", "/api/transactions", "/api/portfolio/holdings"):
        res = client.post("/api/orders", headers=auth_headers(owner["token"]),
                          json={"instrument": "ACME", "side": "BUY",
                                "order_type": "MARKET", "quantity": 1})
        assert res.status_code == 201
        break

    res = client.get("/api/transactions", headers=auth_headers(other["token"]))
    assert res.status_code == 200
    assert res.get_json()["data"] == []

    res = client.get("/api/portfolio/holdings", headers=auth_headers(other["token"]))
    assert res.status_code == 200
    assert res.get_json()["data"] == []


def test_unauthenticated_access_to_protected_routes(client):
    for path in ("/api/account", "/api/orders", "/api/transactions",
                 "/api/portfolio", "/api/instruments"):
        res = client.get(path)
        assert res.status_code == 401, path
        assert res.get_json()["error"]["code"] == "AUTH_REQUIRED"

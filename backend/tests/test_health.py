"""Health endpoint and JSON error contract."""

from __future__ import annotations


def test_health_reports_database_connectivity(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.get_json()["data"]
    assert data["status"] == "ok"
    assert data["database"] is True


def test_unknown_endpoint_returns_json_error(client):
    res = client.get("/api/does-not-exist")
    assert res.status_code == 404
    body = res.get_json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message"}
    assert body["error"]["code"] == "NOT_FOUND"


def test_malformed_json_is_a_clean_4xx(client, register_user, auth_headers):
    user = register_user()
    res = client.post(
        "/api/orders", data="{not json", headers={
            **auth_headers(user["token"]), "Content-Type": "application/json"}
    )
    assert res.status_code == 400
    assert res.get_json()["error"]["code"] == "BAD_REQUEST"

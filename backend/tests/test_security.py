"""Security endpoints (admin only): indicators, sources, feeds, audit."""

from __future__ import annotations

import pytest


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_indicator_lifecycle(client, admin_token, db):
    headers = _headers(admin_token)
    body = {
        "indicator_type": "ip",
        "value": "198.51.100.77",
        "threat_category": "c2",
        "confidence": 85,
        "source_name": "Pytest Feed",
        "notes": "created by pytest",
    }

    res = client.post("/api/security/indicators", json=body, headers=headers)
    assert res.status_code == 201, res.get_data(as_text=True)
    indicator = res.get_json()["data"]
    assert indicator["is_active"] is True
    assert indicator["confidence"] == 85
    assert indicator["source_id"]

    # duplicate is rejected by the UNIQUE (indicator_type, value) constraint
    res = client.post("/api/security/indicators", json=body, headers=headers)
    assert res.status_code == 409
    assert res.get_json()["error"]["code"] == "INDICATOR_EXISTS"

    # appears in the listing and in the screening set
    res = client.get("/api/security/indicators?type=ip&q=198.51.100.77",
                     headers=headers)
    payload = res.get_json()["data"]
    assert payload["total"] == 1
    assert payload["items"][0]["currently_screening"] is True

    res = client.get("/api/security/indicators/active", headers=headers)
    assert "198.51.100.77" in [i["value"] for i in res.get_json()["data"]]

    # admin lookup helper
    res = client.get("/api/security/lookup?type=ip&value=198.51.100.77",
                     headers=headers)
    data = res.get_json()["data"]
    assert data["matched"] is True
    assert data["indicators"][0]["confidence"] == 85

    # edit + disable
    res = client.patch(
        f"/api/security/indicators/{indicator['indicator_id']}",
        json={"is_active": False, "confidence": 60}, headers=headers)
    assert res.status_code == 200
    updated = res.get_json()["data"]
    assert updated["is_active"] is False
    assert updated["confidence"] == 60

    # no-op patch is rejected
    res = client.patch(
        f"/api/security/indicators/{indicator['indicator_id']}",
        json={}, headers=headers)
    assert res.status_code == 422
    assert res.get_json()["error"]["code"] == "NO_CHANGES"

    # the database trigger recorded the changes as security events
    events = db.execute(
        """SELECT count(*) AS n FROM security_events
           WHERE event_type = 'THREAT_INDICATOR_CHANGED'
             AND indicator_id = %s""",
        (indicator["indicator_id"],),
    ).fetchone()
    assert events["n"] >= 2


def test_indicator_validation_errors(client, admin_token):
    headers = _headers(admin_token)
    base = {"indicator_type": "domain", "value": "baddomain.example",
            "threat_category": "phishing", "confidence": 70,
            "source_name": "Pytest Feed"}

    res = client.post("/api/security/indicators",
                      json={**base, "confidence": 1000}, headers=headers)
    assert res.status_code == 422

    res = client.post("/api/security/indicators",
                      json={**base, "indicator_type": "ip"}, headers=headers)
    assert res.status_code == 422, "malformed ip must be rejected"

    res = client.post("/api/security/indicators",
                      json={**base, "threat_category": "apocalypse"},
                      headers=headers)
    assert res.status_code == 422

    res = client.post("/api/security/indicators",
                      json={**base, "source_id": "00000000-0000-4000-8000-000000000000"},
                      headers=headers)
    assert res.status_code == 404
    assert res.get_json()["error"]["code"] == "SOURCE_NOT_FOUND"


def test_file_hash_indicator_is_normalised(client, admin_token):
    headers = _headers(admin_token)
    res = client.post("/api/security/indicators", json={
        "indicator_type": "file_hash",
        "value": "A" * 64,
        "threat_category": "malware",
        "confidence": 91,
        "source_name": "Pytest Feed",
    }, headers=headers)
    assert res.status_code == 201, res.get_data(as_text=True)
    assert res.get_json()["data"]["value"] == "a" * 64


def test_sources_endpoints(client, admin_token):
    headers = _headers(admin_token)

    res = client.post("/api/security/sources", json={
        "name": "Pytest Feed", "description": "feed created by the test suite",
        "reliability": 4,
    }, headers=headers)
    assert res.status_code in (201, 409), res.get_data(as_text=True)

    res = client.get("/api/security/sources", headers=headers)
    assert res.status_code == 200
    rows = res.get_json()["data"]
    feed = [r for r in rows if r["name"] == "Pytest Feed"]
    assert feed and feed[0]["indicator_count"] >= 1

    res = client.post("/api/security/sources",
                      json={"name": "Pytest Feed"}, headers=headers)
    assert res.status_code == 409


def test_dashboard_blocked_orders_events_and_audit(client, admin_token):
    headers = _headers(admin_token)

    res = client.get("/api/security/dashboard", headers=headers)
    assert res.status_code == 200
    dash = res.get_json()["data"]
    for key in ("active_threats", "critical_threats", "total_indicators",
                "threat_sources", "blocked_orders_total", "flagged_orders_total",
                "events_24h", "audit_entries", "client_count"):
        assert key in dash, key

    res = client.get("/api/security/blocked-orders", headers=headers)
    assert res.status_code == 200
    payload = res.get_json()["data"]
    assert set(payload) == {"items", "total"}
    for item in payload["items"]:
        assert item["event_type"] in ("ORDER_BLOCKED", "ORDER_FLAGGED")

    res = client.get("/api/security/events", headers=headers)
    assert res.status_code == 200
    assert isinstance(res.get_json()["data"], list)

    res = client.get("/api/security/audit-logs?action=LOGIN", headers=headers)
    assert res.status_code == 200
    rows = res.get_json()["data"]
    assert all(r["action"] == "LOGIN" for r in rows)

    res = client.get("/api/security/audit-logs?action=THREAT_CREATE",
                     headers=headers)
    assert res.status_code == 200
    assert len(res.get_json()["data"]) >= 1

    res = client.get("/api/security/audit-logs?status=nonsense", headers=headers)
    assert res.status_code == 422


@pytest.mark.parametrize("url", [
    "/api/security/lookup?type=nope&value=1.2.3.4",
    "/api/security/lookup?type=ip",
])
def test_lookup_requires_valid_arguments(client, admin_token, url):
    res = client.get(url, headers=_headers(admin_token))
    assert res.status_code == 422
    assert res.get_json()["error"]["code"] == "VALIDATION_ERROR"

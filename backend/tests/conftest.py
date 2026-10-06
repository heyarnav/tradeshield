"""Pytest fixtures for the TradeShield API suite.

Tests run against the real database configured in .env (Supabase). Every test
user is created through the public API with a unique ``@tradeshield.test``
address and removed again at the end of the session, together with any
indicator/source the suite created.
"""

from __future__ import annotations

import uuid

import psycopg
import pytest
from psycopg.rows import dict_row

from app import create_app

TEST_DOMAIN = "tradeshield.test"
TEST_PASSWORD = "Passw0rd!testing"
PYTEST_SOURCE = "Pytest Feed"


# --------------------------------------------------------------------------
# app / client / raw db connection
# --------------------------------------------------------------------------
@pytest.fixture(scope="session")
def app():
    return create_app({
        "TESTING": True,
        # >= 32 bytes keeps PyJWT quiet about HMAC key length (RFC 7518)
        "JWT_SECRET": "pytest-secret-key-long-enough-for-hs256-32bytes",
        "TRUST_CLIENT_IP_HEADER": True,
    })


@pytest.fixture(scope="session")
def client(app):
    return app.test_client()


@pytest.fixture(scope="session")
def db(app):
    conn = psycopg.connect(app.config["DATABASE_URL"], row_factory=dict_row,
                           autocommit=True)
    yield conn
    conn.close()


@pytest.fixture(scope="session", autouse=True)
def _cleanup_test_data(db):
    yield
    users = "SELECT user_id FROM users WHERE email LIKE %s"
    pattern = f"%@{TEST_DOMAIN}"
    accounts = f"SELECT account_id FROM trading_accounts WHERE user_id IN ({users})"
    # order matters: security_events/audit reference accounts/users,
    # users are RESTRICTed while an account still exists.
    db.execute(
        f"DELETE FROM security_events WHERE account_id IN ({accounts})", (pattern,)
    )
    db.execute(
        f"DELETE FROM audit_logs WHERE actor_user_id IN ({users})", (pattern,)
    )
    db.execute(f"DELETE FROM trading_accounts WHERE user_id IN ({users})", (pattern,))
    db.execute("DELETE FROM users WHERE email LIKE %s", (pattern,))
    db.execute(
        """DELETE FROM threat_indicators
           WHERE source_id IN (SELECT source_id FROM threat_sources WHERE name = %s)""",
        (PYTEST_SOURCE,),
    )
    db.execute("DELETE FROM threat_sources WHERE name = %s", (PYTEST_SOURCE,))


# --------------------------------------------------------------------------
# auth helpers
# --------------------------------------------------------------------------
@pytest.fixture
def auth_headers():
    def _headers(token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}
    return _headers


@pytest.fixture
def register_user(client):
    def _register(**overrides) -> dict:
        email = f"test-{uuid.uuid4().hex[:12]}@{TEST_DOMAIN}"
        body = {"email": email, "password": TEST_PASSWORD,
                "full_name": "Test Client"}
        body.update(overrides)
        res = client.post("/api/auth/register", json=body)
        assert res.status_code == 201, res.get_data(as_text=True)
        data = res.get_json()["data"]
        return {"email": body["email"], "password": body["password"], **data}
    return _register


@pytest.fixture
def login(client):
    def _login(email: str, password: str) -> dict:
        res = client.post("/api/auth/login", json={"email": email,
                                                   "password": password})
        return res
    return _login


@pytest.fixture(scope="session")
def admin_token(client):
    res = client.post("/api/auth/login",
                      json={"email": "admin@tradeshield.dev",
                            "password": "Admin@123"})
    assert res.status_code == 200, res.get_data(as_text=True)
    return res.get_json()["data"]["token"]


@pytest.fixture(scope="session")
def seeded_client_token(client):
    res = client.post("/api/auth/login",
                      json={"email": "client@tradeshield.dev",
                            "password": "Client@123"})
    assert res.status_code == 200, res.get_data(as_text=True)
    return res.get_json()["data"]["token"]

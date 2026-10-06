"""Authentication: registration, login, JWT handling, password hashing."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from werkzeug.security import generate_password_hash

from app.security import verify_password
from conftest import TEST_PASSWORD


def test_register_creates_user_account_and_portfolio(client, register_user, db):
    user = register_user()
    assert user["token"]
    assert user["user"]["role"] == "client"
    assert user["account"]["account_number"].startswith("TS-")
    assert user["account"]["balance"] == 100000.0

    row = db.execute(
        """SELECT count(*) AS n FROM portfolios p
           JOIN trading_accounts a ON a.account_id = p.account_id
           WHERE a.user_id = %s""",
        (user["user"]["user_id"],),
    ).fetchone()
    assert row["n"] == 1


def test_register_rejects_duplicate_email(client, register_user):
    user = register_user()
    res = client.post("/api/auth/register", json={
        "email": user["email"], "password": TEST_PASSWORD,
        "full_name": "Impostor",
    })
    assert res.status_code == 409
    body = res.get_json()
    assert body["error"]["code"] == "EMAIL_EXISTS"
    assert set(body["error"]) == {"code", "message"}


def test_register_rejects_weak_password_and_bad_email(client):
    res = client.post("/api/auth/register", json={
        "email": "test-short@tradeshield.test", "password": "abc",
        "full_name": "Test Client",
    })
    assert res.status_code == 422
    assert res.get_json()["error"]["code"] == "VALIDATION_ERROR"

    res = client.post("/api/auth/register", json={
        "email": "not-an-email", "password": TEST_PASSWORD,
        "full_name": "Test Client",
    })
    assert res.status_code == 422


def test_register_ignores_role_escalation(client, db):
    """A client cannot self-assign the admin role."""
    res = client.post("/api/auth/register", json={
        "email": "test-escalate@tradeshield.test", "password": TEST_PASSWORD,
        "full_name": "Escalator", "role": "admin",
    })
    assert res.status_code == 201
    assert res.get_json()["data"]["user"]["role"] == "client"

    row = db.execute(
        "SELECT role FROM users WHERE email = %s",
        ("test-escalate@tradeshield.test",),
    ).fetchone()
    assert row["role"] == "client"


def test_login_success_and_failure(client, register_user, login):
    user = register_user()

    res = login(user["email"], TEST_PASSWORD)
    assert res.status_code == 200
    assert res.get_json()["data"]["token"]

    res = login(user["email"], "wrong-password")
    assert res.status_code == 401
    assert res.get_json()["error"]["code"] == "INVALID_CREDENTIALS"

    res = login("nobody@tradeshield.test", TEST_PASSWORD)
    assert res.status_code == 401
    assert res.get_json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_login_is_audited(client, register_user, login, db):
    user = register_user()
    login(user["email"], "definitely-wrong")
    row = db.execute(
        """SELECT count(*) AS n FROM audit_logs
           WHERE action = 'LOGIN_FAILED' AND status = 'failure'
             AND actor_user_id = %s""",
        (user["user"]["user_id"],),
    ).fetchone()
    assert row["n"] == 1


def test_me_requires_valid_token(client, register_user, auth_headers, app):
    user = register_user()

    res = client.get("/api/auth/me")
    assert res.status_code == 401
    assert res.get_json()["error"]["code"] == "AUTH_REQUIRED"

    res = client.get("/api/auth/me", headers=auth_headers("garbage.token.here"))
    assert res.status_code == 401
    assert res.get_json()["error"]["code"] == "INVALID_TOKEN"

    expired = jwt.encode(
        {"sub": user["user"]["user_id"], "role": "client",
         "email": user["email"], "exp": datetime.now(timezone.utc) - timedelta(hours=1)},
        app.config["JWT_SECRET"], algorithm="HS256",
    )
    res = client.get("/api/auth/me", headers=auth_headers(expired))
    assert res.status_code == 401
    assert res.get_json()["error"]["code"] == "TOKEN_EXPIRED"

    res = client.get("/api/auth/me", headers=auth_headers(user["token"]))
    assert res.status_code == 200
    assert res.get_json()["data"]["user"]["email"] == user["email"]


def test_deactivated_user_token_stops_working(client, register_user, auth_headers, db):
    user = register_user()
    db.execute("UPDATE users SET is_active = false WHERE user_id = %s",
               (user["user"]["user_id"],))
    try:
        res = client.get("/api/auth/me", headers=auth_headers(user["token"]))
        assert res.status_code == 401
        assert res.get_json()["error"]["code"] == "INVALID_TOKEN"
    finally:
        db.execute("UPDATE users SET is_active = true WHERE user_id = %s",
                   (user["user"]["user_id"],))


def test_password_hashing_is_argon2_and_upgrades_legacy_hashes():
    legacy = generate_password_hash("Secret123!")     # Phase-1 seed format
    ok, upgraded = verify_password(legacy, "Secret123!")
    assert ok is True
    assert upgraded is not None and upgraded.startswith("$argon2")

    ok, _ = verify_password(legacy, "nope")
    assert ok is False

    from app.security import hash_password
    modern = hash_password("Secret123!")
    assert modern.startswith("$argon2")
    ok, upgraded = verify_password(modern, "Secret123!")
    assert ok is True and upgraded is None

"""Authentication endpoints: register, login, current user."""

from __future__ import annotations

import psycopg
from flask import Blueprint, current_app, g, jsonify, request

from ..db import fetch_one, run, transaction
from ..errors import ApiError, translate_db_error
from ..schemas import LoginIn, RegisterIn, parse
from ..security import (
    auth_required,
    create_token,
    hash_password,
    json_body,
    new_account_number,
    verify_password,
)

bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def _audit(actor_user_id, role, action, entity_type, entity_id, status):
    run(
        """INSERT INTO audit_logs
              (actor_user_id, actor_role, action, entity_type, entity_id, ip_address, status)
           VALUES (%s, %s, %s, %s, %s, %s::inet, %s)""",
        (actor_user_id, role, action, entity_type, entity_id,
         request.remote_addr, status),
    )


def _audit_best_effort(actor_user_id, role, action, entity_type, entity_id, status):
    """Audit rows must never change the API response -- but a silent failure would
    hide gaps in the audit trail, so every failure is logged loudly."""
    try:
        with transaction():
            _audit(actor_user_id, role, action, entity_type, entity_id, status)
    except psycopg.errors.DatabaseError:
        current_app.logger.exception("audit_logs write failed for action=%s status=%s",
                                     action, status)


@bp.post("/register")
def register():
    """Create user + trading account + portfolio atomically, return a JWT."""
    payload = parse(RegisterIn, json_body())
    password_hash = hash_password(payload.password)

    try:
        with transaction():
            user = fetch_one(
                """INSERT INTO users (email, password_hash, full_name, role)
                   VALUES (%s, %s, %s, 'client')
                   RETURNING user_id, email, full_name, role, created_at""",
                (payload.email, password_hash, payload.full_name),
            )
            account = fetch_one(
                """INSERT INTO trading_accounts (user_id, account_number)
                   VALUES (%s, %s)
                   RETURNING account_id, account_number, balance, currency, status, created_at""",
                (user["user_id"], new_account_number()),
            )
            fetch_one(
                """INSERT INTO portfolios (account_id, name)
                   VALUES (%s, %s) RETURNING portfolio_id""",
                (account["account_id"], "Main Portfolio"),
            )
            _audit(user["user_id"], "client", "REGISTER", "account",
                   str(account["account_id"]), "success")
    except psycopg.errors.DatabaseError as exc:
        if exc.sqlstate == "23505":
            constraint = getattr(exc.diag, "constraint_name", "") or ""
            if constraint == "uq_users_email":
                raise ApiError(409, "EMAIL_EXISTS",
                               "An account with this email already exists.") from None
            raise ApiError(409, "CONFLICT",
                           "That record already exists.") from None
        raise translate_db_error(exc) from None

    token = create_token(user["user_id"], user["role"], user["email"])
    return jsonify({
        "data": {
            "token": token,
            "user": {"user_id": str(user["user_id"]), "email": user["email"],
                     "full_name": user["full_name"], "role": user["role"]},
            "account": {"account_id": str(account["account_id"]),
                        "account_number": account["account_number"],
                        "balance": account["balance"],
                        "currency": account["currency"],
                        "status": account["status"]},
        }
    }), 201


@bp.post("/login")
def login():
    payload = parse(LoginIn, json_body())
    user = fetch_one(
        """SELECT user_id, email, password_hash, full_name, role, is_active
           FROM users WHERE lower(email) = lower(%s)""",
        (payload.email,),
    )

    ok = False
    upgrade_hash = None
    if user and user["is_active"]:
        ok, upgrade_hash = verify_password(user["password_hash"], payload.password)

    if not ok:
        # Audited in its own transaction so the record survives the raised 401.
        _audit_best_effort(user["user_id"] if user else None, None, "LOGIN_FAILED",
                           "user", str(user["user_id"]) if user else payload.email,
                           "failure")
        raise ApiError(401, "INVALID_CREDENTIALS", "Email or password is incorrect.")

    if upgrade_hash:
        # Transparent upgrade of a Phase-1 (werkzeug/scrypt) hash to argon2id.
        # Deliberately not in the same transaction as the audit row, so a failing
        # audit insert cannot roll the re-hash back.
        try:
            with transaction():
                run("UPDATE users SET password_hash = %s WHERE user_id = %s",
                    (upgrade_hash, user["user_id"]))
        except psycopg.errors.DatabaseError:
            current_app.logger.warning("password re-hash upgrade failed for user %s",
                                       user["user_id"], exc_info=True)

    _audit_best_effort(user["user_id"], user["role"], "LOGIN", "user",
                       str(user["user_id"]), "success")

    token = create_token(user["user_id"], user["role"], user["email"])
    return jsonify({
        "data": {
            "token": token,
            "user": {"user_id": str(user["user_id"]), "email": user["email"],
                     "full_name": user["full_name"], "role": user["role"]},
        }
    }), 200


@bp.get("/me")
@auth_required
def me():
    account = fetch_one(
        """SELECT account_id, account_number, balance, currency, status, created_at
           FROM trading_accounts WHERE user_id = %s""",
        (g.user["user_id"],),
    )
    return jsonify({
        "data": {
            "user": {"user_id": str(g.user["user_id"]), "email": g.user["email"],
                     "full_name": g.user["full_name"], "role": g.user["role"]},
            "account": account,
        }
    }), 200

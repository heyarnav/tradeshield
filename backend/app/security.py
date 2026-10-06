"""Authentication, JWT and RBAC helpers.

- argon2 password hashing (with transparent upgrade of the Phase-1 seed hashes)
- HS256 JWT issue/verify
- ``auth_required`` / ``admin_required`` route decorators
"""

from __future__ import annotations

import ipaddress
import secrets
import time
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error
from flask import current_app, g, request

from .db import fetch_one
from .errors import ApiError

_hasher = PasswordHasher()  # argon2id defaults


# --------------------------------------------------------------------------
# passwords
# --------------------------------------------------------------------------
def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored_hash: str, candidate: str) -> tuple[bool, str | None]:
    """Verify a password.

    Returns ``(ok, upgraded_hash)`` -- ``upgraded_hash`` is non-None when the
    stored hash came from the Phase-1 seed (werkzeug/scrypt) and should be
    replaced with an argon2 hash after a successful login.
    """
    if stored_hash.startswith("$argon2"):
        try:
            ok = _hasher.verify(stored_hash, candidate)
        except Argon2Error:
            ok = False
        if not ok:
            return False, None
        try:
            upgrade = _hasher.check_needs_rehash(stored_hash)
        except Argon2Error:
            upgrade = False
        return True, (hash_password(candidate) if upgrade else None)

    # Legacy hash written by Phase 1 seeding (werkzeug scrypt format).
    from werkzeug.security import check_password_hash

    try:
        ok = check_password_hash(stored_hash, candidate)
    except Exception:  # noqa: BLE001 - a malformed hash is simply a failed login
        ok = False
    return ok, (hash_password(candidate) if ok else None)


# --------------------------------------------------------------------------
# JWT
# --------------------------------------------------------------------------
def create_token(user_id: str, role: str, email: str) -> str:
    ttl = int(current_app.config.get("JWT_TTL_HOURS", 8))
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "email": email,
        "iat": now,
        "exp": now + timedelta(hours=ttl),
        "jti": secrets.token_hex(8),
    }
    return jwt.encode(payload, current_app.config["JWT_SECRET"], algorithm="HS256")


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(
            token, current_app.config["JWT_SECRET"], algorithms=["HS256"]
        )
    except jwt.ExpiredSignatureError as exc:
        raise ApiError(401, "TOKEN_EXPIRED", "Your session has expired, please sign in again.") from exc
    except jwt.InvalidTokenError as exc:
        raise ApiError(401, "INVALID_TOKEN", "The authentication token is invalid.") from exc


# --------------------------------------------------------------------------
# decorators
# --------------------------------------------------------------------------
def auth_required(view):
    """Authenticate the request and load the *current* user row into ``g.user``.

    The role is read from the database (not the token) so revoking a role takes
    effect immediately.
    """

    @wraps(view)
    def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        if not header.lower().startswith("bearer "):
            raise ApiError(401, "AUTH_REQUIRED", "Authentication is required.")
        token = header.split(" ", 1)[1].strip()
        if not token:
            raise ApiError(401, "AUTH_REQUIRED", "Authentication is required.")
        payload = decode_token(token)
        user = fetch_one(
            "SELECT user_id, email, full_name, role, is_active "
            "FROM users WHERE user_id = %s",
            (payload.get("sub"),),
        )
        if not user or not user["is_active"]:
            raise ApiError(401, "INVALID_TOKEN", "The authentication token is invalid.")
        g.user = user
        return view(*args, **kwargs)

    return wrapper


def admin_required(view):
    """Require an authenticated user whose database role is ``admin``."""

    @auth_required
    @wraps(view)
    def wrapper(*args, **kwargs):
        if g.user["role"] != "admin":
            raise ApiError(403, "FORBIDDEN", "Administrator privileges are required.")
        return view(*args, **kwargs)

    return wrapper


# --------------------------------------------------------------------------
# request helpers
# --------------------------------------------------------------------------
def json_body() -> dict:
    """Parse the JSON request body.

    Malformed JSON raises a 400 (werkzeug BadRequest, rendered as JSON by the
    app-level HTTPException handler); an absent/empty body yields ``{}`` so
    per-field validation errors can be reported as 422.
    """
    body = request.get_json(silent=False)
    return body if isinstance(body, dict) else {}


def current_account() -> dict:
    """The trading account of the authenticated user (404 if none)."""
    account = fetch_one(
        "SELECT account_id, user_id, account_number, balance, currency, status, created_at "
        "FROM trading_accounts WHERE user_id = %s",
        (g.user["user_id"],),
    )
    if not account:
        raise ApiError(404, "ACCOUNT_NOT_FOUND", "No trading account is associated with this user.")
    return account


def resolve_origin_ip(simulated: str | None = None) -> str:
    """The IP the order is screened against.

    Defaults to the real socket address. The client-supplied ``X-Origin-IP``
    header and the request body's ``origin_ip`` field are honoured **only** when
    TRUST_CLIENT_IP_HEADER is enabled -- that flag is what makes the
    blocked/flagged screening demos runnable from a browser, and turning it on
    anywhere real would let a client choose the address screened against it.
    """
    header_value = None
    if current_app.config.get("TRUST_CLIENT_IP_HEADER"):
        header_value = request.headers.get("X-Origin-IP") or request.headers.get("X-Forwarded-For")
        if header_value:
            header_value = header_value.split(",")[0].strip()
        header_value = header_value or simulated
    value = header_value or request.remote_addr or "0.0.0.0"
    try:
        return str(ipaddress.ip_address(value))
    except ValueError as exc:
        raise ApiError(422, "VALIDATION_ERROR", "origin_ip must be a valid IPv4 or IPv6 address.") from exc


def client_ip() -> str | None:
    """Best-effort caller IP for audit rows (never fails)."""
    try:
        return resolve_origin_ip(None)
    except ApiError:
        return None


def new_account_number() -> str:
    """TS-XXXXXXXX (8 hex chars, unique by construction + DB constraint)."""
    return "TS-" + secrets.token_hex(4).upper()


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

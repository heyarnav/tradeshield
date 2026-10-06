"""Configuration: loads the repo-root .env (same file db/apply.py uses)."""

from __future__ import annotations

import os
import secrets
import warnings
from pathlib import Path

# backend/app/config.py -> parents[0]=app, [1]=backend, [2]=repo root
ROOT = Path(__file__).resolve().parents[2]

# Both loopback spellings must be allowed: Next dev serves the app on whichever
# host you type, and a browser sends that exact Origin in the CORS preflight.
DEFAULT_CORS_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000"


def load_env(path: Path | None = None) -> None:
    """Populate os.environ from .env without overriding existing values."""
    env_file = path or (ROOT / ".env")
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def get_config(overrides: dict | None = None) -> dict:
    load_env()

    # An unset/short JWT secret must never be used to sign tokens: fall back to
    # a random per-process secret (sessions die on restart, but nothing is
    # forgeable). Loudly warn so the real secret gets set in .env.
    secret = os.environ.get("JWT_SECRET", "").strip()
    ephemeral = False
    if len(secret) < 32:
        if secret:
            warnings.warn("JWT_SECRET is shorter than 32 bytes; using an ephemeral "
                          "secret instead. Sessions will not survive a restart.",
                          RuntimeWarning, stacklevel=2)
        secret = secrets.token_urlsafe(48)
        ephemeral = True

    origins = os.environ.get("CORS_ORIGINS", "").strip() or DEFAULT_CORS_ORIGINS

    config = {
        "DATABASE_URL": os.environ.get("DATABASE_URL", ""),
        "JWT_SECRET": secret,
        "JWT_SECRET_IS_EPHEMERAL": ephemeral,
        "JWT_TTL_HOURS": int(os.environ.get("JWT_TTL_HOURS", "8")),
        # Development aid only: lets the browser send the simulated client IP
        # (X-Origin-IP header or the order body field) so the blocked/flagged
        # screening demos work end-to-end. Must stay FALSE anywhere real, or a
        # client could choose the address that gets screened.
        "TRUST_CLIENT_IP_HEADER": os.environ.get(
            "TRUST_CLIENT_IP_HEADER", "false"
        ).lower()
        in ("1", "true", "yes", "on"),
        "CORS_ORIGINS": origins,
        "JSON_SORT_KEYS": False,
        "MAX_CONTENT_LENGTH": 256 * 1024,
    }
    config.update(overrides or {})
    return config

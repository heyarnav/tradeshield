#!/usr/bin/env python3
"""TradeShield * database applier (psycopg3).

Applies db/*.sql in order against DATABASE_URL (Supabase pooler DSN).

Usage:
    python db/apply.py                 # apply 01..06 in order
    python db/apply.py --from 03       # apply from 03 onwards
    python db/apply.py --only 05       # apply a single file
    python db/apply.py --reset         # DROP all TradeShield tables first
    python db/apply.py --status        # show which objects exist

DATABASE_URL is read from the environment or from a .env file at the repo root.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

try:
    import psycopg
    from psycopg import sql as psql_sql
except ImportError:  # pragma: no cover
    sys.exit("psycopg3 is required: pip install 'psycopg[binary]'")

ROOT = Path(__file__).resolve().parent.parent
DB_DIR = ROOT / "db"

ORDER = [
    "01_schema.sql",
    "02_functions.sql",
    "03_triggers.sql",
    "04_views.sql",
    "05_indexes.sql",
    "06_seed.sql",
    "07_blockchain_proofs.sql",
    "07_blockchain_proofs_seed.sql",
]

# Reverse dependency order -- used only by --reset.
DROP = [
    "audit_logs",
    "security_events",
    "transactions",
    "trade_executions",
    "orders",
    "portfolio_holdings",
    "portfolios",
    "instruments",
    "trading_accounts",
    "threat_indicators",
    "threat_sources",
    "users",
]

OBJECT_CHECKS = [
    ("tables", "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'"),
    ("views", "SELECT count(*) FROM information_schema.views WHERE table_schema='public'"),
    ("functions", "SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public'"),
    ("triggers", "SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal"),
    ("indexes", "SELECT count(*) FROM pg_indexes WHERE schemaname='public' AND indexname LIKE 'ix_%'"),
    ("indicators", "SELECT count(*) FROM threat_indicators"),
    ("users", "SELECT count(*) FROM users"),
]


def load_env() -> str:
    """Read DATABASE_URL from the environment or a repo-root .env file."""
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL is not set (export it or add it to .env)")
    return url


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply TradeShield SQL to the database")
    parser.add_argument("--reset", action="store_true", help="drop all TradeShield tables first")
    parser.add_argument("--status", action="store_true", help="print object counts and exit")
    parser.add_argument("--only", help="apply a single file, e.g. 04_views.sql")
    parser.add_argument("--from", dest="start", help="apply from this file onwards, e.g. 03")
    args = parser.parse_args()

    dsn = load_env()

    with psycopg.connect(dsn, autocommit=False) as conn:
        if args.status:
            for label, query in OBJECT_CHECKS:
                try:
                    value = conn.execute(query).fetchone()[0]
                except Exception as exc:  # missing relation => nothing created yet
                    value = f"n/a ({exc.__class__.__name__})"
                print(f"{label:<12} {value}")
            return 0

        if args.reset:
            print("-- resetting: dropping TradeShield tables")
            with conn.transaction():
                conn.execute(
                    "DROP TABLE IF EXISTS "
                    + ", ".join(f"{t} CASCADE" for t in DROP)
                )
            print("   dropped")

        files = ORDER
        if args.only:
            files = [f for f in ORDER if f.startswith(args.only)]
            if not files:
                sys.exit(f"no file matches --only {args.only}")
        elif args.start:
            start = next((i for i, f in enumerate(ORDER) if f.startswith(args.start)), None)
            if start is None:
                sys.exit(f"no file matches --from {args.start}")
            files = ORDER[start:]

        for name in files:
            path = DB_DIR / name
            if not path.exists():
                print(f"!! missing {path}")
                return 1
            began = time.perf_counter()
            with conn.transaction():
                conn.execute(path.read_text())
            print(f"ok  {name:<20} {(time.perf_counter() - began) * 1000:7.1f} ms")

    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

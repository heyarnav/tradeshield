#!/usr/bin/env python3
"""TradeShield * Phase 1 database verification.

Exercises the security trigger, financial trigger, execution function, views
and index usage directly against DATABASE_URL (no Flask involved).

    DATABASE_URL=... python db/verify.py
"""

from __future__ import annotations

import sys
import uuid
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apply import load_env  # noqa: E402  (reads .env / DATABASE_URL)

import psycopg  # noqa: E402

CHECKS: list[tuple[str, bool, object]] = []


def check(name: str, ok: bool, info: object = "") -> None:
    CHECKS.append((name, bool(ok)))
    print(("PASS  " if ok else "FAIL  ") + name + ("" if ok else f"  :: {info}"))


def sqlstate(fn, *args, **kwargs) -> str | None:
    try:
        fn(*args, **kwargs)
        return None
    except psycopg.errors.DatabaseError as exc:
        return exc.sqlstate


def _explain_index(
    conn: psycopg.Connection,
    build_hint_sql: str,
    explain_sql: str,
    index_name: str,
    table_hint: str = "",
    build_params: tuple | list | dict | None = None,
    explain_params: tuple | list | dict | None = None,
) -> tuple[bool, str]:
    """Force a sane plan and check that *index_name* appears in it.

    On a trivially small table PostgreSQL quite correctly prefers a sequential
    scan, which would make a single EXPLAIN assertion flaky. To avoid that we
    temporarily bloat the table (inside a transaction that is rolled back) so a
    seq scan becomes implausible, run ANALYZE, then EXPLAIN. The rollback
    leaves no residue and no audit rows.
    """
    with conn.transaction():
        try:
            if build_hint_sql:
                conn.execute(build_hint_sql, build_params or ())
            conn.execute("ANALYZE " + table_hint)
            cur = conn.execute(
                "EXPLAIN (COSTS OFF) " + explain_sql, explain_params or ())
            plan = "\n".join(r[0] for r in cur.fetchall())
        finally:
            conn.execute("ROLLBACK")
    return index_name in plan, plan


def main() -> int:
    conn = psycopg.connect(load_env(), autocommit=True)
    cur = conn.cursor()

    # deterministic starting point (previous runs may have moved prices)
    cur.execute(
        "UPDATE instruments SET current_price = 175.40 WHERE symbol = 'ACME'"
    )
    cur.execute("SELECT instrument_id FROM instruments WHERE symbol = 'ACME'")
    acme = cur.fetchone()[0]
    cur.execute("SELECT instrument_id FROM instruments WHERE symbol = 'OLD'")
    old = cur.fetchone()[0]

    tag = uuid.uuid4().hex[:8]
    acct = None
    try:
        # ---- fixture: fresh client ------------------------------------------
        cur.execute(
            "INSERT INTO users (email, password_hash, full_name) "
            "VALUES (%s, 'x', 'Verify') RETURNING user_id",
            (f"verify-{tag}@ts.dev",),
        )
        uid = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO trading_accounts (user_id, account_number, balance) "
            "VALUES (%s, %s, 10000.00) RETURNING account_id",
            (uid, f"TS-{tag[:8].upper()}"),
        )
        acct = cur.fetchone()[0]
        cur.execute("INSERT INTO portfolios (account_id) VALUES (%s)", (acct,))

        def order_count() -> int:
            cur.execute(
                "SELECT count(*) FROM orders WHERE account_id = %s", (acct,)
            )
            return cur.fetchone()[0]

        def balance() -> Decimal:
            cur.execute(
                "SELECT balance FROM trading_accounts WHERE account_id = %s", (acct,)
            )
            return cur.fetchone()[0]

        def holding(symbol: str):
            cur.execute(
                """SELECT h.quantity, h.avg_buy_price
                   FROM portfolio_holdings h
                   JOIN instruments i ON i.instrument_id = h.instrument_id
                   JOIN portfolios p ON p.portfolio_id = h.portfolio_id
                   WHERE p.account_id = %s AND i.symbol = %s""",
                (acct, symbol),
            )
            return cur.fetchone()

        def place(side, otype, qty, price=None, ip="10.0.0.5",
                  domain=None, url=None, instrument=None):
            cur.execute(
                """INSERT INTO orders (account_id, instrument_id, side, order_type,
                                      quantity, limit_price, origin_ip,
                                      referrer_domain, referrer_url)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   RETURNING order_id, status, risk_status""",
                (acct, instrument or acme, side, otype, qty, price, ip, domain, url),
            )
            row = cur.fetchone()
            cur.execute("SELECT fn_execute_order(%s)", (row[0],))
            return row, cur.fetchone()[0]

        # ---- 1. normal clear MARKET BUY -------------------------------------
        row, res = place("BUY", "MARKET", 10)
        check("clear MARKET BUY executes",
              bool(res["executed"]) and row[2] == "CLEAR", (row, res))
        check("BUY deducts cash (10000 - 1754.00)",
              balance() == Decimal("8246.00"), balance())
        check("BUY creates holding @ market price",
              holding("ACME") == (Decimal("10.000000"), Decimal("175.4000")),
              holding("ACME"))

        # ---- 2. weighted average cost on second BUY -------------------------
        cur.execute(
            "UPDATE instruments SET current_price = 100.00 WHERE instrument_id = %s",
            (acme,),
        )
        place("BUY", "MARKET", 10)
        expected_avg = Decimal("137.7000")   # (10*175.40 + 10*100.00) / 20
        check("weighted average buy price updated",
              holding("ACME") == (Decimal("20.000000"), expected_avg),
              holding("ACME"))

        # ---- 3. SELL ---------------------------------------------------------
        before = balance()
        row, res = place("SELL", "MARKET", 5)
        q, avg = holding("ACME")
        check("SELL executes and adds cash",
              bool(res["executed"]) and q == Decimal("15.000000")
              and avg == expected_avg
              and balance() == before + Decimal("500.00"),
              (q, avg, balance(), before))

        # ---- 4. insufficient holdings -> TS003, no row ----------------------
        n_before = order_count()
        st = sqlstate(place, "SELL", "MARKET", 999)
        check("insufficient holdings -> TS003 and rollback",
              st == "TS003" and order_count() == n_before, (st, order_count()))

        # ---- 5. insufficient funds -> TS002, no row -------------------------
        st = sqlstate(place, "BUY", "MARKET", 100000)
        check("insufficient funds -> TS002 and rollback",
              st == "TS002" and order_count() == n_before, (st, order_count()))

        # ---- 6. price rules ---------------------------------------------------
        st = sqlstate(place, "BUY", "LIMIT", 1)          # no limit_price
        check("LIMIT without limit_price -> TS006", st == "TS006", st)
        try:
            cur.execute(
                """INSERT INTO orders (account_id, instrument_id, side, order_type,
                                      quantity, limit_price, origin_ip)
                   VALUES (%s,%s,'BUY','MARKET',1,175.00,'10.0.0.5')""",
                (acct, acme),
            )
            st2 = None
        except psycopg.errors.DatabaseError as exc:
            st2 = exc.sqlstate
        check("MARKET with limit_price -> TS006", st2 == "TS006", st2)

        # ---- 7. LIMIT waiting then filling ----------------------------------
        cur.execute(
            "SELECT current_price FROM instruments WHERE instrument_id = %s", (acme,)
        )
        px = cur.fetchone()[0]
        row, res = place("BUY", "LIMIT", 2, price=px - 10)
        check("unsatisfiable LIMIT stays PENDING",
              res["status"] == "PENDING" and row[1] == "PENDING", (row, res))
        cur.execute(
            "UPDATE instruments SET current_price = %s WHERE instrument_id = %s",
            (px - 20, acme),
        )
        cur.execute("SELECT fn_execute_order(%s)", (row[0],))
        res2 = cur.fetchone()[0]
        check("LIMIT fills once price satisfies",
              bool(res2["executed"]) and res2["price"] == px - 20, res2)

        # ---- 8. blocked order ------------------------------------------------
        n_before = order_count()
        st = sqlstate(place, "BUY", "MARKET", 1, ip="198.51.100.66")
        check("critical threat -> TS001, order row never written",
              st == "TS001" and order_count() == n_before, (st, order_count()))
        # Flask's post-rollback persistence:
        cur.execute(
            """INSERT INTO security_events (event_type, severity, indicator_id,
                                            account_id, details)
               VALUES ('ORDER_BLOCKED', 'critical',
                       (SELECT indicator_id FROM threat_indicators
                        WHERE indicator_type='ip' AND value='198.51.100.66'),
                       %s,
                       '{"side":"BUY","quantity":1,"origin_ip":"198.51.100.66"}'::jsonb)""",
            (acct,),
        )
        check("post-rollback security event persists", cur.rowcount == 1)
        cur.execute(
            """INSERT INTO audit_logs (actor_user_id, actor_role, action, entity_type,
                                       ip_address, status)
               VALUES (%s, 'client', 'ORDER_BLOCKED', 'order', '198.51.100.66', 'failure')""",
            (uid,),
        )
        check("post-rollback audit entry persists", cur.rowcount == 1)

        # ---- 9. flagged order -------------------------------------------------
        row, res = place("BUY", "MARKET", 1, domain="promo-trades.io")
        cur.execute(
            "SELECT count(*) FROM security_events "
            "WHERE event_type = 'ORDER_FLAGGED' AND order_id = %s", (row[0],)
        )
        check("medium threat -> order created FLAGGED + event",
              bool(res["executed"]) and row[2] == "FLAGGED"
              and cur.fetchone()[0] == 1, (row, res))

        # ---- 10. expired / disabled / low confidence all allowed --------------
        r1, _ = place("BUY", "MARKET", 1, ip="192.0.2.99")            # expired
        r2, _ = place("BUY", "MARKET", 1, domain="disabled-legacy.example")
        r3, _ = place("BUY", "MARKET", 1, ip="203.0.113.24")          # 45 < 60
        check("expired / inactive / low-confidence indicators allowed",
              r1[2] == "CLEAR" and r2[2] == "CLEAR" and r3[2] == "CLEAR",
              (r1[2], r2[2], r3[2]))

        # ---- 11. financial rules on entities ----------------------------------
        st = sqlstate(place, "BUY", "MARKET", 1, instrument=old)
        check("inactive instrument -> TS005", st == "TS005", st)
        cur.execute(
            "UPDATE trading_accounts SET status = 'suspended' WHERE account_id = %s",
            (acct,),
        )
        st = sqlstate(place, "BUY", "MARKET", 1)
        check("suspended account -> TS005", st == "TS005", st)
        cur.execute(
            "UPDATE trading_accounts SET status = 'active' WHERE account_id = %s",
            (acct,),
        )

        # ---- 12. all application views resolve --------------------------------
        for view in ("vw_active_threats", "vw_portfolio_summary", "vw_order_history",
                     "vw_transaction_history", "vw_blocked_orders",
                     "vw_security_dashboard", "vw_threat_source_summary",
                     "vw_client_trading_stats"):
            try:
                cur.execute(f"SELECT count(*) FROM {view}")
                cur.fetchone()
                ok, info = True, ""
            except Exception as exc:  # noqa: BLE001
                ok, info = False, exc
            check(f"view {view}", ok, info)

        # ---- 13. generic threat lookup (incl. file hash) ----------------------
        cur.execute(
            """SELECT confidence FROM fn_lookup_threat('file_hash',
                 'E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855')"""
        )
        row = cur.fetchone()
        check("fn_lookup_threat resolves file hash",
              row is not None and row[0] == 90, row)

        # ---- 14. GROUP BY / HAVING view --------------------------------------
        cur.execute("SELECT name, active_indicators FROM vw_threat_source_summary")
        rows = cur.fetchall()
        check("threat source summary (GROUP BY + HAVING)",
              len(rows) >= 3 and all(r[1] > 0 for r in rows), rows)

        # ---- 15. index usage on the screening hot path ------------------------
        # A single EXPLAIN on the tiny seeded table is flaky: PostgreSQL quite
        # correctly picks a sequential scan when the whole table fits on one
        # page. To test the index honestly we transiently bloat the table so a
        # seq scan becomes implausible, ANALYZE, EXPLAIN, then roll everything
        # back -- no residue, no audit rows.
        screening_ok, screening_plan = _explain_index(
            conn,
            build_hint_sql="""INSERT INTO threat_indicators
                                  (source_id, indicator_type, value, threat_category,
                                   confidence, first_seen, last_seen, expires_at,
                                   is_active, notes)
                               SELECT source_id, 'ip',
                                      '10.255.' || mod(floor(i / 256)::int, 256) || '.' || mod(i::int, 256),
                                      'recon', 50, now(), now(),
                                      now() + interval '30 days', true,
                                      'transient verify filler'
                               FROM generate_series(1, 20000) AS t(i)
                               CROSS JOIN (SELECT source_id FROM threat_sources LIMIT 1) s
                               WHERE NOT EXISTS (
                                   SELECT 1 FROM threat_indicators
                                   WHERE notes = 'transient verify filler'
                               )""",
            explain_sql="""SELECT * FROM threat_indicators
                            WHERE is_active
                              AND indicator_type = 'ip'
                              AND value = '198.51.100.66'""",
            index_name="ix_indicators_screen",
            table_hint="threat_indicators",
        )
        # The exact (indicator_type, value) lookup is backed by *two* indexes:
        # the UNIQUE constraint uq_indicator_type_value and the partial hot-path
        # index ix_indicators_screen (which additionally skips disabled rows).
        # Either planner choice is correct for this exact lookup; the important
        # property is that a sequential scan is avoided once the table is large.
        screening_index_used = (
            "ix_indicators_screen" in screening_plan
            or "uq_indicator_type_value" in screening_plan
        )
        check("screening lookup uses an index (not a seq scan)",
              screening_index_used, screening_plan)

        # The order list is the application's hottest filtered query. Same
        # honesty treatment: transiently bloat + ANALYZE inside a rolled-back
        # transaction so the planner cannot cheaply seq-scan.
        orders_ok, orders_plan = _explain_index(
            conn,
            build_hint_sql="""INSERT INTO orders (account_id, instrument_id, side,
                                                   order_type, quantity, origin_ip)
                               SELECT %s,
                                      (SELECT instrument_id FROM instruments WHERE symbol = 'ACME'),
                                      'BUY', 'MARKET', 0.000001, '203.0.113.10'
                               FROM generate_series(1, 5000)""",
            explain_sql="""SELECT * FROM orders
                            WHERE account_id = %s
                            ORDER BY placed_at DESC LIMIT 20""",
            index_name="ix_orders_account_placed",
            table_hint="orders",
            build_params=(acct,),
            explain_params=(acct,),
        )
        check("order list uses ix_orders_account_placed", orders_ok, orders_plan)

        # ---- 16. portfolio summary view shows this account --------------------
        cur.execute(
            "SELECT cash_balance, holdings_count, total_equity "
            "FROM vw_portfolio_summary WHERE account_id = %s", (acct,)
        )
        ps = cur.fetchone()
        check("portfolio summary view values",
              ps is not None and ps[1] >= 1, ps)

    finally:
        if acct:
            cur.execute(
                "DELETE FROM trading_accounts WHERE account_id = %s", (acct,)
            )
        cur.execute(
            "DELETE FROM users WHERE email LIKE 'verify-%@ts.dev'"
        )
        # restore seeded price moved while testing LIMIT fills
        cur.execute(
            "UPDATE instruments SET current_price = 175.40, price_updated_at = now() "
            "WHERE symbol = 'ACME' AND current_price <> 175.40"
        )
        conn.close()

    failed = [name for name, ok in CHECKS if not ok]
    print(f"\n{len(CHECKS) - len(failed)}/{len(CHECKS)} checks passed")
    if failed:
        print("failed: " + ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
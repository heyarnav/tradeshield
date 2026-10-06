# TradeShield -- Design Document

Status: **DESIGN PHASE -- awaiting approval.** No implementation code has been written yet.

---

## 1. Architecture

Three tiers, strictly separated. The frontend never talks to the database.

```
????????????????????????        ????????????????????????????        ????????????????????????????
?  Next.js / React / TS?  HTTP  ?  Flask REST API (psycopg3)?  SQL   ?  Supabase PostgreSQL      ?
?  App Router, Tailwind? ?????? ?  JWT auth, RBAC, business ? ?????? ?  constraints, triggers,   ?
?  client-side pages   ?  JSON  ?  logic, audit writer      ?  param ?  functions, views, indexes ?
????????????????????????        ????????????????????????????        ????????????????????????????
```

Responsibilities:

| Layer | Owns |
|---|---|
| Next.js | Presentation, routing, auth token storage, calling the API |
| Flask | Authentication (JWT), authorization (client vs admin, own-rows-only), request validation, orchestration, writing the audit/security event **after** a DB error |
| PostgreSQL | Data integrity (PK/FK/UNIQUE/NOT NULL/CHECK), 3NF design, transactions + row locking, order security screening (BEFORE INSERT trigger), financial validation rules, views, indexes |

Key decisions:

- **JWT bearer auth** (PyJWT), 8-hour expiry, `role` claim (`client` | `admin`). Password hashing with `werkzeug.security` (scrypt/pbkdf2) -- zero extra native dependency.
- **Authorization in Flask**: every client query is scoped by `user_id` derived from the verified JWT, never from request bodies. Admin routes require `role == "admin"`.
- **DB as the enforcement backstop**: even if Flask validation were bypassed, the BEFORE INSERT triggers reject bad/blocked orders.
- **Blocked orders never become rows.** The trigger raises an exception (custom SQLSTATEs); the transaction rolls back; Flask then opens a *new* transaction to persist `security_events` + `audit_logs`.
- Financial values are `NUMERIC(14,2)` (cash) / `NUMERIC(14,4)` (prices) / `NUMERIC(18,6)` (quantities). No floats anywhere.
- Synchronous trading: order insert + execution happen in one database transaction, one HTTP request.
- Config via environment: `DATABASE_URL` (Supabase pooler, psycopg3 DSN), `JWT_SECRET`, `FLASK_PORT` (default 5001), `NEXT_PUBLIC_API_URL` (default `http://localhost:5001/api`).

---

## 2. ER Diagram Structure

Entities (12 tables):

```
users ??1:1?? trading_accounts ??1:1?? portfolios ??1:N?? portfolio_holdings ??N:1?? instruments
                     ?
                     ???1:N?? orders ??N:1?? instruments
                     ?            ?
                     ?            ???1:N?? trade_executions ??1:1?? transactions
                     ?
                     ???(referenced by)?? security_events, audit_logs

threat_sources ??1:N?? threat_indicators
threat_indicators ??(0..1)?? security_events
users ??(0..N)?? audit_logs
```

Textual ER notation (PK / FK / cardinality):

```
[users] 1 ???? 1 [trading_accounts]
[trading_accounts] 1 ???? 1 [portfolios]
[portfolios] 1 ???? N [portfolio_holdings]
[instruments] 1 ???? N [portfolio_holdings]
[trading_accounts] 1 ???? N [orders]
[instruments] 1 ???? N [orders]
[orders] 1 ???? N [trade_executions]
[trade_executions] 1 ???? 1 [transactions]
[threat_sources] 1 ???? N [threat_indicators]
[threat_indicators] 1 ???? 0..N [security_events]
[users] 1 ???? 0..N [audit_logs]
[trading_accounts] 1 ???? 0..N [security_events]
```

---

## 3. Tables and Columns

All PKs are `UUID DEFAULT gen_random_uuid()`. All timestamps are `TIMESTAMPTZ DEFAULT now()`.

### 3.1 `users`
| Column | Type | Constraints |
|---|---|---|
| user_id | UUID | PK |
| email | VARCHAR(255) | NOT NULL, UNIQUE (lowercased) |
| password_hash | VARCHAR(255) | NOT NULL |
| full_name | VARCHAR(100) | NOT NULL |
| role | VARCHAR(10) | NOT NULL DEFAULT 'client', CHECK IN ('client','admin') |
| is_active | BOOLEAN | NOT NULL DEFAULT true |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() |

### 3.2 `trading_accounts`
| Column | Type | Constraints |
|---|---|---|
| account_id | UUID | PK |
| user_id | UUID | NOT NULL, UNIQUE, FK ? users ON DELETE RESTRICT |
| account_number | VARCHAR(12) | NOT NULL, UNIQUE (generated, e.g. `TS-8F3K2A9Q`) |
| balance | NUMERIC(14,2) | NOT NULL DEFAULT 100000.00, CHECK (balance >= 0) |
| currency | CHAR(3) | NOT NULL DEFAULT 'USD' |
| status | VARCHAR(10) | NOT NULL DEFAULT 'active', CHECK IN ('active','suspended','closed') |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() |

*Seeded starting cash = $100,000 simulated.*

### 3.3 `instruments`
| Column | Type | Constraints |
|---|---|---|
| instrument_id | UUID | PK |
| symbol | VARCHAR(12) | NOT NULL, UNIQUE (uppercased) |
| name | VARCHAR(100) | NOT NULL |
| asset_type | VARCHAR(10) | NOT NULL, CHECK IN ('equity','etf','crypto','index') |
| exchange | VARCHAR(16) | NOT NULL |
| current_price | NUMERIC(14,4) | NOT NULL, CHECK (current_price > 0) -- simulated market price |
| tick_size | NUMERIC(10,4) | NOT NULL DEFAULT 0.01, CHECK (tick_size > 0) |
| is_active | BOOLEAN | NOT NULL DEFAULT true |
| price_updated_at | TIMESTAMPTZ | NOT NULL DEFAULT now() |

### 3.4 `portfolios`
| Column | Type | Constraints |
|---|---|---|
| portfolio_id | UUID | PK |
| account_id | UUID | NOT NULL, UNIQUE, FK ? trading_accounts ON DELETE CASCADE |
| name | VARCHAR(50) | NOT NULL DEFAULT 'Main Portfolio' |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() |

### 3.5 `portfolio_holdings`
| Column | Type | Constraints |
|---|---|---|
| holding_id | UUID | PK |
| portfolio_id | UUID | NOT NULL, FK ? portfolio_holdings owner `portfolios` ON DELETE CASCADE |
| instrument_id | UUID | NOT NULL, FK ? instruments ON DELETE RESTRICT |
| quantity | NUMERIC(18,6) | NOT NULL DEFAULT 0, CHECK (quantity >= 0) |
| avg_buy_price | NUMERIC(14,4) | NOT NULL, CHECK (avg_buy_price >= 0) |
| opened_at | TIMESTAMPTZ | NOT NULL DEFAULT now() |
| | | **UNIQUE (portfolio_id, instrument_id)** -- one row per instrument per portfolio |

### 3.6 `orders`
| Column | Type | Constraints |
|---|---|---|
| order_id | UUID | PK |
| account_id | UUID | NOT NULL, FK ? trading_accounts ON DELETE CASCADE |
| instrument_id | UUID | NOT NULL, FK ? instruments ON DELETE RESTRICT |
| side | CHAR(4) | NOT NULL, CHECK IN ('BUY','SELL') |
| order_type | CHAR(6) | NOT NULL, CHECK IN ('MARKET','LIMIT') |
| quantity | NUMERIC(18,6) | NOT NULL, CHECK (quantity > 0) |
| limit_price | NUMERIC(14,4) | NULL, CHECK (limit_price > 0) |
| status | VARCHAR(16) | NOT NULL DEFAULT 'PENDING', CHECK IN ('PENDING','EXECUTED','CANCELLED','REJECTED') |
| risk_status | VARCHAR(8) | NOT NULL DEFAULT 'CLEAR', CHECK IN ('CLEAR','FLAGGED') |
| threat_indicator_id | UUID | NULL, FK ? threat_indicators ON DELETE SET NULL |
| security_note | VARCHAR(255) | NULL -- e.g. `flagged: confidence 72, category phishing` |
| origin_ip | INET | NOT NULL -- supplied by Flask from the request, screened by trigger |
| referrer_domain | VARCHAR(255) | NULL -- optional order context (screened) |
| referrer_url | TEXT | NULL -- optional order context (screened) |
| execution_price | NUMERIC(14,4) | NULL -- fill price snapshot |
| placed_at | TIMESTAMPTZ | NOT NULL DEFAULT now() |
| updated_at | TIMESTAMPTZ | NOT NULL DEFAULT now() |
| | | **CHECK**: `(order_type = 'MARKET' AND limit_price IS NULL) OR (order_type = 'LIMIT' AND limit_price IS NOT NULL)` |

> Blocked orders never appear here -- the trigger aborts before the row exists.

### 3.7 `trade_executions`
| Column | Type | Constraints |
|---|---|---|
| execution_id | UUID | PK |
| order_id | UUID | NOT NULL, FK ? orders ON DELETE CASCADE (1:N allows partial fills later) |
| quantity | NUMERIC(18,6) | NOT NULL, CHECK (quantity > 0) |
| price | NUMERIC(14,4) | NOT NULL, CHECK (price > 0) |
| gross_amount | NUMERIC(14,2) | NOT NULL, CHECK (gross_amount >= 0) |
| executed_at | TIMESTAMPTZ | NOT NULL DEFAULT now() |

*`account_id` deliberately **not** stored here -- it would be transitively derived (`execution ? order ? account`), a 3NF violation. Queries join through `orders` (indexed).*

### 3.8 `transactions` (cash ledger)
| Column | Type | Constraints |
|---|---|---|
| transaction_id | UUID | PK |
| execution_id | UUID | NOT NULL, UNIQUE, FK ? trade_executions ON DELETE CASCADE (1:1) |
| cash_delta | NUMERIC(14,2) | NOT NULL, CHECK (cash_delta <> 0) -- negative for BUY, positive for SELL |
| balance_after | NUMERIC(14,2) | NOT NULL, CHECK (balance_after >= 0) -- historical snapshot |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() |

*Side/type/instrument are derived by joining to `orders` -- shown in `vw_transaction_history`. `balance_after` is an append-only ledger snapshot (a fact about that moment, not a transitive attribute of current state), which is why it is permitted under 3NF.*

### 3.9 `threat_sources`
| Column | Type | Constraints |
|---|---|---|
| source_id | UUID | PK |
| name | VARCHAR(100) | NOT NULL, UNIQUE |
| description | VARCHAR(255) | NULL |
| contact_url | VARCHAR(255) | NULL |
| reliability | SMALLINT | NOT NULL DEFAULT 3, CHECK (reliability BETWEEN 1 AND 5) |
| is_active | BOOLEAN | NOT NULL DEFAULT true |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() |

### 3.10 `threat_indicators`
| Column | Type | Constraints |
|---|---|---|
| indicator_id | UUID | PK |
| source_id | UUID | NOT NULL, FK ? threat_sources ON DELETE RESTRICT |
| indicator_type | VARCHAR(10) | NOT NULL, CHECK IN ('ip','domain','url','file_hash') |
| value | VARCHAR(450) | NOT NULL -- normalized: IP as text, domain lowercased, URL lowercased, hash lowercase hex |
| threat_category | VARCHAR(16) | NOT NULL, CHECK IN ('malware','phishing','c2','botnet','fraud','spam','recon','other') |
| confidence | SMALLINT | NOT NULL, CHECK (confidence BETWEEN 0 AND 100) |
| first_seen | TIMESTAMPTZ | NOT NULL DEFAULT now() |
| last_seen | TIMESTAMPTZ | NOT NULL DEFAULT now(), CHECK (last_seen >= first_seen) |
| expires_at | TIMESTAMPTZ | NULL -- NULL = never expires |
| is_active | BOOLEAN | NOT NULL DEFAULT true |
| notes | VARCHAR(255) | NULL |
| | | **UNIQUE (indicator_type, value)** -- one canonical record per value; a second source merges into it (simplest correct model; a multi-source M:N junction is a noted extension) |

Active & non-expired (the screening predicate): `is_active = true AND (expires_at IS NULL OR expires_at > now())`.

### 3.11 `security_events`
| Column | Type | Constraints |
|---|---|---|
| event_id | UUID | PK |
| event_type | VARCHAR(24) | NOT NULL, CHECK IN ('ORDER_BLOCKED','ORDER_FLAGGED','THREAT_MATCH','AUTH_FAILURE','THREAT_INDICATOR_CHANGED','ORDER_REJECTED') |
| severity | VARCHAR(8) | NOT NULL, CHECK IN ('low','medium','high','critical') |
| indicator_id | UUID | NULL, FK ? threat_indicators ON DELETE SET NULL |
| order_id | UUID | NULL, FK ? orders ON DELETE SET NULL -- **NULL for blocked orders** (no row exists) |
| account_id | UUID | NULL, FK ? trading_accounts ON DELETE SET NULL |
| details | JSONB | NOT NULL DEFAULT '{}' -- attempted order payload, IP, confidence, reason |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() |

### 3.12 `audit_logs`
| Column | Type | Constraints |
|---|---|---|
| audit_id | UUID | PK |
| actor_user_id | UUID | NULL, FK ? users ON DELETE SET NULL (NULL for anonymous/failed login) |
| actor_role | VARCHAR(10) | NULL, CHECK IN ('client','admin','system') |
| action | VARCHAR(40) | NOT NULL -- 'LOGIN','LOGIN_FAILED','REGISTER','ORDER_PLACED','ORDER_BLOCKED','THREAT_CREATE','THREAT_UPDATE','THREAT_DISABLE', >> |
| entity_type | VARCHAR(30) | NULL -- 'order','threat_indicator','account' (polymorphic, so no FK -- documented exception) |
| entity_id | VARCHAR(40) | NULL -- UUID/text of the entity |
| ip_address | INET | NULL |
| status | VARCHAR(8) | NOT NULL, CHECK IN ('success','failure') |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() |

### 3.13 No `blocked_orders` table
Blocked orders are `security_events` rows with `event_type = 'ORDER_BLOCKED'` and the attempted order in `details`. `vw_blocked_orders` presents them as columns.

---

## 4. Relationships / Cardinalities

| Relationship | Cardinality | Optionality | Enforced by |
|---|---|---|---|
| users ? trading_accounts | 1 : 1 | mandatory | UNIQUE(user_id) |
| users ? portfolios (via account) | 1 : 1 | mandatory | UNIQUE(account_id) |
| trading_accounts ? portfolio_holdings | 1 : N | via portfolio | FK portfolio_id |
| instruments ? portfolio_holdings | 1 : N | optional | FK instrument_id |
| trading_accounts ? orders | 1 : N | optional | FK account_id |
| instruments ? orders | 1 : N | optional | FK instrument_id |
| orders ? trade_executions | 1 : N | 1 after execution | FK order_id |
| trade_executions ? transactions | 1 : 1 | mandatory | UNIQUE(execution_id) |
| threat_sources ? threat_indicators | 1 : N | mandatory | FK source_id |
| threat_indicators ? security_events | 1 : 0..N | optional | FK indicator_id |
| users ? audit_logs | 1 : 0..N | optional | FK actor_user_id |

---

## 5. 3NF Reasoning

- **1NF** -- every attribute is atomic: no arrays or repeating groups. Multi-valued threat sources are lifted into `threat_sources` instead of a comma-separated column; `security_events.details` JSONB stores *variable, schema-less event evidence* only (never data needed for joins/lookups), which does not break 1NF in practice for the graded requirements.
- **2NF** -- every table has a single-column surrogate PK (UUID), so no composite keys exist and therefore no partial dependencies.
- **3NF** -- no non-key attribute depends on another non-key attribute. Concrete removals:
  - Instrument name/type/price live in `instruments` -- **not** duplicated on `orders` or `trade_executions`; the order keeps only an `execution_price` snapshot (a fact about that event, not a copy of a mutable attribute used for lookups).
  - `account_id` is **not** stored on `trade_executions` or `transactions` (transitive: execution ? order ? account).
  - `role`, `email` live on `users`, never on `trading_accounts`.
  - `threat_category`/`confidence` live on `threat_indicators`; source metadata (`reliability`) lives on `threat_sources`.
  - Order status is not derivable from another non-key column (it is independent state), so it belongs on `orders`.
- **Documented, justified exceptions**: historical snapshots (`execution_price`, `gross_amount`, `cash_delta`, `balance_after`) describe past events and must not be recomputed from current state -- standard append-only ledger practice.

---

## 6. Order Flow

```
Client POST /api/orders  {side, order_type, quantity, limit_price?, referrer_domain?, referrer_url?}
  ?
  ?? Flask: verify JWT ? user_id, role
  ?? Flask: validate payload (side/type enums, quantity > 0, LIMIT ? limit_price required,
  ?        MARKET ? limit_price must be absent, price > 0, tick-size check)
  ?? Flask: resolve account_id from user_id (never from the body), confirm account exists
  ?
  ?? BEGIN  (psycopg3 connection, autocommit off)
  ?    ?? INSERT INTO orders (...)  ??? BEFORE INSERT trigger #1: SECURITY SCREEN
  ?    ?      * match origin_ip / referrer_domain / referrer_url against active non-expired indicators
  ?    ?      * confidence >= 80  ? RAISE EXCEPTION 'ORDER_BLOCKED'  (SQLSTATE TS001)  ? no row
  ?    ?      * confidence 60-79  ? risk_status='FLAGGED', threat_indicator_id, security_note (row kept)
  ?    ?      * confidence < 60 / no match ? CLEAR
  ?    ?   ??? BEFORE INSERT trigger #2: FINANCIAL VALIDATION
  ?    ?      * account active, instrument active
  ?    ?      * quantity > 0, MARKET/LIMIT price rules
  ?    ?      * BUY  ? balance >= quantity ? price        else RAISE TS002
  ?    ?      * SELL ? holding quantity >= order quantity  else RAISE TS003
  ?    ?
  ?    ?? (only if order will fill now -- MARKET always; LIMIT when price condition met)
  ?    ?      * SELECT ... FROM trading_accounts  FOR UPDATE      ? lock order: account first
  ?    ?      * SELECT ... FROM portfolio_holdings FOR UPDATE      ? then holding (ON CONFLICT upsert)
  ?    ?      * read instrument.current_price (this transaction sees latest committed price)
  ?    ?      * MARKET: fill at current_price
  ?    ?        LIMIT BUY:  fill if current_price <= limit_price
  ?    ?        LIMIT SELL: fill if current_price >= limit_price
  ?    ?        otherwise ? order stays PENDING, commit, return 202-style {status:'PENDING'}
  ?    ?
  ?    ?? BUY execution:  re-check funds under lock ? balance -= gross
  ?    ?      ? upsert holding: new_avg = (q_old*avg_old + q_buy*price) / (q_old + q_buy)
  ?    ?      ? INSERT trade_executions ? INSERT transactions (cash_delta < 0, balance_after)
  ?    ?      ? UPDATE orders SET status='EXECUTED', execution_price=price
  ?    ?? SELL execution: re-check holdings under lock ? holding.quantity -= q
  ?    ?      ? balance += gross (avg_buy_price unchanged)
  ?    ?      ? INSERT trade_executions ? INSERT transactions (cash_delta > 0, balance_after)
  ?    ?      ? UPDATE orders SET status='EXECUTED', execution_price=price
  ?    ?? INSERT audit_logs(action='ORDER_PLACED', status='success')
  ?? COMMIT
  ?
  ?? success ? 201 {order, execution, transaction, holding}
  ?
  ?? psycopg3 raises DatabaseError with custom SQLSTATE
       ? ROLLBACK  (order row / execution / holding / balance changes all vanish)
       ? NEW transaction: INSERT security_events (ORDER_BLOCKED, severity critical,
                           details = attempted order + indicator + confidence)
                          + INSERT audit_logs(action='ORDER_BLOCKED', status='failure')
       ? COMMIT     (audit survives permanently)
       ? 403 {error: {code:'ORDER_BLOCKED', message, indicator_confidence}}
```

Not-matched-but-flagged orders are still created and may execute; they carry `risk_status='FLAGGED'` plus an `ORDER_FLAGGED` security event, and are surfaced on the Blocked/Flagged page.

---

## 7. Security Flow

1. **Ingest**: admin (or demo script) adds indicators via `POST /api/security/indicators`; Flask normalizes the value (lowercase domain/url/hash), then inserts with source, category, confidence, first/last seen, expiry, active flag.
2. **Storage**: indicators live in `threat_indicators` with `source_id` FK to `threat_sources`; screened fields are typed and CHECK-constrained.
3. **Screening policy** (constants in the trigger, documented):

| Condition | Result |
|---|---|
| confidence ? 80, active, not expired | **BLOCK** -- exception, no order row |
| confidence 60-79 | **FLAG** -- order row created with `risk_status='FLAGGED'` + security event |
| confidence < 60 | **ALLOW** -- order proceeds normally |
| inactive or expired | ignored entirely |

4. **Match logic**: highest-confidence active non-expired match across the order's `origin_ip`, `referrer_domain`, `referrer_url`; domain matching uses exact + parent-domain comparison (e.g. `evil.example.com` matches indicator `example.com`). `file_hash` values are screenable through the generic lookup function/admin test endpoint.
5. **Persistence after failure**: because the trigger's exception rolls back same-transaction writes, Flask records the block in a *separate* transaction (security event + audit log) after catching the error -- the order is gone, the evidence is permanent.
6. **AuthN/AuthZ**: JWT with role claim; every client route re-derives `account_id` from the token; admin routes check `role`; SQL is fully parameterized (psycopg3 `%s` placeholders, no string interpolation).
7. **App-level rules in Flask** mirror the DB rules so users get clean 4xx messages instead of SQLSTATEs; the DB remains authoritative.

---

## 8. PostgreSQL Trigger Design

```sql
-- Screening helper: returns the single worst active, non-expired match (or NULL)
CREATE FUNCTION fn_screen_threat(p_ip INET, p_domain TEXT, p_url TEXT)
RETURNS TABLE (indicator_id UUID, confidence SMALLINT, category TEXT, value TEXT)
LANGUAGE sql STABLE AS $$ ... $$;

-- Trigger 1: security screening (runs first -- name sorts first)
CREATE FUNCTION trg_orders_security_screen() RETURNS trigger AS $$
DECLARE v_match RECORD; BEGIN
  SELECT * INTO v_match FROM fn_screen_threat(NEW.origin_ip, NEW.referrer_domain, NEW.referrer_url)
  ORDER BY confidence DESC LIMIT 1;
  IF v_match IS NULL THEN NEW.risk_status := 'CLEAR'; RETURN NEW; END IF;
  IF v_match.confidence >= 80 THEN
    RAISE EXCEPTION 'ORDER_BLOCKED: threat % (%) confidence %',
      v_match.value, v_match.category, v_match.confidence
      USING ERRCODE = 'TS001',
            DETAIL  = json_build_object('indicator_id', v_match.indicator_id,
                                        'confidence', v_match.confidence,
                                        'value', v_match.value)::text,
            HINT    = 'Threat indicator matched; order rejected before insert.';
  ELSIF v_match.confidence >= 60 THEN
    NEW.risk_status := 'FLAGGED'; NEW.threat_indicator_id := v_match.indicator_id;
    NEW.security_note := format('flagged: confidence %s, category %s',
                                v_match.confidence, v_match.category);
  ELSE NEW.risk_status := 'CLEAR'; END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER t1_orders_security_screen
  BEFORE INSERT ON orders
  FOR EACH ROW EXECUTE FUNCTION trg_orders_security_screen();

-- Trigger 2: financial validation (runs second)
CREATE FUNCTION trg_orders_financial_check() RETURNS trigger AS $$
DECLARE v_acct RECORD; v_inst RECORD; v_holding NUMERIC; v_needed NUMERIC;
BEGIN
  SELECT * INTO v_acct FROM trading_accounts WHERE account_id = NEW.account_id;
  IF NOT FOUND THEN RAISE EXCEPTION 'Unknown account' USING ERRCODE='TS004'; END IF;
  IF v_acct.status <> 'active'  THEN RAISE EXCEPTION 'Account not active' USING ERRCODE='TS005'; END IF;
  SELECT * INTO v_inst FROM instruments WHERE instrument_id = NEW.instrument_id;
  IF NOT FOUND OR NOT v_inst.is_active THEN RAISE EXCEPTION 'Instrument not tradable' USING ERRCODE='TS005'; END IF;
  IF NEW.quantity <= 0 THEN RAISE EXCEPTION 'Quantity must be > 0' USING ERRCODE='TS004'; END IF;
  IF NEW.order_type = 'LIMIT' THEN
    IF NEW.limit_price IS NULL OR NEW.limit_price <= 0 THEN
      RAISE EXCEPTION 'LIMIT orders require a positive limit_price' USING ERRCODE='TS006'; END IF;
  ELSE IF NEW.limit_price IS NOT NULL THEN
    RAISE EXCEPTION 'MARKET orders must not carry a limit_price' USING ERRCODE='TS006'; END IF; END IF;

  IF NEW.side = 'BUY' THEN
    v_needed := round(NEW.quantity * COALESCE(NEW.limit_price, v_inst.current_price), 2);
    IF v_acct.balance < v_needed THEN
      RAISE EXCEPTION 'Insufficient funds: need %, have %', v_needed, v_acct.balance
        USING ERRCODE = 'TS002'; END IF;
  ELSE
    SELECT COALESCE(h.quantity,0) INTO v_holding
      FROM portfolios p LEFT JOIN portfolio_holdings h USING (portfolio_id)
      WHERE p.account_id = NEW.account_id AND h.instrument_id = NEW.instrument_id;
    IF COALESCE(v_holding,0) < NEW.quantity THEN
      RAISE EXCEPTION 'Insufficient holdings: need %, have %', NEW.quantity, COALESCE(v_holding,0)
        USING ERRCODE = 'TS003'; END IF;
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER t2_orders_financial_check BEFORE INSERT ON orders
  FOR EACH ROW EXECUTE FUNCTION trg_orders_financial_check();
```

Also: `trg_orders_updated_at()` (BEFORE UPDATE) and `trg_audit_orders()` (AFTER INSERT/UPDATE ? `audit_logs`, `actor_role='system'`).

**Custom SQLSTATEs** let Flask map errors precisely without string matching:

| SQLSTATE | Meaning | HTTP |
|---|---|---|
| TS001 | order blocked by threat | 403 |
| TS002 | insufficient funds | 422 |
| TS003 | insufficient holdings | 422 |
| TS004 | invalid order data | 422 |
| TS005 | inactive account/instrument | 422 |
| TS006 | limit price rule violated | 422 |

---

## 9. Transaction Design

- **Isolation**: `READ COMMITTED` + explicit `SELECT ... FOR UPDATE` row locks (adequate and easy to reason about; `SERIALIZABLE` noted as an alternative).
- **Lock ordering (deadlock-free)**: `trading_accounts` ? `portfolio_holdings` ? `instruments` (read). Always the same order in every code path.
- **Atomic unit**: order insert, funds/holdings update, execution row, transaction row, order status, audit row -- one `BEGIN >> COMMIT`. Any failure ? `ROLLBACK` ? *nothing* changed (demonstrates rollback).
- **Double-spend prevention**: the funds/holdings check happens twice -- inside the BEFORE INSERT trigger (fast fail) and again after `FOR UPDATE` (authoritative, under lock). Two concurrent BUYs serialize on the account row.
- **Weighted average cost** is recomputed inside the locked update: `avg = (q_old*avg_old + q_new*price) / (q_old + q_new)`, rounded to 4 dp.
- **Holding cleanup**: SELL reduces quantity; a holding reaching exactly 0 keeps its row (history preserved), CHECK allows 0.
- **Audit after rollback**: security event + audit log are written in a fresh transaction *after* Flask handles the exception, so they survive.

---

## 10. API Structure

Base: `http://localhost:5001/api`. All responses `{data: >>}` or `{error: {code, message}}`. Auth header: `Authorization: Bearer <jwt>`.

| Method | Path | Access | Purpose |
|---|---|---|---|
| GET | `/health` | public | liveness + DB ping |
| POST | `/auth/register` | public | create user + account + portfolio, return JWT |
| POST | `/auth/login` | public | verify credentials, return JWT |
| GET | `/auth/me` | any authed | current user + role |
| GET | `/account` | client (own) | balance, status, account number, equity |
| GET | `/instruments` | authed | list instruments (optional `?asset_type=`) |
| GET | `/instruments/<id>` | authed | instrument detail + current price |
| GET | `/portfolio` | client (own) | portfolio summary (cash, market value, P&L) |
| GET | `/portfolio/holdings` | client (own) | holdings with live valuation |
| GET | `/orders` | client (own) | orders (`?status=&limit=`) |
| POST | `/orders` | client (own) | place order (screening + execution) |
| GET | `/orders/<id>` | client (own) | order detail + executions |
| GET | `/transactions` | client (own) | transaction history |
| GET | `/security/indicators` | admin | list (`?type=&active=&q=`) |
| POST | `/security/indicators` | admin | create indicator (+ audit) |
| PATCH | `/security/indicators/<id>` | admin | edit / disable / re-enable (+ audit) |
| GET | `/security/sources` * POST | admin | threat sources CRUD-lite |
| GET | `/security/dashboard` | admin | counts, blocked/flagged, top sources, recent events |
| GET | `/security/blocked-orders` | admin | blocked + flagged orders view |
| GET | `/security/events` | admin | security event feed |
| GET | `/security/audit-logs` | admin | audit trail (`?action=&actor=&since=`) |
| GET | `/security/lookup?value=>>&type=>>` | admin | test a value against indicators |

Error codes returned to the client mirror the SQLSTATE table plus `UNAUTHORIZED`, `FORBIDDEN`, `NOT_FOUND`, `VALIDATION_ERROR`, `CONFLICT`.

---

## 11. Next.js Page Structure

App Router + TypeScript + Tailwind (dark fintech theme), client-side data fetching with a shared `lib/api.ts` (fetch wrapper, token in `localStorage`, 401 ? redirect to login).

```
app/
??? layout.tsx                 # fonts, theme, AuthProvider, Toaster
??? page.tsx                   # redirect ? /dashboard or /login
??? (auth)/
?   ??? login/page.tsx         # split-screen brand + form
?   ??? register/page.tsx
??? (app)/                     # guarded shell: sidebar + topbar + command bar
?   ??? layout.tsx             # role-aware nav (client items / admin section)
?   ??? dashboard/page.tsx     # equity, cash, P&L, holdings mix, recent orders
?   ??? market/page.tsx        # instrument table, quote cards, quick-buy
?   ??? portfolio/page.tsx     # holdings + allocation + unrealized P&L
?   ??? orders/page.tsx        # order list + place-order drawer (BUY/SELL/MARKET/LIMIT)
?   ??? transactions/page.tsx  # ledger with signed amounts & running balance
?   ??? account/page.tsx       # profile, balance, account status
??? (admin)/
    ??? layout.tsx             # admin shell, threat-orange accent
    ??? security/page.tsx      # security dashboard (KPIs, feeds)
    ??? threats/page.tsx       # indicator table: add/edit/disable modal
    ??? blocked/page.tsx       # blocked + flagged orders with reason/confidence
    ??? audit/page.tsx         # audit log table with filters
```

Shared components: `StatCard`, `DataTable` (sort/filter/paginate), `Badge` (risk status colors: CLEAR green, FLAGGED amber, BLOCKED red), `OrderTicket` (buy/sell form with live cost preview), `Sparkline`/`AreaChart` (equity curve), `Modal`, `Toast`, `EmptyState`. Every table, badge and chart uses one design-token palette so the product reads as a single system.

---

## 12. Project Folder Structure

```
tradeshield/
??? README.md
??? docs/
?   ??? DESIGN.md                  # this document
?   ??? ER_DIAGRAM.md              # mermaid ER diagram
?   ??? SCHEMA.md                  # relational schema + normalization notes
?   ??? API.md                     # endpoint reference
?   ??? TESTING.md
?   ??? DBMS_DEMONSTRATION.md      # walkthrough of the 12 demo scenarios
??? db/
?   ??? apply.sql                  # or apply.sh -- runs files in order against DATABASE_URL
?   ??? 01_schema.sql              # tables + PK/FK/UNIQUE/CHECK/NOT NULL
?   ??? 02_functions.sql           # fn_screen_threat, execution helpers
?   ??? 03_triggers.sql
?   ??? 04_views.sql
?   ??? 05_indexes.sql
?   ??? 06_seed.sql                # admin, demo client, instruments, sources, indicators
?   ??? demo/
?   ?   ??? 01_normal_order.sql >> 12_index_explain.sql   # 12 demonstration scripts
?   ?   ??? run_all.sql
?   ??? queries/
?       ??? analytics.sql          # joins, GROUP BY/HAVING, subqueries, CTEs
??? backend/
?   ??? app/
?   ?   ??? __init__.py            # app factory, CORS, error handlers
?   ?   ??? config.py  db.py  errors.py
?   ?   ??? middleware/auth.py     # JWT verify, require_role
?   ?   ??? routes/                # auth, account, instruments, portfolio,
?   ?                              # orders, transactions, security
?   ??? tests/                     # pytest (auth, authz, orders, security, rollback)
?   ??? requirements.txt           # flask, psycopg[binary], PyJWT, pytest, python-dotenv
?   ??? run.py
??? frontend/
    ??? app/  components/  lib/  public/  styles/
    ??? package.json               # next, react, typescript, tailwindcss
    ??? tsconfig.json
```

---

## Demonstration & Test Coverage Mapping (Phase 5/6 targets)

Demo scripts: normal order * blocked order * flagged order * insufficient funds * insufficient holdings * successful trade * rollback * portfolio update * threat lookup * audit history * views * `EXPLAIN ANALYZE` index usage.

Pytest: registration * login * authorization (cross-account access denied) * order validation * LIMIT price requirement * insufficient funds * insufficient holdings * successful BUY * successful SELL * blocked order (403 + no order row + security event exists) * flagged order (created with `risk_status='FLAGGED'`) * audit logging * rollback (no partial writes) * portfolio updates (quantity + weighted average).

Analytics queries exercised in `db/queries/analytics.sql`: multi-table joins, `GROUP BY`/`HAVING` (e.g. sources with > 1 high-confidence indicator), correlated subqueries (client's last order per instrument), CTEs (running portfolio equity), window functions for order sequences, and `EXPLAIN ANALYZE` on the order-screening and order-history queries against the real indexes.

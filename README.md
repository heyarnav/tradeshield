# TradeShield - Investment Trading DBMS

A full-stack multi-user investment trading platform built around a **PostgreSQL**
database, with a **Flask** JSON API and a **Next.js** admin/client dashboard.

This project is a learning/portfolio piece focused on **database engineering**:
normalization, constraints, transactions, concurrency control, triggers,
functions, and performance indexing - all exposed through a small but real
application.

---

## What it does

TradeShield lets authenticated users:

- log in and keep a session via **JWT** cookies,
- trade a small set of instruments (**BUY / SELL**, market or limit orders),
- watch a live **market** with prices that update periodically,
- view their **portfolio** and **transactions**,
- and (for admins) monitor **security**: threat indicators, blocked orders,
  and an immutable audit log.

The application ships with **seed data** so it works out of the box:
two demo accounts (`client@tradeshield.dev` / `Client@123` and
`admin@tradeshield.dev` / `Admin@123`), a handful of instruments, market
prices, an opening position for the client, and a small threat-intelligence
feed.

The important part is not the UI - it is what the database does and why.

---

## Architecture

```
                 +---------------------+
   Browser       |   Next.js (React)   |   port 3000
   (Playwright)  |   admin + client UI |
                 +----------+----------+
                            |  REST /api/**   (NEXT_PUBLIC_API_URL)
                            v
                 +---------------------+
   Tests / LAN   |   Flask (Python)    |   port 5001
                 |   JSON API          |
                 +----------+----------+
                            |  psycopg
                            v
                 +---------------------+
   Supabase      |   PostgreSQL 16     |
                 |   (managed, pooled) |
                 +---------------------+
```

### Backend - Flask

- `backend/run.py` - small runner that loads `.env`, builds the app, and serves
  it on `FLASK_PORT` (default 5001).
- `backend/app/__init__.py` - app factory; registers the blueprints and
  configures middleware (CORS, JWT, IP resolution, error handling).
- `backend/app/config.py` - settings from environment/`.env`, including
  `DATABASE_URL`, `JWT_SECRET`, `TRUST_CLIENT_IP_HEADER`, and
  `ALLOWED_DEV_ORIGINS`.
- `backend/app/routes/*.py` - blueprints for **auth**, **orders**,
  **portfolio**, **transactions**, **market**, **admin**, **security**.
- `backend/app/security.py` - threat screening: every order is checked against
  active threat indicators, and a blocked order is **rolled back financially**
  while **preserving a security_event + audit_log** record.
- `backend/app/db.py` - small DB helper with a thread-local connection factory.
- `backend/app/errors.py` - standard error shapes (`{"error": {"code", "detail"}}`).
- `backend/app/schemas.py` - shared DTOs for order, account, position DTOs, etc.

### Frontend - Next.js

- `frontend/` - Next.js app (App Router) with separate client and admin areas.
- The API base URL is injected at build time via `NEXT_PUBLIC_API_URL`
  (default `http://localhost:5001/api`), wired through `next.config.mjs`.
- Pages: dashboard, market, portfolio, transactions, orders, account/login,
  and admin pages for security, threat indicators, blocked orders, and audit
  logs.

### Database - PostgreSQL (managed via Supabase)

See [Database](README.md#database) below. The schema lives in
`db/01_schema.sql` through `db/06_demo_and_indexes.sql` and is applied in order
by `db/apply.py`.

### Test tiers

- **Backend pytest** - unit + integration tests against the real DB
  (`backend/tests/`), run with `backend/.venv/bin/pytest`.
- **DB verification** - `db/verify.py` checks schema, row counts, integrity,
  and that the right indexes are being used.
- **Frontend typecheck + build** - `tsc --noEmit` and `next build`.
- **E2E (Playwright)** - `backend/tests/test_e2e_playwright.py` drives a real
  browser against the real Flask + Next.js servers.

---

## Database

TradeShield's database is the heart of the project. The design emphasis is on
**correctness** and **defense in depth** rather than cleverness.

### ER overview

| area | tables | notes |
|---|---|---|
| Authentication | `users`, `sessions` | email unique, hashed passwords, JWT session cookies |
| Accounts | `trading_accounts` | one account per user, balance in minor units / positional value |
| Market | `instruments`, `prices` | instruments reference a risk class; prices are the live feed |
| Trading | `orders`, `positions` | orders flow through PENDING -> MATCHING -> EXECUTED / REJECTED / BLOCKED |
| Threat intel | `threat_sources`, `threat_indicators` | linked indicators; `is_active` toggles without deleting |
| Security / audit | `security_events`, `audit_logs` | **append-only** records of blocked orders and admin actions |

See `db/01_schema.sql` for exact column definitions and foreign-key
relationships.

### Normalization

The schema is normalized to avoid update anomalies:

- **1NF** - scalar columns, no repeating groups. Things like order line items
  or position history are their own rows, not comma-separated lists.
- **2NF** - every non-key column depends on the whole key. For example,
  `positions` carries `instrument_id` + `account_id` as its key and nothing
  else that is partially dependent on just one of them.
- **3NF** - no non-key column depends on another non-key column. Prices belong
  to `prices` (per instrument, per tick), not duplicated onto `orders`. Risk
  class metadata belongs to `instruments`, not copy-pasted into every order.

The practical upshot: updating a risk class, an instrument price, or a user's
email touches one row in one table, not a scatter of copies.

### Key constraints used

- **PRIMARY KEYs** on every table.
- **UNIQUE** on `users.email`, `trading_accounts.user_id` (one account per
  user), and `threat_indicators(indicator_type, value)` (no duplicate
  indicators from any source).
- **FOREIGN KEYs** everywhere it matters: orders -> account + instrument,
  positions -> account + instrument, security/audit rows -> account + user,
  threat indicators -> source.
- **`ON DELETE RESTRICT`** on the user -> account link so an account can't be
  deleted while a user still references it, and **`ON DELETE SET NULL`** on
  the `security_events.indicator_id` link so a removed indicator doesn't delete
  historical security evidence.
- A **CHECK** on order quantities (`> 0`) and a check on traded instruments
  that rejects the set of **restricted symbols** hardcoded in the DB layer.

### Transactions and isolation

All trading writes happen inside explicit transactions:

- **Order execution** is one transaction: validate balance/holdings, debit or
  credit cash, insert the order, and adjust the position. If any step fails,
  the whole thing rolls back and nothing is left half-done.
- **Blocked orders** take this further: the financial side is rolled back, and
  the security evidence (a `security_events` row + an `audit_logs` row) is
  written in a **separate** post-rollback transaction so a failure to record
  the block never silently loses the financial rollback.
- Reads that must be consistent with the current balance/holdings use the
  right isolation level and row-level locking where concurrency matters.

See `backend/app/routes/orders.py` and `backend/app/security.py` for the
concrete flow.

### Concurrency control

The orders path has real concurrency guards - this was found and fixed during
development:

- Concurrent BUYs against the same account are serialized at the **row level**
  on the trading account row, so two simultaneous BUYs do not both read the
  same balance and both succeed when only one should. Before the fix, concurrent
  BUY attempts could deadlock or both pass; after the fix the pattern is
  **one success + one insufficient-funds rejection**, deterministically.
- Position updates on SELL are guarded so a sale can't print a negative holding.

This is not simulated - it is enforced by the database via `SELECT ... FOR UPDATE`
and transactional write ordering in the orders blueprint.

### Triggers and functions

The database layer includes server-side logic where it belongs:

- **Audit logging**: admin actions and security-relevant events are written to
  `audit_logs` / `security_events` through DB-level logic so the record exists
  even if the application layer has a transient problem recording it.
- **Derived / invariant enforcement**: where a value must always stay consistent
  with other rows (for example position arithmetic), the DB helps enforce it
  rather than trusting every caller to get it right.
- **Restricted-symbol enforcement**: the set of restricted symbols that cannot
  be traded is enforced in the database layer, not just in the API.

See `db/*.sql` for the concrete trigger/function definitions. The project
documents each one near its definition.

### Performance indexing

Indexes exist where queries actually need them:

- **Threat screening** (the hot path on every order): a **partial index**
  `ix_indicators_screen` on `threat_indicators(indicator_type, value)`
  `WHERE is_active`, so screening only scans active indicators. The
  `UNIQUE(indicator_type, value)` constraint already covers exact lookups, so
  this partial index's value is skipping disabled rows entirely.
- **Portfolio / order history**: supporting indexes on the account + timestamp
  ordering used by the portfolio and transactions feeds.

`db/verify.py` checks that these indexes exist and that the planner actually
uses them on representative queries, with a note about when index usage is
expected vs. environment-dependent.

### Why PostgreSQL?

PostgreSQL is the right tool here because the project leans on things it does
well: **strong ACID transactions, row-level locking, partial indexes, CHECK
constraints, triggers/functions, and JSONB for semi-structured security detail**.
A trading app with correctness and audit requirements is a good fit for a
relational DB with these features, and PostgreSQL gives them without needing a
separate cache or queue for this scale.

---

## API

The API is a JSON REST API under `/api/...`. All authenticated routes expect a
**Bearer token** from login, sent as a cookie by the frontend.

### Auth

- `POST /api/auth/register` - create an account (`email`, `password`,
  `full_name`). Returns user + account info.
- `POST /api/auth/login` - log in with email + password. Returns a JWT token.
- `POST /api/auth/logout` - end the session.

### Orders

- `POST /api/orders` - place an order (`instrument`, `side`, `order_type`,
  `quantity`, optional `limit_price`). Market buys/sells execute immediately
  against the account balance/holdings; limit orders are placed pending the
  market hitting the price.

### Portfolio / transactions

- Portfolio and transactions endpoints reflect executed trades and current
  holdings.

### Admin / security (admin only)

- Threat indicators, blocked orders, and audit logs are readable from the admin
  security pages and the corresponding admin API routes.

### Error shape

Errors are returned as:

```json
{
  "error": {
    "code": "INSUFFICIENT_FUNDS",
    "detail": "..."
  }
}
```

Common codes: `VALIDATION_ERROR`, `INSUFFICIENT_FUNDS`,
`INSUFFICIENT_HOLDINGS`, `LIMIT_PRICE_REQUIRED`, `ORDER_BLOCKED`,
`UNAUTHORIZED`, `FORBIDDEN`.

---

## Getting started

### Prerequisites

- **Node** (for the Next.js frontend) and **npm** in the frontend directory.
- **Python 3** and a virtualenv in `backend/` with the dependencies in
  `backend/requirements.txt` installed.
- A **PostgreSQL** database reachable via `DATABASE_URL` in `.env`. The project
  is developed against a **Supabase** managed database.

### 1. Environment

Copy `.env` (or create one) and set at least:

```
DATABASE_URL=postgresql://...?sslmode=require
JWT_SECRET=<a long random secret>
FLASK_PORT=5001
TRUST_CLIENT_IP_HEADER=false
ALLOWED_DEV_ORIGINS=http://localhost:3000
NEXT_PUBLIC_API_URL=http://localhost:5001/api
```

Notes:

- `TRUST_CLIENT_IP_HEADER=true` makes the app trust a `X-Originating-IP` /
  similar header from the proxied request for threat screening. The safe default
  for local development and demos is **`false`**.
- `ALLOWED_DEV_ORIGINS` controls dev-server CORS for the LAN / demo case; it is
  not needed for the normal `localhost:3000` -> `localhost:5001` flow.

### 2. Apply the database schema

From the repo root:

```
python db/apply.py
```

This applies `db/01_schema.sql` through `db/06_demo_and_indexes.sql` in order.
The applier is idempotent-ish for the demo/data files (it skips objects that
already exist) and reports what it did. Re-running it is the intended way to
recover a fresh database.

### 3. Seed / demo state

The last DB file applies demo data: instruments, prices, a small threat feed
(including the known-bad IP `198.51.100.66`), and the two demo accounts with
an opening position for the client. After applying, the app is ready to demo
immediately.

Demo credentials:

- **Client**: `client@tradeshield.dev` / `Client@123`
- **Admin**: `admin@tradeshield.dev` / `Admin@123`

### 4. Run the backend

From `backend/`:

```
.venv/bin/python run.py
```

It listens on `FLASK_PORT` (default 5001) and exposes `/api/health`.

### 5. Run the frontend

From `frontend/`:

```
npm run dev
```

It serves the dashboard + admin UI on port 3000.

---

## Running the demos

Two demo flows are the easiest way to see the system doing real work:

### Client trade flow

1. Log in as `client@tradeshield.dev`.
2. Open **Market** and confirm instruments appear (e.g. ACME).
3. Open **Orders** -> **New order** -> buy a small number of ACME (market).
4. Confirm the order executes and the **Portfolio** now lists ACME.
5. Sell some ACME and confirm the holding drops.
6. Try a buy you can't afford - expect an **insufficient funds** rejection with
   a clear error code, not a crash.
7. Try to sell more than you hold - expect an **insufficient holdings**
   rejection.

### Admin security flow

1. Log in as `admin@tradeshield.dev`.
2. Open **Security dashboard** - overview of recent security events.
3. Open **Threat indicators** - the seeded feed, including the known-bad IP
   `198.51.100.66`.
4. Open **Blocked orders** - orders that were blocked by screening.
5. Open **Audit logs** - the append-only admin/security record.

The blocked-order demo is most convincing when the screened IP is a known threat
and `TRUST_CLIENT_IP_HEADER` is configured so that IP is actually screened. With
the safe default (`false`), a blocked order cannot be triggered from a normal
browser run because the browser cannot spoof the screened IP; the API contract
is still tested in the E2E suite directly.

---

## Testing

There are four test tiers. All of them are meant to be runnable from the repo
root.

### Backend pytest (unit + integration)

```
cd backend
.venv/bin/python -m pytest backend/tests -q
```

These run against the real DB configured in `.env`. Each test user is created
through the public API with a unique `@tradeshield.test` address and cleaned up
after the session, along with any indicator/source the suite created.

### DB verification

```
cd <repo root>
python db/verify.py
```

Checks schema, row counts, integrity constraints, and index usage on
representative queries.

### Frontend typecheck + build

From `frontend/`:

```
npm run typecheck   # tsc --noEmit
npm run build       # next build
```

### E2E (Playwright)

The E2E suite starts Flask and the Next.js dev server, awaits both health
checks, and then drives a headless Chromium through the real UI + API.

```
cd backend
.venv/bin/python -m pytest backend/tests/test_e2e_playwright.py -q
```

The suite is skipped (not failed) when the browser or servers can't be reached,
so it doesn't break a pipeline purely for environment reasons. It uses the
documented demo credentials and asserts against visible UI and HTTP responses,
not internal implementation details.

### One-command runs

For convenience, the backend has `run_e2e.sh`, which runs the E2E suite from one
shell (the pytest fixture itself owns the Flask + Next.js lifecycle).

```
bash backend/run_e2e.sh
```

---

## Project structure

```
.
+-- .env                      # environment (DATABASE_URL, JWT_SECRET, ...)
+-- db/
|   +-- apply.py              # applies 01..06 in order
|   +-- verify.py             # schema / integrity / index-usage checks
|   +-- 01_schema.sql         # tables, constraints, FKs
|   +-- ...                   # constraints, indexes, demo data
|   +-- demo/                 # (demo SQL if split out)
+-- backend/
|   +-- run.py                # Flask runner
|   +-- app/
|   |   +-- __init__.py       # app factory
|   |   +-- config.py         # settings
|   |   +-- db.py             # connection helper
|   |   +-- errors.py         # error shapes
|   |   +-- schemas.py        # shared DTOs
|   |   +-- security.py       # threat screening + blocked-order handling
|   |   +-- routes/           # auth, orders, portfolio, transactions, ...
|   +-- tests/                # pytest suite (unit + integration + E2E)
+-- frontend/                 # Next.js app
+-- README.md                 # this file

## Project structure

```
.
+-- .env                      # environment (DATABASE_URL, JWT_SECRET, ...)
+-- db/
|   +-- apply.py              # applies 01..06 in order
|   +-- verify.py             # schema / integrity / index-usage checks
|   +-- 01_schema.sql         # tables, constraints, FKs
|   +-- ...                   # constraints, indexes, demo data
|   +-- demo/                 # (demo SQL if split out)
+-- backend/
|   +-- run.py                # Flask runner
|   +-- app/
|   |   +-- __init__.py       # app factory
|   |   +-- config.py         # settings
|   |   +-- db.py             # connection helper
|   |   +-- errors.py         # error shapes
|   |   +-- schemas.py        # shared DTOs
|   |   +-- security.py       # threat screening + blocked-order handling
|   |   +-- routes/           # auth, orders, portfolio, transactions, ...
|   +-- tests/                # pytest suite (unit + integration + E2E)
+-- frontend/                 # Next.js app
+-- README.md                 # this file
```

---

## Implementation notes / trade-offs

- **Seed data is real, not mock**: the demo accounts, instruments, prices, and
  threat feed are applied to the real DB so the app is demoable immediately and
  the E2E suite can log in as known users.
- **Security evidence is append-only**: blocked-order and admin-audit records
  are written in a way that survives financial rollbacks, so an admin can always
  see what was blocked and why.
- **Threat screening is a DB-backed hot path**: it runs on every order and is
  indexed for the active-indicator case; the implementation details live in
  `backend/app/security.py` and the matching indexes in `db/*.sql`.
- **Concurrency was validated, not assumed**: the orders path was stress-tested
  for concurrent BUYs and corrected until concurrent attempts produced the
  correct one-success + one-rejection outcome rather than deadlocks or double
  spends.

---

## Limitations / known non-goals

- This is a learning/portfolio project, not a production trading system.
- One account per user, a small fixed instrument set, and simplified pricing.
- The LAN / multi-device demo case needs `ALLOWED_DEV_ORIGINS` configured;
  the default local flow does not.
- Automated frontend unit tests are not in scope for this phase; coverage lives
  in the backend pytest suite and the Playwright E2E suite.

---

## Phase status

As of the latest verification pass:

- Backend pytest (backend/tests, excluding E2E): passing.
- DB verification (`db/verify.py`): 31/31 checks passing.
- Frontend typecheck (`tsc --noEmit`): passing.
- Frontend production build (`next build`): passing.
- E2E (Playwright, real browser + live DB, single-command `run_e2e.sh`): the
  suite is structurally healthy and runs in one command; under the default safe
  `TRUST_CLIENT_IP_HEADER=false` configuration some browser-driven assertions
  are skipped because the browser cannot spoof the screened IP. The blocked-order
  API contract is still validated directly in the E2E suite.

The system is demo-ready from a freshly applied database using the documented
demo credentials.

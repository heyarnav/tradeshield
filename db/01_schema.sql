-- ============================================================================
-- TradeShield * 01_schema.sql
-- Financial + security schema: entities, PKs, FKs, UNIQUE, NOT NULL, CHECK.
-- Normalized to 3NF (see docs/DESIGN.md sec5).
-- Apply order: 01_schema -> 02_functions -> 03_triggers -> 04_views
--              -> 05_indexes -> 06_seed        (use db/apply.py)
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid(); builtin since PG13

-- ----------------------------------------------------------------------------
-- 1. users -- identity & roles (account data lives in trading_accounts)
-- ----------------------------------------------------------------------------
CREATE TABLE users (
    user_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email          VARCHAR(255) NOT NULL,
    password_hash  VARCHAR(255) NOT NULL,
    full_name      VARCHAR(100) NOT NULL,
    role           VARCHAR(10)  NOT NULL DEFAULT 'client'
                   CHECK (role IN ('client', 'admin')),
    is_active      BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT uq_users_email      UNIQUE (email),
    CONSTRAINT ck_users_email_fmt  CHECK (email ~* '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$')
);

-- ----------------------------------------------------------------------------
-- 2. threat_sources -- indicator provenance stored separately (not on indicators)
-- ----------------------------------------------------------------------------
CREATE TABLE threat_sources (
    source_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name         VARCHAR(100) NOT NULL,
    description  VARCHAR(255),
    contact_url  VARCHAR(255),
    reliability  SMALLINT     NOT NULL DEFAULT 3
                 CHECK (reliability BETWEEN 1 AND 5),
    is_active    BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT uq_threat_sources_name UNIQUE (name)
);

-- ----------------------------------------------------------------------------
-- 3. threat_indicators -- IP / domain / URL / file hash intelligence
--    Screening predicate: is_active AND (expires_at IS NULL OR expires_at > now())
-- ----------------------------------------------------------------------------
CREATE TABLE threat_indicators (
    indicator_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id       UUID NOT NULL,
    indicator_type  VARCHAR(10)  NOT NULL
                    CHECK (indicator_type IN ('ip', 'domain', 'url', 'file_hash')),
    value           VARCHAR(450) NOT NULL,
    threat_category VARCHAR(16)  NOT NULL
                    CHECK (threat_category IN
                           ('malware','phishing','c2','botnet','fraud','spam','recon','other')),
    confidence      SMALLINT     NOT NULL CHECK (confidence BETWEEN 0 AND 100),
    first_seen      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    last_seen       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ,
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
    notes           VARCHAR(255),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT fk_indicators_source
        FOREIGN KEY (source_id) REFERENCES threat_sources (source_id) ON DELETE RESTRICT,
    CONSTRAINT uq_indicator_type_value UNIQUE (indicator_type, value),
    CONSTRAINT ck_indicator_last_seen CHECK (last_seen >= first_seen)
);

-- ----------------------------------------------------------------------------
-- 4. trading_accounts -- 1:1 with users, holds the cash balance
-- ----------------------------------------------------------------------------
CREATE TABLE trading_accounts (
    account_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        UUID NOT NULL,
    account_number VARCHAR(12)  NOT NULL,
    balance        NUMERIC(14,2) NOT NULL DEFAULT 100000.00
                   CHECK (balance >= 0),
    currency       CHAR(3)      NOT NULL DEFAULT 'USD' CHECK (currency ~ '^[A-Z]{3}$'),
    status         VARCHAR(10)  NOT NULL DEFAULT 'active'
                   CHECK (status IN ('active', 'suspended', 'closed')),
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT uq_accounts_user      UNIQUE (user_id),
    CONSTRAINT uq_accounts_number    UNIQUE (account_number),
    CONSTRAINT fk_accounts_user      FOREIGN KEY (user_id)
                                     REFERENCES users (user_id) ON DELETE RESTRICT
);

-- ----------------------------------------------------------------------------
-- 5. instruments -- simulated market data (price lives here, never on orders)
-- ----------------------------------------------------------------------------
CREATE TABLE instruments (
    instrument_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol           VARCHAR(12)  NOT NULL,
    name             VARCHAR(100) NOT NULL,
    asset_type       VARCHAR(10)  NOT NULL
                     CHECK (asset_type IN ('equity', 'etf', 'crypto', 'index')),
    exchange         VARCHAR(16)  NOT NULL DEFAULT 'SIM',
    current_price    NUMERIC(14,4) NOT NULL CHECK (current_price > 0),
    tick_size        NUMERIC(10,4) NOT NULL DEFAULT 0.01 CHECK (tick_size > 0),
    is_active        BOOLEAN      NOT NULL DEFAULT TRUE,
    price_updated_at TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT uq_instruments_symbol UNIQUE (symbol)
);

-- ----------------------------------------------------------------------------
-- 6. portfolios -- exactly one per trading account
-- ----------------------------------------------------------------------------
CREATE TABLE portfolios (
    portfolio_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id   UUID NOT NULL,
    name         VARCHAR(50) NOT NULL DEFAULT 'Main Portfolio',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_portfolios_account UNIQUE (account_id),
    CONSTRAINT fk_portfolios_account FOREIGN KEY (account_id)
                                     REFERENCES trading_accounts (account_id) ON DELETE CASCADE
);

-- ----------------------------------------------------------------------------
-- 7. portfolio_holdings -- one row per (portfolio, instrument)
-- ----------------------------------------------------------------------------
CREATE TABLE portfolio_holdings (
    holding_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    portfolio_id  UUID NOT NULL,
    instrument_id UUID NOT NULL,
    quantity      NUMERIC(18,6) NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    avg_buy_price NUMERIC(14,4) NOT NULL DEFAULT 0 CHECK (avg_buy_price >= 0),
    opened_at     TIMESTAMPTZ   NOT NULL DEFAULT now(),
    CONSTRAINT uq_holding_portfolio_instrument UNIQUE (portfolio_id, instrument_id),
    CONSTRAINT fk_holdings_portfolio FOREIGN KEY (portfolio_id)
                                     REFERENCES portfolios (portfolio_id) ON DELETE CASCADE,
    CONSTRAINT fk_holdings_instrument FOREIGN KEY (instrument_id)
                                      REFERENCES instruments (instrument_id) ON DELETE RESTRICT
);

-- ----------------------------------------------------------------------------
-- 8. orders -- a blocked order never reaches this table (BEFORE INSERT raises)
-- ----------------------------------------------------------------------------
CREATE TABLE orders (
    order_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id         UUID NOT NULL,
    instrument_id      UUID NOT NULL,
    side               VARCHAR(4)   NOT NULL CHECK (side IN ('BUY', 'SELL')),
    order_type         VARCHAR(6)   NOT NULL CHECK (order_type IN ('MARKET', 'LIMIT')),
    quantity           NUMERIC(18,6) NOT NULL CHECK (quantity > 0),
    limit_price        NUMERIC(14,4) CHECK (limit_price IS NULL OR limit_price > 0),
    status             VARCHAR(16)  NOT NULL DEFAULT 'PENDING'
                       CHECK (status IN ('PENDING', 'EXECUTED', 'CANCELLED', 'REJECTED')),
    risk_status        VARCHAR(8)   NOT NULL DEFAULT 'CLEAR'
                       CHECK (risk_status IN ('CLEAR', 'FLAGGED')),
    threat_indicator_id UUID,
    security_note      VARCHAR(255),
    origin_ip          INET NOT NULL,               -- screened by t1 trigger
    referrer_domain    VARCHAR(255),                -- optional order context (screened)
    referrer_url       TEXT,                        -- optional order context (screened)
    execution_price    NUMERIC(14,4)
                       CHECK (execution_price IS NULL OR execution_price > 0),
    placed_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_order_price_rule CHECK (
        (order_type = 'MARKET' AND limit_price IS NULL) OR
        (order_type = 'LIMIT'   AND limit_price IS NOT NULL)
    ),
    CONSTRAINT ck_order_executed_price CHECK (
        status <> 'EXECUTED' OR execution_price IS NOT NULL
    ),
    CONSTRAINT fk_orders_account    FOREIGN KEY (account_id)
                                     REFERENCES trading_accounts (account_id) ON DELETE CASCADE,
    CONSTRAINT fk_orders_instrument FOREIGN KEY (instrument_id)
                                     REFERENCES instruments (instrument_id) ON DELETE RESTRICT,
    CONSTRAINT fk_orders_indicator  FOREIGN KEY (threat_indicator_id)
                                     REFERENCES threat_indicators (indicator_id) ON DELETE SET NULL
);

-- ----------------------------------------------------------------------------
-- 9. trade_executions -- 1:N with orders (partial fills stay possible)
--    account_id is deliberately NOT stored: execution -> order -> account would
--    be a transitive (3NF-violating) dependency.
-- ----------------------------------------------------------------------------
CREATE TABLE trade_executions (
    execution_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id     UUID NOT NULL,
    quantity     NUMERIC(18,6) NOT NULL CHECK (quantity > 0),
    price        NUMERIC(14,4) NOT NULL CHECK (price > 0),
    gross_amount NUMERIC(14,2) NOT NULL CHECK (gross_amount >= 0),
    executed_at  TIMESTAMPTZ   NOT NULL DEFAULT now(),
    CONSTRAINT fk_executions_order FOREIGN KEY (order_id)
                                   REFERENCES orders (order_id) ON DELETE CASCADE
);

-- ----------------------------------------------------------------------------
-- 10. transactions -- append-only cash ledger, 1:1 with an execution
-- ----------------------------------------------------------------------------
CREATE TABLE transactions (
    transaction_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id   UUID NOT NULL,
    cash_delta     NUMERIC(14,2) NOT NULL CHECK (cash_delta <> 0),
    balance_after  NUMERIC(14,2) NOT NULL CHECK (balance_after >= 0),
    created_at     TIMESTAMPTZ   NOT NULL DEFAULT now(),
    CONSTRAINT uq_transactions_execution UNIQUE (execution_id),
    CONSTRAINT fk_transactions_execution FOREIGN KEY (execution_id)
                                         REFERENCES trade_executions (execution_id) ON DELETE CASCADE
);

-- ----------------------------------------------------------------------------
-- 11. security_events -- persists AFTER rollback for blocked orders
--      (order_id is NULL for blocks: the order row never existed)
-- ----------------------------------------------------------------------------
CREATE TABLE security_events (
    event_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type   VARCHAR(24) NOT NULL
                 CHECK (event_type IN ('ORDER_BLOCKED','ORDER_FLAGGED','THREAT_MATCH',
                                       'AUTH_FAILURE','THREAT_INDICATOR_CHANGED','ORDER_REJECTED')),
    severity     VARCHAR(8)  NOT NULL
                 CHECK (severity IN ('low','medium','high','critical')),
    indicator_id UUID,
    order_id     UUID,
    account_id   UUID,
    details      JSONB       NOT NULL DEFAULT '{}'::jsonb,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_events_indicator FOREIGN KEY (indicator_id)
                                   REFERENCES threat_indicators (indicator_id) ON DELETE SET NULL,
    CONSTRAINT fk_events_order     FOREIGN KEY (order_id)
                                   REFERENCES orders (order_id) ON DELETE SET NULL,
    CONSTRAINT fk_events_account   FOREIGN KEY (account_id)
                                   REFERENCES trading_accounts (account_id) ON DELETE SET NULL
);

-- ----------------------------------------------------------------------------
-- 12. audit_logs -- who did what, when, from where
--      entity_type/entity_id are polymorphic by design (documented 3NF exception)
-- ----------------------------------------------------------------------------
CREATE TABLE audit_logs (
    audit_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_user_id UUID,
    actor_role    VARCHAR(10)
                  CHECK (actor_role IS NULL OR actor_role IN ('client','admin','system')),
    action        VARCHAR(40) NOT NULL,
    entity_type   VARCHAR(30),
    entity_id     VARCHAR(40),
    ip_address    INET,
    status        VARCHAR(8)  NOT NULL DEFAULT 'success'
                  CHECK (status IN ('success','failure')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_audit_actor FOREIGN KEY (actor_user_id)
                              REFERENCES users (user_id) ON DELETE SET NULL
);

-- ============================================================================
-- TradeShield * 05_indexes.sql
-- Every index below is justified by a real application query -- nothing added
-- "just in case". Rationale in comments; measured with EXPLAIN ANALYZE in
-- db/demo/12_index_explain.sql.
-- ----------------------------------------------------------------------------

-- Order list per client (GET /api/orders, vw_order_history filter by account)
CREATE INDEX IF NOT EXISTS ix_orders_account_placed
    ON orders (account_id, placed_at DESC);

-- Market page / open-order book: pending orders for one instrument
-- (partial: only ~a fraction of rows are ever PENDING)
CREATE INDEX IF NOT EXISTS ix_orders_open
    ON orders (instrument_id, placed_at DESC)
    WHERE status = 'PENDING';

-- Admin flagged-order feed (partial on the rare state)
CREATE INDEX IF NOT EXISTS ix_orders_flagged
    ON orders (placed_at DESC)
    WHERE risk_status = 'FLAGGED';

-- FK + "order detail -> executions" join (vw_order_history LEFT JOIN executions)
CREATE INDEX IF NOT EXISTS ix_executions_order
    ON trade_executions (order_id);

-- HOT PATH: t1 screening lookup runs on EVERY order insert.
-- The UNIQUE(indicator_type, value) constraint already covers exact lookups, so
-- this partial index additionally skips disabled indicators entirely.
CREATE INDEX IF NOT EXISTS ix_indicators_screen
    ON threat_indicators (indicator_type, value)
    WHERE is_active;

-- FK (no leading-column coverage elsewhere) + "who holds instrument X"
CREATE INDEX IF NOT EXISTS ix_holdings_instrument
    ON portfolio_holdings (instrument_id);
-- NOTE: portfolio_id needs NO extra index -- the leading column of
-- uq_holding_portfolio_instrument (portfolio_id, instrument_id) already serves it.

-- Security feed pagination (Security Events / Blocked Orders screens)
CREATE INDEX IF NOT EXISTS ix_security_events_time
    ON security_events (created_at DESC);
CREATE INDEX IF NOT EXISTS ix_security_events_type_time
    ON security_events (event_type, created_at DESC);

-- Audit log filters: by actor, by time, by action (Admin -> Audit Logs)
CREATE INDEX IF NOT EXISTS ix_audit_actor_time
    ON audit_logs (actor_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_audit_time
    ON audit_logs (created_at DESC);
CREATE INDEX IF NOT EXISTS ix_audit_action_time
    ON audit_logs (action, created_at DESC);

-- Ledger ordering for /api/transactions (global newest-first feeds)
CREATE INDEX IF NOT EXISTS ix_transactions_time
    ON transactions (created_at DESC);

-- Instrument browsing filters (Market page: asset_type + active only)
CREATE INDEX IF NOT EXISTS ix_instruments_browse
    ON instruments (asset_type)
    WHERE is_active;

-- Threat indicator admin list by source (Source panel / source joins)
CREATE INDEX IF NOT EXISTS ix_indicators_source
    ON threat_indicators (source_id);

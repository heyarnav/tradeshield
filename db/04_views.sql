-- ============================================================================
-- TradeShield * 04_views.sql
-- Every view maps to a real application screen (see docs/DESIGN.md sec10).
-- ============================================================================

-- ----------------------------------------------------------------------------
-- vw_active_threats -- threat intelligence feed (admin: Threat Indicators)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_active_threats AS
SELECT i.indicator_id,
       i.indicator_type,
       i.value,
       i.threat_category,
       i.confidence,
       i.first_seen,
       i.last_seen,
       i.expires_at,
       s.source_id,
       s.name        AS source_name,
       s.reliability,
       i.notes
FROM threat_indicators i
JOIN threat_sources s ON s.source_id = i.source_id
WHERE i.is_active
  AND (i.expires_at IS NULL OR i.expires_at > now())
ORDER BY i.confidence DESC, i.last_seen DESC;

-- ----------------------------------------------------------------------------
-- vw_portfolio_summary -- one row per account: cash, valuation, P&L
--   (client: Dashboard + Portfolio; admin: account net worth)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_portfolio_summary AS
SELECT a.account_id,
       a.user_id,
       a.account_number,
       u.email,
       a.balance                                   AS cash_balance,
       a.status                                    AS account_status,
       COUNT(h.holding_id)                         AS holdings_count,
       COALESCE(SUM(h.quantity * i.current_price), 0)  AS market_value,
       COALESCE(SUM(h.quantity * h.avg_buy_price), 0)   AS cost_basis,
       COALESCE(SUM(h.quantity * (i.current_price - h.avg_buy_price)), 0) AS unrealized_pnl,
       a.balance + COALESCE(SUM(h.quantity * i.current_price), 0)         AS total_equity
FROM trading_accounts a
JOIN users u              ON u.user_id = a.user_id
LEFT JOIN portfolios p    ON p.account_id = a.account_id
LEFT JOIN portfolio_holdings h ON h.portfolio_id = p.portfolio_id
LEFT JOIN instruments i   ON i.instrument_id = h.instrument_id
GROUP BY a.account_id, a.user_id, a.account_number, u.email, a.balance, a.status;

-- ----------------------------------------------------------------------------
-- vw_order_history -- orders joined to account + instrument (client: Orders)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_order_history AS
SELECT o.order_id,
       o.account_id,
       u.user_id,
       u.email,
       o.status,
       o.risk_status,
       o.security_note,
       i.symbol,
       i.name            AS instrument_name,
       o.side,
       o.order_type,
       o.quantity,
       o.limit_price,
       o.execution_price,
       e.execution_id,
       e.gross_amount,
       o.origin_ip,
       o.placed_at,
       o.updated_at
FROM orders o
JOIN trading_accounts a ON a.account_id = o.account_id
JOIN users u            ON u.user_id = a.user_id
JOIN instruments i      ON i.instrument_id = o.instrument_id
LEFT JOIN trade_executions e ON e.order_id = o.order_id
ORDER BY o.placed_at DESC;

-- ----------------------------------------------------------------------------
-- vw_transaction_history -- cash ledger joined back to orders (client: Transactions)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_transaction_history AS
SELECT t.transaction_id,
       t.execution_id,
       o.account_id,
       u.email,
       o.order_id,
       o.side,
       o.order_type,
       i.symbol,
       ex.quantity,
       ex.price,
       t.cash_delta,
       t.balance_after,
       t.created_at
FROM transactions t
JOIN trade_executions ex ON ex.execution_id = t.execution_id
JOIN orders o            ON o.order_id = ex.order_id
JOIN trading_accounts a  ON a.account_id = o.account_id
JOIN users u             ON u.user_id = a.user_id
JOIN instruments i       ON i.instrument_id = o.instrument_id
ORDER BY t.created_at DESC;

-- ----------------------------------------------------------------------------
-- vw_blocked_orders -- blocked/flagged order attempts reconstructed from
-- security_events (blocked orders have no row in `orders` by design)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_blocked_orders AS
SELECT e.event_id,
       e.event_type,
       e.severity,
       e.created_at           AS detected_at,
       e.account_id,
       e.order_id,
       e.indicator_id,
       i.indicator_type,
       i.value                AS indicator_value,
       i.threat_category,
       i.confidence,
       s.name                 AS source_name,
       (e.details->>'side')          AS attempted_side,
       (e.details->>'order_type')    AS attempted_order_type,
       (e.details->>'quantity')::NUMERIC      AS attempted_quantity,
       (e.details->>'limit_price')::NUMERIC   AS attempted_limit_price,
       (e.details->>'origin_ip')     AS origin_ip,
       (e.details->>'reason')        AS reason,
       e.details
FROM security_events e
LEFT JOIN threat_indicators i ON i.indicator_id = e.indicator_id
LEFT JOIN threat_sources s    ON s.source_id = i.source_id
WHERE e.event_type IN ('ORDER_BLOCKED', 'ORDER_FLAGGED')
ORDER BY e.created_at DESC;

-- ----------------------------------------------------------------------------
-- vw_security_dashboard -- single row of KPIs (admin: Security Dashboard)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_security_dashboard AS
SELECT (SELECT COUNT(*) FROM vw_active_threats)                       AS active_threats,
       (SELECT COUNT(*) FROM vw_active_threats WHERE confidence >= 80) AS critical_threats,
       (SELECT COUNT(*) FROM threat_indicators)                       AS total_indicators,
       (SELECT COUNT(*) FROM threat_indicators WHERE NOT is_active)   AS disabled_indicators,
       (SELECT COUNT(*) FROM threat_sources)                          AS threat_sources,
       (SELECT COUNT(*) FROM security_events
         WHERE event_type = 'ORDER_BLOCKED')                          AS blocked_orders_total,
       (SELECT COUNT(*) FROM security_events
         WHERE event_type = 'ORDER_BLOCKED'
           AND created_at > now() - interval '24 hours')              AS blocked_orders_24h,
       (SELECT COUNT(*) FROM orders WHERE risk_status = 'FLAGGED')    AS flagged_orders_total,
       (SELECT COUNT(*) FROM security_events
         WHERE created_at > now() - interval '24 hours')              AS events_24h,
       (SELECT COUNT(*) FROM audit_logs)                              AS audit_entries,
       (SELECT COUNT(*) FROM users WHERE role = 'client')             AS client_count,
       now()                                                          AS generated_at;

-- ----------------------------------------------------------------------------
-- vw_threat_source_summary -- GROUP BY + HAVING: sources still contributing
-- at least one active indicator
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_threat_source_summary AS
SELECT s.source_id,
       s.name,
       s.reliability,
       s.is_active,
       COUNT(i.indicator_id)  AS total_indicators,
       COUNT(*) FILTER (WHERE i.is_active
                          AND (i.expires_at IS NULL OR i.expires_at > now()))
                              AS active_indicators,
       COUNT(*) FILTER (WHERE i.confidence >= 80) AS critical_indicators,
       MAX(i.last_seen)       AS last_contribution
FROM threat_sources s
LEFT JOIN threat_indicators i ON i.source_id = s.source_id
GROUP BY s.source_id, s.name, s.reliability, s.is_active
HAVING COUNT(*) FILTER (WHERE i.is_active
                          AND (i.expires_at IS NULL OR i.expires_at > now())) > 0;

-- ----------------------------------------------------------------------------
-- vw_client_trading_stats -- GROUP BY + HAVING: clients with activity
-- (admin: Security Dashboard client table)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_client_trading_stats AS
SELECT o.account_id,
       a.account_number,
       u.email,
       COUNT(*)                                   AS total_orders,
       COUNT(*) FILTER (WHERE o.status = 'EXECUTED')  AS executed_orders,
       COUNT(*) FILTER (WHERE o.risk_status = 'FLAGGED') AS flagged_orders,
       COALESCE(SUM(e.gross_amount), 0)            AS traded_value,
       MAX(o.placed_at)                           AS last_order_at
FROM orders o
JOIN trading_accounts a ON a.account_id = o.account_id
JOIN users u            ON u.user_id = a.user_id
LEFT JOIN trade_executions e ON e.order_id = o.order_id
GROUP BY o.account_id, a.account_number, u.email
HAVING COUNT(*) > 0
ORDER BY traded_value DESC;

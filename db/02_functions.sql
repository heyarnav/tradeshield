-- ============================================================================
-- TradeShield * 02_functions.sql
--   fn_screen_threat  -- worst active/non-expired match for an order's context
--   fn_lookup_threat  -- generic indicator lookup for any type (incl. file_hash)
--   fn_execute_order  -- atomic BUY/SELL execution (funds, holdings, ledger)
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Threat screening used by the BEFORE INSERT trigger.
-- Matches IP (exact), domain (exact or parent domain), URL (exact or prefix).
-- Returns at most the single highest-confidence active, non-expired match.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_screen_threat(
    p_ip     INET,
    p_domain TEXT,
    p_url    TEXT
)
RETURNS TABLE (
    indicator_id    UUID,
    confidence      SMALLINT,
    threat_category VARCHAR,
    value           VARCHAR
)
LANGUAGE sql
STABLE
AS $$
    SELECT i.indicator_id, i.confidence, i.threat_category, i.value
    FROM threat_indicators i
    WHERE i.is_active
      AND (i.expires_at IS NULL OR i.expires_at > now())
      AND (
            (p_ip IS NOT NULL
             AND i.indicator_type = 'ip'
             AND i.value = host(p_ip))
         OR (p_domain IS NOT NULL
             AND i.indicator_type = 'domain'
             AND (lower(p_domain) = i.value
                  OR lower(p_domain) LIKE '%.' || i.value))
         OR (p_url IS NOT NULL
             AND i.indicator_type = 'url'
             AND (lower(p_url) = i.value
                  OR lower(p_url) LIKE i.value || '%'))
          )
    ORDER BY i.confidence DESC, i.last_seen DESC
    LIMIT 1;
$$;

-- ----------------------------------------------------------------------------
-- Generic lookup for any indicator type -- powers /api/security/lookup and the
-- threat-lookup demonstration script (works for file hashes too).
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_lookup_threat(p_type VARCHAR, p_value TEXT)
RETURNS TABLE (
    indicator_id    UUID,
    indicator_type  VARCHAR,
    value           VARCHAR,
    threat_category VARCHAR,
    confidence      SMALLINT,
    source_name     VARCHAR,
    is_active       BOOLEAN,
    expires_at      TIMESTAMPTZ
)
LANGUAGE sql
STABLE
AS $$
    SELECT i.indicator_id, i.indicator_type, i.value, i.threat_category, i.confidence,
           s.name, i.is_active, i.expires_at
    FROM threat_indicators i
    JOIN threat_sources s ON s.source_id = i.source_id
    WHERE i.indicator_type = p_type
      AND i.value = CASE
                        WHEN p_type IN ('domain','url','file_hash') THEN lower(p_value)
                        ELSE p_value
                    END
    ORDER BY i.confidence DESC;
$$;

-- ----------------------------------------------------------------------------
-- fn_execute_order -- the financial core. Called by Flask inside the SAME
-- transaction that inserted the order, so everything commits or rolls back
-- together. Locks the account row first, then the holding row (fixed order =>
-- no deadlocks). Re-checks funds/holdings under lock (authoritative second check).
--
-- Returns JSONB: {"executed": bool, "status": ..., "execution_id": ...,
--                 "price": ..., "gross": ..., "reason": ...}
-- Raises TS002 (insufficient funds) / TS003 (insufficient holdings) on races.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_execute_order(p_order_id UUID)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    o               RECORD;
    inst            RECORD;
    v_portfolio     UUID;
    v_holding_id    UUID;
    v_holding_qty   NUMERIC(18,6) := 0;
    v_price         NUMERIC(14,4);
    v_gross         NUMERIC(14,2);
    v_exec          UUID;
    v_new_qty       NUMERIC(18,6);
    v_new_avg       NUMERIC(14,4);
    v_balance       NUMERIC(14,2);
BEGIN
    SELECT * INTO o FROM orders WHERE order_id = p_order_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Order % not found', p_order_id USING ERRCODE = 'TS004';
    END IF;
    IF o.status <> 'PENDING' THEN
        RETURN jsonb_build_object('executed', false, 'status', o.status,
                                  'reason', 'order is not pending');
    END IF;

    SELECT * INTO inst FROM instruments WHERE instrument_id = o.instrument_id;

    -- ---- decide whether this order fills right now -------------------------
    IF o.order_type = 'MARKET' THEN
        v_price := inst.current_price;
    ELSIF o.side = 'BUY' AND inst.current_price <= o.limit_price THEN
        v_price := inst.current_price;          -- fills at the (better) market price
    ELSIF o.side = 'SELL' AND inst.current_price >= o.limit_price THEN
        v_price := inst.current_price;
    ELSE
        RETURN jsonb_build_object('executed', false, 'status', 'PENDING',
                                  'reason', 'limit price not satisfied by current market price');
    END IF;

    v_gross := round(o.quantity * v_price, 2);

    SELECT portfolio_id INTO v_portfolio
    FROM portfolios WHERE account_id = o.account_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'No portfolio for account %', o.account_id USING ERRCODE = 'TS004';
    END IF;

    -- ---- lock the account row first (fixed lock order) ----------------------
    SELECT balance INTO v_balance
    FROM trading_accounts
    WHERE account_id = o.account_id
    FOR UPDATE;

    IF o.side = 'BUY' THEN
        -- authoritative funds check under lock
        IF v_balance < v_gross THEN
            RAISE EXCEPTION 'Insufficient funds: required %, available %', v_gross, v_balance
                USING ERRCODE = 'TS002';
        END IF;

        UPDATE trading_accounts
        SET balance = balance - v_gross
        WHERE account_id = o.account_id;

        -- weighted average buy price: (q_old*avg_old + q_new*price) / (q_old + q_new)
        INSERT INTO portfolio_holdings (portfolio_id, instrument_id, quantity, avg_buy_price)
        VALUES (v_portfolio, o.instrument_id, o.quantity, v_price)
        ON CONFLICT (portfolio_id, instrument_id) DO UPDATE
            SET quantity      = portfolio_holdings.quantity + EXCLUDED.quantity,
                avg_buy_price = round(
                    (portfolio_holdings.quantity * portfolio_holdings.avg_buy_price
                     + EXCLUDED.quantity * EXCLUDED.avg_buy_price)
                    / (portfolio_holdings.quantity + EXCLUDED.quantity), 4);

    ELSE -- SELL
        SELECT ph.holding_id, ph.quantity INTO v_holding_id, v_holding_qty
        FROM portfolio_holdings ph
        WHERE ph.portfolio_id = v_portfolio
          AND ph.instrument_id = o.instrument_id
        FOR UPDATE;

        IF NOT FOUND THEN
            RAISE EXCEPTION 'Insufficient holdings: required %, available 0', o.quantity
                USING ERRCODE = 'TS003';
        END IF;
        IF v_holding_qty < o.quantity THEN
            RAISE EXCEPTION 'Insufficient holdings: required %, available %',
                o.quantity, v_holding_qty
                USING ERRCODE = 'TS003';
        END IF;

        UPDATE portfolio_holdings
        SET quantity = quantity - o.quantity
        WHERE holding_id = v_holding_id;

        UPDATE trading_accounts
        SET balance = balance + v_gross
        WHERE account_id = o.account_id;
    END IF;

    -- ---- execution + ledger + order status (all one transaction) ------------
    v_exec := gen_random_uuid();
    INSERT INTO trade_executions (execution_id, order_id, quantity, price, gross_amount)
    VALUES (v_exec, p_order_id, o.quantity, v_price, v_gross);

    SELECT balance INTO v_balance
    FROM trading_accounts WHERE account_id = o.account_id;

    INSERT INTO transactions (execution_id, cash_delta, balance_after)
    VALUES (v_exec,
            CASE WHEN o.side = 'BUY' THEN -v_gross ELSE v_gross END,
            v_balance);

    UPDATE orders
    SET status = 'EXECUTED', execution_price = v_price, updated_at = now()
    WHERE order_id = p_order_id;

    RETURN jsonb_build_object(
        'executed',     true,
        'status',       'EXECUTED',
        'execution_id', v_exec,
        'price',        v_price,
        'gross',        v_gross,
        'side',         o.side
    );
END;
$$;

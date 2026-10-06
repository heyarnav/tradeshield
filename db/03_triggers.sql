-- ============================================================================
-- TradeShield * 03_triggers.sql
-- BEFORE INSERT t1 -- threat screening (blocks with a PostgreSQL exception)
-- BEFORE INSERT t2 -- financial validation (funds, holdings, price rules)
-- BEFORE UPDATE t3 -- updated_at maintenance
-- AFTER  INSERT/UPDATE t4 -- order audit + flagged-order security event
-- AFTER  INSERT/UPDATE t5 -- threat-indicator change security event
--
-- Blocked order => t1 raises TS001 => whole transaction rolls back => the order
-- row never exists. Flask then records security_events/audit_logs in a NEW
-- transaction so the evidence survives permanently.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- t1 * SECURITY SCREENING
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_orders_security_screen()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_match RECORD;
BEGIN
    SELECT * INTO v_match
    FROM fn_screen_threat(NEW.origin_ip, NEW.referrer_domain, NEW.referrer_url)
    ORDER BY confidence DESC
    LIMIT 1;

    IF NOT FOUND THEN
        NEW.risk_status := 'CLEAR';
        RETURN NEW;
    END IF;

    IF v_match.confidence >= 80 THEN
        -- CRITICAL: reject before the row is ever written
        RAISE EXCEPTION 'ORDER_BLOCKED: threat indicator % (%, confidence %) matched order context',
                        v_match.value, v_match.threat_category, v_match.confidence
            USING ERRCODE = 'TS001',
                  DETAIL  = jsonb_build_object(
                                'indicator_id', v_match.indicator_id,
                                'value',        v_match.value,
                                'category',     v_match.threat_category,
                                'confidence',   v_match.confidence
                            )::text,
                  HINT    = 'Critical threat indicator matched; order rejected by BEFORE INSERT trigger.';
    ELSIF v_match.confidence >= 60 THEN
        -- MEDIUM: order is created but marked for review
        NEW.risk_status       := 'FLAGGED';
        NEW.threat_indicator_id := v_match.indicator_id;
        NEW.security_note     := format('flagged: confidence %s, category %s',
                                        v_match.confidence, v_match.threat_category);
    ELSE
        NEW.risk_status := 'CLEAR';   -- low confidence: allowed
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS t1_orders_security_screen ON orders;
CREATE TRIGGER t1_orders_security_screen
    BEFORE INSERT ON orders
    FOR EACH ROW
    EXECUTE FUNCTION trg_orders_security_screen();

-- ----------------------------------------------------------------------------
-- t2 * FINANCIAL VALIDATION (database-level trading rules)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_orders_financial_check()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_account   RECORD;
    v_instrument RECORD;
    v_holding   NUMERIC(18,6) := 0;
    v_needed    NUMERIC(14,2);
BEGIN
    -- Account exists, is active, and is locked for the rest of the transaction.
    --
    -- The lock is required for correctness under concurrency, not just for the
    -- funds check: inserting the order row takes a FOR KEY SHARE lock on the
    -- referenced account (orders.account_id FK), and fn_execute_order later
    -- upgrades that same lock to FOR UPDATE. Two orders for one account would
    -- each hold the KEY SHARE lock and each wait for the other's upgrade, which
    -- PostgreSQL resolves by aborting one transaction with a deadlock (40P01).
    -- Taking FOR UPDATE here -- BEFORE the row exists, i.e. before any FK lock is
    -- granted -- serialises orders per account at the front of the transaction
    -- and removes the upgrade cycle entirely. Lock order stays "account first",
    -- matching fn_execute_order, so no new cycle is introduced.
    SELECT * INTO v_account
    FROM trading_accounts WHERE account_id = NEW.account_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Trading account % does not exist', NEW.account_id
            USING ERRCODE = 'TS004';
    END IF;
    IF v_account.status <> 'active' THEN
        RAISE EXCEPTION 'Trading account % is not active (status: %)',
                        NEW.account_id, v_account.status
            USING ERRCODE = 'TS005';
    END IF;

    -- instrument exists and is tradable
    SELECT * INTO v_instrument
    FROM instruments WHERE instrument_id = NEW.instrument_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Instrument % does not exist', NEW.instrument_id
            USING ERRCODE = 'TS004';
    END IF;
    IF NOT v_instrument.is_active THEN
        RAISE EXCEPTION 'Instrument % is not active', v_instrument.symbol
            USING ERRCODE = 'TS005';
    END IF;

    -- quantity / price rules
    IF NEW.quantity <= 0 THEN
        RAISE EXCEPTION 'Quantity must be greater than 0' USING ERRCODE = 'TS004';
    END IF;
    IF NEW.order_type = 'LIMIT' THEN
        IF NEW.limit_price IS NULL OR NEW.limit_price <= 0 THEN
            RAISE EXCEPTION 'LIMIT orders require a positive limit_price'
                USING ERRCODE = 'TS006';
        END IF;
    ELSE
        IF NEW.limit_price IS NOT NULL THEN
            RAISE EXCEPTION 'MARKET orders must not carry a limit_price'
                USING ERRCODE = 'TS006';
        END IF;
    END IF;

    -- BUY: sufficient funds (checked at the worst-case price for LIMIT)
    IF NEW.side = 'BUY' THEN
        v_needed := round(NEW.quantity
                          * COALESCE(NEW.limit_price, v_instrument.current_price), 2);
        IF v_account.balance < v_needed THEN
            RAISE EXCEPTION 'Insufficient funds: required %, available %',
                            v_needed, v_account.balance
                USING ERRCODE = 'TS002';
        END IF;
    ELSE
        -- SELL: sufficient holdings
        SELECT COALESCE(h.quantity, 0) INTO v_holding
        FROM portfolios p
        LEFT JOIN portfolio_holdings h ON h.portfolio_id = p.portfolio_id
                                      AND h.instrument_id = NEW.instrument_id
        WHERE p.account_id = NEW.account_id;

        IF v_holding IS NULL THEN
            v_holding := 0;   -- no portfolio row at all
        END IF;
        IF v_holding < NEW.quantity THEN
            RAISE EXCEPTION 'Insufficient holdings: required %, available %',
                            NEW.quantity, v_holding
                USING ERRCODE = 'TS003';
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS t2_orders_financial_check ON orders;
CREATE TRIGGER t2_orders_financial_check
    BEFORE INSERT ON orders
    FOR EACH ROW
    EXECUTE FUNCTION trg_orders_financial_check();

-- ----------------------------------------------------------------------------
-- t3 * updated_at maintenance
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS t3_orders_updated_at ON orders;
CREATE TRIGGER t3_orders_updated_at
    BEFORE UPDATE ON orders
    FOR EACH ROW
    EXECUTE FUNCTION trg_set_updated_at();

-- ----------------------------------------------------------------------------
-- t4 * order lifecycle: audit row + flagged-order security event
--        (AFTER triggers run in the same transaction as the order; that is
--         correct for successful orders and irrelevant for blocked ones,
--         which never get this far.)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_orders_audit()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO audit_logs (actor_role, action, entity_type, entity_id,
                                ip_address, status)
        VALUES ('system', 'ORDER_PLACED', 'order', NEW.order_id::text,
                NEW.origin_ip, 'success');

        IF NEW.risk_status = 'FLAGGED' THEN
            INSERT INTO security_events (event_type, severity, indicator_id,
                                         order_id, account_id, details)
            VALUES ('ORDER_FLAGGED', 'medium', NEW.threat_indicator_id,
                    NEW.order_id, NEW.account_id,
                    jsonb_build_object(
                        'side',       NEW.side,
                        'order_type', NEW.order_type,
                        'quantity',   NEW.quantity,
                        'limit_price', NEW.limit_price,
                        'origin_ip',  host(NEW.origin_ip),
                        'reason',     NEW.security_note,
                        'confidence', (SELECT confidence FROM threat_indicators
                                       WHERE indicator_id = NEW.threat_indicator_id)
                    ));
        END IF;
    ELSE
        INSERT INTO audit_logs (actor_role, action, entity_type, entity_id,
                                ip_address, status)
        VALUES ('system',
                CASE WHEN NEW.status = 'EXECUTED' THEN 'ORDER_EXECUTED'
                     ELSE 'ORDER_UPDATED' END,
                'order', NEW.order_id::text, NEW.origin_ip, 'success');
    END IF;

    RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS t4_orders_audit ON orders;
CREATE TRIGGER t4_orders_audit
    AFTER INSERT OR UPDATE ON orders
    FOR EACH ROW
    EXECUTE FUNCTION trg_orders_audit();

-- ----------------------------------------------------------------------------
-- t5 * threat indicator created / updated / disabled => security event
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_indicator_audit()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO security_events (event_type, severity, indicator_id, details)
    VALUES (
        'THREAT_INDICATOR_CHANGED',
        CASE WHEN TG_OP = 'DELETE' THEN 'medium'
             WHEN COALESCE(NEW.is_active, FALSE) AND NOT COALESCE(OLD.is_active, TRUE)
                  THEN 'high'        -- re-enabled
             WHEN TG_OP = 'UPDATE' AND NOT NEW.is_active THEN 'high'  -- disabled
             ELSE 'low' END,
        CASE WHEN TG_OP = 'DELETE' THEN OLD.indicator_id ELSE NEW.indicator_id END,
        jsonb_build_object(
            'operation',      TG_OP,
            'indicator_type', CASE WHEN TG_OP = 'DELETE' THEN OLD.indicator_type
                                   ELSE NEW.indicator_type END,
            'value',          CASE WHEN TG_OP = 'DELETE' THEN OLD.value
                                   ELSE NEW.value END,
            'confidence',     CASE WHEN TG_OP = 'DELETE' THEN OLD.confidence
                                   ELSE NEW.confidence END,
            'is_active',      CASE WHEN TG_OP = 'DELETE' THEN OLD.is_active
                                   ELSE NEW.is_active END
        )
    );
    RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS t5_indicator_changes ON threat_indicators;
CREATE TRIGGER t5_indicator_changes
    AFTER INSERT OR UPDATE ON threat_indicators
    FOR EACH ROW
    EXECUTE FUNCTION trg_indicator_audit();

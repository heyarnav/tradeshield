-- ============================================================================
-- TradeShield * 06_seed.sql
-- Demo data: users, accounts, instruments, threat sources & indicators.
-- Idempotent: every insert is guarded by ON CONFLICT / NOT EXISTS.
-- Passwords (werkzeug scrypt hashes):
--   admin@tradeshield.dev   -> Admin@123
--   client@tradeshield.dev  -> Client@123
--   client2@tradeshield.dev -> Client@123   (used by authorization tests)
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Users
-- ----------------------------------------------------------------------------
INSERT INTO users (user_id, email, password_hash, full_name, role)
VALUES ('a0000000-0000-4000-8000-000000000001',
        'admin@tradeshield.dev',
        'scrypt:32768:8:1$b19qo24EiYNg1SdL$385d6e8e782955394458fadbe1dc46528a78f3c4fc0fcb13f8c4ed5509b7536cb2b270de3233dbae1f0c2ffbcb9501fdee2cb50321fa9ffa09ca776120d3b248',
        'Security Operations', 'admin'),
       ('a0000000-0000-4000-8000-000000000002',
        'client@tradeshield.dev',
        'scrypt:32768:8:1$b6lkamk5TOz0XYdJ$47d97253549e2930844c20b334e5a0c0a530a0d3e90f7c1da5a5aa9d595f48d3e2e59ca62dbee06d15f3930758a2186468e25589a8029d5ee4c96b85d8d53ce9',
        'Aarav Mehta', 'client'),
       ('a0000000-0000-4000-8000-000000000003',
        'client2@tradeshield.dev',
        'scrypt:32768:8:1$b6lkamk5TOz0XYdJ$47d97253549e2930844c20b334e5a0c0a530a0d3e90f7c1da5a5aa9d595f48d3e2e59ca62dbee06d15f3930758a2186468e25589a8029d5ee4c96b85d8d53ce9',
        'Diya Sharma', 'client')
ON CONFLICT (email) DO NOTHING;

-- ----------------------------------------------------------------------------
-- Trading accounts + portfolios (starting cash $100,000)
-- ----------------------------------------------------------------------------
INSERT INTO trading_accounts (user_id, account_number, balance)
SELECT u.user_id,
       CASE WHEN u.role = 'admin' THEN 'TS-ADMIN01'
            ELSE 'TS-' || upper(right(replace(u.user_id::text, '-', ''), 8))
       END,
       100000.00
FROM users u
WHERE u.email IN ('admin@tradeshield.dev','client@tradeshield.dev','client2@tradeshield.dev')
  AND NOT EXISTS (SELECT 1 FROM trading_accounts a WHERE a.user_id = u.user_id)
ON CONFLICT (user_id) DO NOTHING;

INSERT INTO portfolios (account_id, name)
SELECT a.account_id, 'Main Portfolio'
FROM trading_accounts a
WHERE NOT EXISTS (SELECT 1 FROM portfolios p WHERE p.account_id = a.account_id);

-- ----------------------------------------------------------------------------
-- Instruments (simulated market)
-- ----------------------------------------------------------------------------
INSERT INTO instruments (symbol, name, asset_type, exchange, current_price, tick_size)
VALUES ('ACME', 'Acme Corporation',        'equity', 'SIM', 175.40,  0.01),
       ('BLU',  'BlueRiver Energy',        'equity', 'SIM',  88.25,  0.01),
       ('CRTL', 'CoreTel Networks',        'equity', 'SIM',  42.10,  0.01),
       ('DYN',  'Dynasty Motors',          'equity', 'SIM', 310.00,  0.01),
       ('ECHO', 'EchoHealth Labs',         'equity', 'SIM',  19.75,  0.01),
       ('FLUX', 'Flux Semiconductor',      'equity', 'SIM', 512.30,  0.01),
       ('GLD',  'Simulated Gold ETF',      'etf',    'SIM', 402.10,  0.01),
       ('TLT',  'Simulated Bond ETF',      'etf',    'SIM',  96.40,  0.01),
       ('BTC',  'Bitcoin (simulated)',     'crypto', 'SIM', 67250.00, 0.01),
       ('ETH',  'Ethereum (simulated)',    'crypto', 'SIM', 3240.50, 0.01),
       ('SPX',  'Simulated S&P 500 Index', 'index',  'SIM', 5480.90, 0.10),
       ('VOLT', 'VoltGrid Utilities',      'equity', 'SIM',  63.55,  0.01)
ON CONFLICT (symbol) DO NOTHING;

-- An inactive instrument (exercises the "instrument is active" rule)
INSERT INTO instruments (symbol, name, asset_type, exchange, current_price, is_active)
VALUES ('OLD', 'Delisted OldCo', 'equity', 'SIM', 4.20, FALSE)
ON CONFLICT (symbol) DO NOTHING;

-- ----------------------------------------------------------------------------
-- Opening position for the demo client (documented as an opening balance,
-- i.e. no fabricated trade history): 100 ACME @ 150.00, 40 GLD @ 380.00
-- ----------------------------------------------------------------------------
INSERT INTO portfolio_holdings (portfolio_id, instrument_id, quantity, avg_buy_price)
SELECT p.portfolio_id, i.instrument_id, v.quantity, v.avg
FROM portfolios p
JOIN trading_accounts a ON a.account_id = p.account_id
JOIN users u            ON u.user_id = a.user_id
JOIN (VALUES ('ACME', 100::NUMERIC, 150.00),
             ('GLD',   40::NUMERIC, 380.00)) AS v(symbol, quantity, avg)
     ON TRUE
JOIN instruments i ON i.symbol = v.symbol
WHERE u.email = 'client@tradeshield.dev'
ON CONFLICT (portfolio_id, instrument_id) DO NOTHING;

-- ----------------------------------------------------------------------------
-- Threat sources (stored separately from indicators)
-- ----------------------------------------------------------------------------
INSERT INTO threat_sources (source_id, name, description, contact_url, reliability)
VALUES ('b0000000-0000-4000-8000-000000000001', 'Open Threat Exchange',
        'Community-shared indicator feed', 'https://example.org/ote', 4),
       ('b0000000-0000-4000-8000-000000000002', 'Campus SOC Feed',
        'Internal security operations centre', NULL, 5),
       ('b0000000-0000-4000-8000-000000000003', 'HoneyNet Project',
        'Honeypot-derived observations', 'https://example.org/honeynet', 3),
       ('b0000000-0000-4000-8000-000000000004', 'Legacy Feed (quarantined)',
        'Deprecated feed, indicators disabled', NULL, 1)
ON CONFLICT (name) DO NOTHING;

-- ----------------------------------------------------------------------------
-- Threat indicators
--   confidence >= 80  -> BLOCK   (order never written)
--   confidence 60-79  -> FLAG    (order written with risk_status = FLAGGED)
--   confidence <  60  -> ALLOW
--   expired / inactive indicators are ignored by the screening function
-- ----------------------------------------------------------------------------
INSERT INTO threat_indicators
    (indicator_id, source_id, indicator_type, value, threat_category, confidence,
     first_seen, last_seen, expires_at, is_active, notes)
VALUES
    -- CRITICAL (would BLOCK an order from this IP / domain / URL)
    ('c0000000-0000-4000-8000-000000000001', 'b0000000-0000-4000-8000-000000000002',
     'ip', '198.51.100.66', 'c2', 95,
     now() - interval '10 days', now() - interval '2 hours', NULL, TRUE,
     'Confirmed C2 beacon source -- blocked demo'),
    ('c0000000-0000-4000-8000-000000000002', 'b0000000-0000-4000-8000-000000000001',
     'domain', 'secure-login-tradeshield.net', 'phishing', 92,
     now() - interval '6 days', now() - interval '1 day', NULL, TRUE,
     'Credential-harvesting lookalike domain'),
    ('c0000000-0000-4000-8000-000000000003', 'b0000000-0000-4000-8000-000000000003',
     'url', 'http://malware.example/dropper.bin', 'malware', 88,
     now() - interval '3 days', now() - interval '3 days', NULL, TRUE,
     'Payload delivery URL'),
    ('c0000000-0000-4000-8000-000000000004', 'b0000000-0000-4000-8000-000000000002',
     'file_hash', 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
     'malware', 90,
     now() - interval '15 days', now() - interval '5 days', NULL, TRUE,
     'Known ransomware sample'),

    -- MEDIUM (would FLAG an order whose referrer domain matches)
    ('c0000000-0000-4000-8000-000000000005', 'b0000000-0000-4000-8000-000000000003',
     'domain', 'promo-trades.io', 'fraud', 68,
     now() - interval '4 days', now() - interval '6 hours', NULL, TRUE,
     'Pump-and-promo landing domain -- flagged demo'),

    -- LOW (ALLOW: order proceeds as CLEAR)
    ('c0000000-0000-4000-8000-000000000006', 'b0000000-0000-4000-8000-000000000001',
     'ip', '203.0.113.24', 'spam', 45,
     now() - interval '20 days', now() - interval '2 days', NULL, TRUE,
     'Bulk scanner, low confidence -- allowed demo'),

    -- EXPIRED (confidence 99 but ignored because expires_at is in the past)
    ('c0000000-0000-4000-8000-000000000007', 'b0000000-0000-4000-8000-000000000002',
     'ip', '192.0.2.99', 'recon', 99,
     now() - interval '60 days', now() - interval '30 days',
     now() - interval '1 day', TRUE,
     'Expired -- must be ignored by screening'),

    -- DISABLED (confidence 95 but inactive)
    ('c0000000-0000-4000-8000-000000000008', 'b0000000-0000-4000-8000-000000000004',
     'domain', 'disabled-legacy.example', 'botnet', 95,
     now() - interval '90 days', now() - interval '60 days', NULL, FALSE,
     'Disabled after false positive -- disable demo')
ON CONFLICT (indicator_type, value) DO NOTHING;

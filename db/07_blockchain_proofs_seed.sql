-- ==============================================================================
-- TradeShield * 07_blockchain_proofs_seed.sql
--
-- Seeds MOCK blockchain proof records for the demo dataset so the admin page is
-- not empty on first run.
--
-- IMPORTANT: these are MOCK proofs. They are NOT real blockchain transactions.
-- They are attached to stable demo reference identifiers only, to illustrate the
-- admin UI and mock verification flow.
--
-- Apply AFTER 06_seed.sql and AFTER 07_blockchain_proofs.sql.
-- Idempotent: INSERT ... ON CONFLICT DO NOTHING.
-- ==============================================================================

-- Deterministic mock proof helper (same logic as backend/app/blockchain.py).
-- In a real deployment this kind of derivation would live in one place only; for
-- the demo seed we inline a stable equivalent so the DB seed matches the API.

-- A small helper CTE so the seed is readable and deterministic.
WITH mock_now AS (
    SELECT now() AS ts
),
mock_proofs(reference_id, entity_type, event_type, note) AS (
    VALUES
        -- MOCK proof for a demo successful trade execution (illustrative only:
        -- no fabricated order/execution rows are created by this seed).
        ('demo-execution-acme-buy', 'execution', 'TRADE_EXECUTED',
         'MOCK proof anchored to a demo trade execution reference'),

        -- MOCK proof for a second demo successful trade execution
        ('demo-execution-gld-sell', 'execution', 'TRADE_EXECUTED',
         'MOCK proof anchored to a second demo trade execution reference'),

        -- MOCK proof for a demo blocked/security event reference
        ('demo-security-order-blocked', 'security_event', 'ORDER_BLOCKED',
         'MOCK proof anchored to a demo blocked-order security event reference')
),
mock_hashes AS (
    SELECT
        mp.reference_id,
        mp.entity_type,
        mp.event_type,
        mp.note,
        -- deterministic mock record hash (same canonical inputs -> same hash)
        encode(
            digest(
                (mp.entity_type || ':' || mp.reference_id || ':' || mp.event_type || ':' || to_char(mn.ts, 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')),
                'sha256'
            ),
            'hex'
        ) AS record_hash,
        -- deterministic mock transaction hash
        encode(
            digest('TradeShield Local Mock Chain:tx:' || md5(mp.reference_id || mp.entity_type || mp.event_type), 'sha256'),
            'hex'
        ) AS transaction_hash,
        -- deterministic mock block number in a realistic-looking range
        (882100 + (abs(hashtext(mp.reference_id || mp.entity_type)) % 99899)) AS block_number
    FROM mock_now mn
    CROSS JOIN mock_proofs mp
)
INSERT INTO blockchain_proofs
    (proof_id, reference_id, entity_type, event_type, record_hash,
     blockchain_status, transaction_hash, block_number, network,
     contract_address, created_at)
SELECT
    gen_random_uuid(),
    mh.reference_id,
    mh.entity_type,
    mh.event_type,
    mh.record_hash,
    'anchored',
    mh.transaction_hash,
    mh.block_number,
    'TradeShield Local Mock Chain',
    '0x' || substr(encode(digest('TradeShield Local Mock Chain:tradeshield-mock-contract-deployment-2026', 'sha256'), 'hex'), 1, 40),
    mn.ts
FROM mock_hashes mh
CROSS JOIN mock_now mn
ON CONFLICT (reference_id, entity_type) DO NOTHING;

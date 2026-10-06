"""
TradeShield * MOCK blockchain integrity layer.

IMPORTANT: This is a MOCK proof layer for demonstration only.

It is NOT a real blockchain.
It does NOT submit real transactions.
It does NOT use Web3.py, Hardhat, or any real chain client.
It does NOT replace PostgreSQL, which remains the system of record.

What it does:
- Generates deterministic-looking MOCK proof records for critical TradeShield
  events (successful trade executions and blocked/security events).
- Stores mock proof metadata in the `blockchain_proofs` table.
- Provides a mock "verify" check that recomputes the stored mock record hash
  from the same canonical inputs and compares it to the stored value.

Mock values are intentionally clearly fake:
- network = "TradeShield Local Mock Chain"
- contract_address = deterministic-looking 0x... address
- record_hash / transaction_hash = 64-char hex strings
- block_number = deterministic-looking integer
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import TypedDict
from uuid import UUID

# ---------------------------------------------------------------------------
# MOCK constants
# ---------------------------------------------------------------------------

MOCK_NETWORK = "TradeShield Local Mock Chain"

# A fixed mock deployment salt so the mock contract address is stable across
# restarts. This is NOT a real contract deployment.
_MOCK_CONTRACT_SALT = "tradeshield-mock-contract-deployment-2026"

# Mock block range so numbers look realistic rather than arbitrary.
MOCK_BLOCK_BASE = 882100
MOCK_BLOCK_SPAN = 99899


def _hex(bytes_: bytes, length: int) -> str:
    return bytes_.hex()


def mock_record_hash(reference_id: str, entity_type: str, event_type: str,
                     created_at_iso: str) -> str:
    """
    Deterministic MOCK record hash.

    The same canonical inputs always produce the same mock hash. This is SHA-256
    applied to a stable string -- the output LOOKS like a real hash, but in this
    codebase it is used as a MOCK proof marker, not as a real chain commitment.
    """
    canonical = ":".join([
        entity_type,
        str(reference_id),
        event_type,
        created_at_iso,
    ])
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def mock_transaction_hash(proof_id: UUID, network: str) -> str:
    """
    Deterministic MOCK transaction hash.
    """
    canonical = f"{network}:tx:{proof_id}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def mock_block_number(proof_id: UUID) -> int:
    """
    Deterministic MOCK block number.
    """
    h = int(hashlib.sha256(str(proof_id).encode("utf-8")).hexdigest(), 16)
    return MOCK_BLOCK_BASE + (h % MOCK_BLOCK_SPAN)


def mock_contract_address(network: str) -> str:
    """
    Deterministic MOCK contract address.
    """
    h = hashlib.sha256(f"{network}:{_MOCK_CONTRACT_SALT}".encode("utf-8")).hexdigest()
    return "0x" + h[:40]


class MockProofCreated(TypedDict):
    proof_id: UUID
    reference_id: str
    entity_type: str
    event_type: str
    record_hash: str
    blockchain_status: str
    transaction_hash: str
    block_number: int
    network: str
    contract_address: str
    created_at: datetime


def create_mock_proof(
    *,
    reference_id: str,
    entity_type: str,
    event_type: str,
    created_at: datetime | None = None,
) -> MockProofCreated:
    """
    Create a MOCK blockchain proof record for a critical TradeShield event.

    Parameters are the minimal, non-sensitive metadata needed to anchor a proof
    reference. Nothing sensitive is hashed or stored here.

    Returns the created mock proof payload.
    """
    now = created_at or datetime.now(timezone.utc)
    created_at_iso = now.isoformat()

    record_hash = mock_record_hash(
        reference_id=reference_id,
        entity_type=entity_type,
        event_type=event_type,
        created_at_iso=created_at_iso,
    )

    # Build the proof row first so we can derive the tx hash from the proof id.
    proof_id = UUID(hex=hashlib.sha256(
        f"mock-proof:{reference_id}:{entity_type}:{event_type}:{created_at_iso}".encode("utf-8")
    ).hexdigest()[:32].ljust(32, "0") if False else None)  # type: ignore[arg-type]

    # Deterministic proof id (mocks do not need real randomness here).
    proof_id = UUID(int=0)  # placeholder, replaced below
    raw = hashlib.sha256(
        f"mock-proof:{reference_id}:{entity_type}:{event_type}:{created_at_iso}".encode("utf-8")
    ).digest()
    proof_id = UUID(bytes=raw[:16])

    transaction_hash = mock_transaction_hash(proof_id=proof_id, network=MOCK_NETWORK)
    block_number = mock_block_number(proof_id=proof_id)
    contract_address = mock_contract_address(network=MOCK_NETWORK)

    return {
        "proof_id": proof_id,
        "reference_id": reference_id,
        "entity_type": entity_type,
        "event_type": event_type,
        "record_hash": record_hash,
        "blockchain_status": "anchored",
        "transaction_hash": transaction_hash,
        "block_number": block_number,
        "network": MOCK_NETWORK,
        "contract_address": contract_address,
        "created_at": now,
    }


def recompute_mock_record_hash(proof: dict) -> str:
    """
    Recompute the mock record hash from the stored proof metadata.

    This is the core of the mock verify flow: if the stored payload has not
    changed, the recomputed hash equals the stored record_hash.
    """
    return mock_record_hash(
        reference_id=str(proof["reference_id"]),
        entity_type=str(proof["entity_type"]),
        event_type=str(proof["event_type"]),
        created_at_iso=str(proof["created_at"].isoformat()),
    )


def verify_mock_proof(proof: dict) -> dict:
    """
    MOCK verification result for a stored proof.

    Returns a clearly-labelled mock verification response.
    """
    recomputed = recompute_mock_record_hash(proof)
    matches = (recomputed == str(proof.get("record_hash", "")))

    return {
        "verified": bool(matches),
        "mock": True,
        "record_hash": str(proof.get("record_hash", "")),
        "transaction_hash": str(proof.get("transaction_hash", "")),
        "block_number": int(proof.get("block_number", 0)),
        "network": str(proof.get("network", MOCK_NETWORK)),
        "contract_address": str(proof.get("contract_address", "")),
        "recomputed_record_hash": recomputed,
    }


def is_valid_mock_hash(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{64}", value or ""))

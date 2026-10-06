"""
TradeShield * MOCK blockchain proof API.

All endpoints are admin-only and return clearly-labelled MOCK data.

TradeShield's PostgreSQL database is the system of record. This API does not
write to any chain and does not perform real cryptographic commitments.
"""

from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from ..blockchain import (
    MOCK_NETWORK,
    create_mock_proof,
    is_valid_mock_hash,
    recompute_mock_record_hash,
    verify_mock_proof,
)
from ..db import fetch_all, fetch_one, run
from ..errors import ApiError
from ..security import admin_required

bp = Blueprint("blockchain", __name__, url_prefix="/api/blockchain")


def _parse_paging() -> tuple[int, int]:
    try:
        limit = int(request.args.get("limit", 50))
        offset = int(request.args.get("offset", 0))
    except ValueError as exc:
        raise ApiError(422, "VALIDATION_ERROR",
                       "limit and offset must be integers.") from exc
    if not (1 <= limit <= 200) or offset < 0:
        raise ApiError(422, "VALIDATION_ERROR",
                       "limit must be 1..200 and offset must be >= 0.")
    return limit, offset


@bp.get("/proofs")
@admin_required
def list_proofs():
    limit, offset = _parse_paging()
    rows = fetch_all(
        """SELECT proof_id, reference_id, entity_type, event_type,
                  record_hash, blockchain_status, transaction_hash,
                  block_number, network, contract_address, created_at
           FROM blockchain_proofs
           ORDER BY created_at DESC
           LIMIT %s OFFSET %s""",
        (limit, offset),
    )
    total = fetch_one("SELECT count(*) AS n FROM blockchain_proofs")["n"]
    return jsonify({
        "data": {
            "items": rows,
            "total": total,
            "mock": True,
            "network": MOCK_NETWORK,
        }
    }), 200


@bp.get("/proofs/<uuid:proof_id>")
@admin_required
def get_proof(proof_id):
    row = fetch_one(
        """SELECT proof_id, reference_id, entity_type, event_type,
                  record_hash, blockchain_status, transaction_hash,
                  block_number, network, contract_address, created_at
           FROM blockchain_proofs
           WHERE proof_id = %s""",
        (str(proof_id),),
    )
    if not row:
        raise ApiError(404, "PROOF_NOT_FOUND", "Mock proof record not found.")
    return jsonify({
        "data": row,
        "mock": True,
        "network": MOCK_NETWORK,
    }), 200


@bp.get("/proofs/<uuid:proof_id>/verify")
@admin_required
def verify_proof(proof_id):
    """
    MOCK verification endpoint.

    Recomputes the stored mock record hash from the proof's own metadata and
    compares it to the stored record_hash. The result is labelled mock.
    """
    row = fetch_one(
        """SELECT proof_id, reference_id, entity_type, event_type,
                  record_hash, blockchain_status, transaction_hash,
                  block_number, network, contract_address, created_at
           FROM blockchain_proofs
           WHERE proof_id = %s""",
        (str(proof_id),),
    )
    if not row:
        raise ApiError(404, "PROOF_NOT_FOUND", "Mock proof record not found.")

    result = verify_mock_proof(row)
    return jsonify({
        "data": result,
        "proof_id": str(proof_id),
        "mock": True,
        "network": MOCK_NETWORK,
    }), 200

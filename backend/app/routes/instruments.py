"""Instruments: the simulated market."""

from __future__ import annotations

from uuid import UUID

from flask import Blueprint, jsonify, request

from ..db import fetch_all, fetch_one
from ..errors import ApiError
from ..schemas import ASSET_TYPES
from ..security import auth_required

bp = Blueprint("instruments", __name__, url_prefix="/api/instruments")

SELECT = """SELECT instrument_id, symbol, name, asset_type, exchange,
                  current_price, tick_size, is_active, price_updated_at"""


def _int_arg(name: str, default: int, maximum: int) -> int:
    raw = request.args.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ApiError(422, "VALIDATION_ERROR", f"{name} must be an integer.") from exc
    if value < 0 or value > maximum:
        raise ApiError(422, "VALIDATION_ERROR", f"{name} must be between 0 and {maximum}.")
    return value


@bp.get("")
@auth_required
def list_instruments():
    where: list[str] = []
    params: list = []

    asset_type = request.args.get("asset_type")
    if asset_type:
        if asset_type not in ASSET_TYPES:
            raise ApiError(422, "VALIDATION_ERROR",
                           f"asset_type must be one of {', '.join(ASSET_TYPES)}.")
        where.append("asset_type = %s")
        params.append(asset_type)

    active = request.args.get("active")
    if active is not None:
        if active.lower() in ("true", "1", "yes"):
            where.append("is_active = %s")
            params.append(True)
        elif active.lower() in ("false", "0", "no"):
            where.append("is_active = %s")
            params.append(False)

    search = request.args.get("q", "").strip()
    if search:
        where.append("(symbol ILIKE %s OR name ILIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])

    sql = SELECT + " FROM instruments"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY symbol LIMIT %s OFFSET %s"
    params.extend([_int_arg("limit", 100, 500), _int_arg("offset", 0, 100_000)])

    return jsonify({"data": fetch_all(sql, tuple(params))}), 200


@bp.get("/<key>")
@auth_required
def instrument_detail(key: str):
    """Detail by instrument UUID or ticker symbol."""
    try:
        UUID(key)
    except ValueError:
        row = fetch_one(SELECT + " FROM instruments WHERE upper(symbol) = upper(%s)",
                        (key,))
    else:
        row = fetch_one(SELECT + " FROM instruments WHERE instrument_id = %s", (key,))
    if not row:
        raise ApiError(404, "INSTRUMENT_NOT_FOUND", "Instrument not found.")
    return jsonify({"data": row}), 200

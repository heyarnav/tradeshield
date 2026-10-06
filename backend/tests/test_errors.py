"""SQLSTATE -> HTTP mapping and the guarantee that no database internals leak."""

from __future__ import annotations

import psycopg

from app.errors import ApiError, SQLSTATE_MAP, translate_db_error


def test_application_sqlstates_map_to_expected_http_errors():
    assert SQLSTATE_MAP["TS001"] == (403, "ORDER_BLOCKED",
                                     "Order blocked by security screening.")
    assert SQLSTATE_MAP["TS002"][0:2] == (422, "INSUFFICIENT_FUNDS")
    assert SQLSTATE_MAP["TS003"][0:2] == (422, "INSUFFICIENT_HOLDINGS")
    assert SQLSTATE_MAP["TS004"][0:2] == (422, "INVALID_ORDER")
    assert SQLSTATE_MAP["TS005"][0:2] == (422, "ENTITY_INACTIVE")
    assert SQLSTATE_MAP["TS006"][0:2] == (422, "LIMIT_PRICE_RULE")


def test_api_error_shape_matches_the_documented_contract():
    err = ApiError(403, "ORDER_BLOCKED", "Order blocked by security screening.")
    assert err.to_dict() == {
        "error": {"code": "ORDER_BLOCKED",
                  "message": "Order blocked by security screening."}
    }


def test_unique_violation_maps_to_conflict_without_leaking(db):
    try:
        db.execute(
            "INSERT INTO users (email, password_hash, full_name) VALUES (%s, %s, %s)",
            ("admin@tradeshield.dev", "x", "Duplicate"),
        )
    except psycopg.errors.DatabaseError as exc:
        api = translate_db_error(exc)
    else:  # pragma: no cover - the seeded email must always conflict
        raise AssertionError("expected a unique violation")
    assert (api.status, api.code) == (409, "CONFLICT")
    assert "duplicate key" not in api.message
    assert "uq_users_email" not in api.message
    assert "admin@tradeshield.dev" not in api.message


def test_check_violation_maps_to_validation_error(db):
    try:
        db.execute(
            "INSERT INTO users (email, password_hash, full_name) VALUES (%s, %s, %s)",
            ("definitely-not-an-email", "x", "Bad Email"),
        )
    except psycopg.errors.DatabaseError as exc:
        api = translate_db_error(exc)
    else:  # pragma: no cover
        raise AssertionError("expected a check violation")
    assert (api.status, api.code) == (422, "VALIDATION_ERROR")


def test_unknown_database_errors_become_a_generic_500(db):
    try:
        db.execute("SELECT * FROM table_that_does_not_exist")
    except psycopg.errors.DatabaseError as exc:
        api = translate_db_error(exc)
    else:  # pragma: no cover
        raise AssertionError("expected an error")
    assert (api.status, api.code) == (500, "INTERNAL_ERROR")
    assert "table_that_does_not_exist" not in api.message
    assert "psycopg" not in api.message

"""TradeShield Flask application factory."""

from __future__ import annotations

import ipaddress
import logging
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

import psycopg
from flask import Flask, jsonify
from flask_cors import CORS
from flask.json.provider import DefaultJSONProvider
from pydantic import ValidationError as PydanticValidationError
from werkzeug.exceptions import HTTPException

from .config import get_config
from .db import close_db
from .errors import ApiError, translate_db_error
from .schemas import format_validation_error

HTTP_STATUS_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    413: "PAYLOAD_TOO_LARGE",
    415: "UNSUPPORTED_MEDIA_TYPE",
    429: "TOO_MANY_REQUESTS",
}


class ApiJSONProvider(DefaultJSONProvider):
    """JSON numbers for money/quantity, ISO-8601 for timestamps, str for UUIDs."""

    @staticmethod
    def default(o):
        if isinstance(o, Decimal):
            return float(o)
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        if isinstance(o, UUID):
            return str(o)
        if isinstance(o, (ipaddress.IPv4Address, ipaddress.IPv6Address)):
            return str(o)
        return DefaultJSONProvider.default(o)


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(ApiError)
    def _api_error(exc: ApiError):  # noqa: ANN202
        return jsonify(exc.to_dict()), exc.status

    @app.errorhandler(PydanticValidationError)
    def _pydantic_error(exc: PydanticValidationError):  # noqa: ANN202
        return jsonify({
            "error": {"code": "VALIDATION_ERROR",
                      "message": format_validation_error(exc)}
        }), 422

    @app.errorhandler(psycopg.errors.DatabaseError)
    def _db_error(exc: psycopg.errors.DatabaseError):  # noqa: ANN202
        api_error = translate_db_error(exc)
        return jsonify(api_error.to_dict()), api_error.status

    @app.errorhandler(HTTPException)
    def _http_error(exc: HTTPException):  # noqa: ANN202
        code = HTTP_STATUS_CODES.get(exc.code, "HTTP_ERROR")
        message = exc.description or "The request could not be processed."
        if exc.code == 404:
            message = "The requested endpoint does not exist."
        elif exc.code == 415:
            message = "Content-Type must be application/json."
        return jsonify({"error": {"code": code, "message": message}}), exc.code

    @app.errorhandler(Exception)
    def _unhandled(exc: Exception):  # noqa: ANN202
        app.logger.exception("unhandled error")
        return jsonify({
            "error": {"code": "INTERNAL_ERROR",
                      "message": "Something went wrong. Please try again later."}
        }), 500


def create_app(config_overrides: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_mapping(get_config(config_overrides))
    app.json = ApiJSONProvider(app)

    logging.basicConfig(level=logging.INFO)

    origins = [o.strip() for o in app.config["CORS_ORIGINS"].split(",") if o.strip()]
    CORS(app, resources={r"/api/*": {"origins": origins}})
    app.logger.info("CORS allowed origins: %s", ", ".join(origins) or "(none)")

    if app.config.get("JWT_SECRET_IS_EPHEMERAL"):
        app.logger.warning(
            "JWT_SECRET is missing or shorter than 32 bytes -- using a random "
            "per-process secret. Set JWT_SECRET in .env; sessions will otherwise "
            "be invalidated on every restart."
        )
    if app.config.get("TRUST_CLIENT_IP_HEADER"):
        app.logger.warning(
            "TRUST_CLIENT_IP_HEADER is enabled: clients may choose the IP that "
            "order screening uses. This is a development/demo setting only."
        )

    app.teardown_appcontext(close_db)
    _register_error_handlers(app)

    from .routes import BLUEPRINTS

    for blueprint in BLUEPRINTS:
        app.register_blueprint(blueprint)

    return app

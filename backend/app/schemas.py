"""Pydantic request models.

Shape/type/range validation only -- every business rule (funds, holdings,
active account/instrument, screening) stays in PostgreSQL, per Phase 2 rules.
"""

from __future__ import annotations

import ipaddress
import re
from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic import ValidationError as PydanticValidationError

from .errors import ApiError

THREAT_CATEGORIES = (
    "malware", "phishing", "c2", "botnet", "fraud", "spam", "recon", "other",
)
INDICATOR_TYPES = ("ip", "domain", "url", "file_hash")
ASSET_TYPES = ("equity", "etf", "crypto", "index")

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DOMAIN_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}$")
_HASH_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def format_validation_error(exc: PydanticValidationError) -> str:
    """Turn pydantic errors into a short, safe message (max 3 issues)."""
    parts = []
    for err in exc.errors()[:3]:
        loc = ".".join(str(p) for p in err.get("loc", ())) or "body"
        parts.append(f"{loc}: {err.get('msg', 'invalid value')}")
    return "; ".join(parts)


def parse(model_cls, data):
    try:
        return model_cls.model_validate(data or {})
    except PydanticValidationError as exc:
        raise ApiError(422, "VALIDATION_ERROR", format_validation_error(exc)) from exc


class RegisterIn(BaseModel):
    model_config = ConfigDict(extra="ignore")  # role can never be set by a client

    email: str
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=100)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if not _EMAIL_RE.match(v) or len(v) > 255:
            raise ValueError("must be a valid email address")
        return v

    @field_validator("full_name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = (v or "").strip()
        if len(v) < 2:
            raise ValueError("must be at least 2 characters")
        return v


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    email: str
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return (v or "").strip().lower()


class OrderIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    instrument: str = Field(min_length=1, max_length=64)   # symbol or UUID
    side: Literal["BUY", "SELL"]
    order_type: Literal["MARKET", "LIMIT"]
    quantity: Decimal
    limit_price: Optional[Decimal] = None
    referrer_domain: Optional[str] = Field(default=None, max_length=255)
    referrer_url: Optional[str] = Field(default=None, max_length=2048)
    origin_ip: Optional[str] = None   # simulated source IP (dev demos only)

    @field_validator("quantity")
    @classmethod
    def _quantity(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("must be greater than 0")
        if -v.as_tuple().exponent > 6:
            raise ValueError("supports at most 6 decimal places")
        return v

    @field_validator("limit_price")
    @classmethod
    def _limit(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is None:
            return None
        if v <= 0:
            raise ValueError("must be greater than 0")
        if -v.as_tuple().exponent > 4:
            raise ValueError("supports at most 4 decimal places")
        return v

    @field_validator("referrer_domain")
    @classmethod
    def _domain(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v.strip() == "":
            return None
        v = v.strip().lower()
        if not _DOMAIN_RE.match(v):
            raise ValueError("must be a valid domain name")
        return v

    @field_validator("referrer_url")
    @classmethod
    def _url(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v.strip() == "":
            return None
        v = v.strip()
        if not v.lower().startswith(("http://", "https://")):
            raise ValueError("must start with http:// or https://")
        return v

    @field_validator("origin_ip")
    @classmethod
    def _ip(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v.strip() == "":
            return None
        try:
            return str(ipaddress.ip_address(v.strip()))
        except ValueError as exc:
            raise ValueError("must be a valid IP address") from exc

    # MARKET/LIMIT price rules are enforced in the orders route so the API can
    # return distinct codes (LIMIT_PRICE_REQUIRED / LIMIT_PRICE_NOT_ALLOWED);
    # the t2 trigger's TS006 check stays as the database backstop.


class OrderQuery(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: Optional[Literal["PENDING", "EXECUTED", "CANCELLED", "REJECTED"]] = None
    risk_status: Optional[Literal["CLEAR", "FLAGGED"]] = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class IndicatorIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    indicator_type: Literal["ip", "domain", "url", "file_hash"]
    value: str = Field(min_length=3, max_length=450)
    threat_category: Literal[
        "malware", "phishing", "c2", "botnet", "fraud", "spam", "recon", "other"
    ]
    confidence: int = Field(ge=0, le=100)
    source_id: Optional[UUID] = None
    source_name: Optional[str] = Field(default=None, max_length=100)
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    is_active: bool = True
    notes: Optional[str] = Field(default=None, max_length=255)

    @field_validator("value")
    @classmethod
    def _value(cls, v: str, info) -> str:
        v = v.strip()
        kind = info.data.get("indicator_type")
        if kind == "ip":
            try:
                return str(ipaddress.ip_address(v))
            except ValueError as exc:
                raise ValueError("must be a valid IP address") from exc
        if kind == "domain":
            v = v.lower()
            if not _DOMAIN_RE.match(v):
                raise ValueError("must be a valid domain name")
            return v
        if kind == "url":
            v = v.lower()
            if not v.lower().startswith(("http://", "https://")):
                raise ValueError("must start with http:// or https://")
            return v
        if kind == "file_hash":
            v = v.lower()
            if not _HASH_RE.match(v):
                raise ValueError("must be a 64-character SHA-256 hex digest")
            return v
        return v

    @field_validator("source_name")
    @classmethod
    def _source(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() if v else None


class IndicatorPatch(BaseModel):
    """Partial update -- identity fields (type/value) are immutable."""

    model_config = ConfigDict(extra="ignore")

    threat_category: Optional[Literal[
        "malware", "phishing", "c2", "botnet", "fraud", "spam", "recon", "other"
    ]] = None
    confidence: Optional[int] = Field(default=None, ge=0, le=100)
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def _seen_order(self) -> "IndicatorPatch":
        if (self.first_seen and self.last_seen
                and self.last_seen < self.first_seen):
            raise ValueError("last_seen must not be earlier than first_seen")
        return self


class SourceIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=2, max_length=100)
    description: Optional[str] = Field(default=None, max_length=255)
    contact_url: Optional[str] = Field(default=None, max_length=255)
    reliability: int = Field(default=3, ge=1, le=5)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("must be at least 2 characters")
        return v

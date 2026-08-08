"""Framework-neutral license format, editions, and entitlement evaluation."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
import json
import re
from typing import Protocol


MAX_LICENSE_BYTES = 64 * 1024
FEATURE_NAME = re.compile(r"^[a-z][a-z0-9.-]{0,63}$")
EDITION_FEATURES = {
    "community": frozenset({"dashboard", "messages", "transfers"}),
    "standard": frozenset({"dashboard", "messages", "transfers", "bbs", "location"}),
    "professional": frozenset({
        "dashboard", "messages", "transfers", "bbs", "location",
        "gps-history", "beacon", "local-web",
    }),
    "enterprise": frozenset({
        "dashboard", "messages", "transfers", "bbs", "location",
        "gps-history", "beacon", "local-web", "plugins", "organization-deployment",
    }),
}


class LicenseStatus(StrEnum):
    COMMUNITY = "community"
    VALID = "valid"
    EXPIRED = "expired"
    NOT_YET_VALID = "not-yet-valid"
    INVALID = "invalid"


class SignatureVerifier(Protocol):
    def verify(self, key_id: str, message: bytes, signature: bytes) -> bool: ...


@dataclass(frozen=True, slots=True)
class LicenseGrant:
    license_id: str
    edition: str
    subject: str
    subject_type: str
    organization: str | None
    deployment_id: str | None
    seats: int | None
    issued_at: datetime
    not_before: datetime
    expires_at: datetime | None
    features: frozenset[str]


@dataclass(frozen=True, slots=True)
class LicenseState:
    status: LicenseStatus
    edition: str
    features: frozenset[str]
    grant: LicenseGrant | None = None
    source: str | None = None
    reason: str = ""

    def is_enabled(self, feature: str) -> bool:
        return self.status in {LicenseStatus.COMMUNITY, LicenseStatus.VALID} and feature in self.features

    @property
    def organization(self) -> str | None:
        return None if self.grant is None else self.grant.organization

    @property
    def expires_at(self) -> datetime | None:
        return None if self.grant is None else self.grant.expires_at


def community_state(reason: str = "No license file installed") -> LicenseState:
    return LicenseState(LicenseStatus.COMMUNITY, "community",
                        EDITION_FEATURES["community"], reason=reason)


def evaluate_license(document: bytes | str, verifier: SignatureVerifier,
                     now: datetime | None = None, source: str | None = None) -> LicenseState:
    """Validate a bounded signed document and return a fail-closed entitlement state."""
    try:
        raw = document.encode("utf-8") if isinstance(document, str) else document
        if not raw or len(raw) > MAX_LICENSE_BYTES:
            raise ValueError("license file size is invalid")
        envelope = json.loads(raw)
        if not isinstance(envelope, dict) or set(envelope) != {"schema", "key_id", "payload", "signature"}:
            raise ValueError("license envelope fields are invalid")
        if envelope["schema"] != 1 or not isinstance(envelope["key_id"], str):
            raise ValueError("license schema or key identifier is invalid")
        payload = envelope["payload"]
        if not isinstance(payload, dict):
            raise ValueError("license payload is invalid")
        signed = canonical_signed_content(envelope["key_id"], payload)
        signature = _decode_base64url(envelope["signature"], 64)
        if not verifier.verify(envelope["key_id"], signed, signature):
            raise ValueError("license signature is invalid or its key is not trusted")
        grant = _parse_grant(payload)
        instant = (now or datetime.now(UTC)).astimezone(UTC)
        if instant < grant.not_before:
            return LicenseState(LicenseStatus.NOT_YET_VALID, grant.edition, frozenset(),
                                grant, source, "License is not valid yet")
        if grant.expires_at is not None and instant >= grant.expires_at:
            return LicenseState(LicenseStatus.EXPIRED, grant.edition, frozenset(),
                                grant, source, "License has expired")
        features = EDITION_FEATURES[grant.edition] | grant.features
        return LicenseState(LicenseStatus.VALID, grant.edition, features, grant, source)
    except (UnicodeError, ValueError, TypeError, json.JSONDecodeError) as error:
        return LicenseState(LicenseStatus.INVALID, "community", frozenset(),
                            source=source, reason=str(error))


def canonical_signed_content(key_id: str, payload: dict) -> bytes:
    return json.dumps({"schema": 1, "key_id": key_id, "payload": payload},
                      ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _parse_grant(payload: dict) -> LicenseGrant:
    allowed = {"license_id", "edition", "subject", "subject_type", "organization",
               "deployment_id", "seats", "issued_at", "not_before", "expires_at", "features"}
    if set(payload) - allowed:
        raise ValueError("license payload contains unsupported fields")
    required = {"license_id", "edition", "subject", "subject_type", "issued_at", "features"}
    if not required <= set(payload):
        raise ValueError("license payload is incomplete")
    license_id = _bounded_text(payload["license_id"], "license identifier", 128)
    edition = str(payload["edition"]).lower()
    if edition not in EDITION_FEATURES:
        raise ValueError("license edition is unsupported")
    subject = _bounded_text(payload["subject"], "license subject", 200)
    subject_type = str(payload["subject_type"])
    if subject_type not in {"individual", "organization"}:
        raise ValueError("license subject type is invalid")
    organization = _optional_text(payload.get("organization"), "organization", 200)
    deployment_id = _optional_text(payload.get("deployment_id"), "deployment identifier", 128)
    seats = payload.get("seats")
    if seats is not None and (isinstance(seats, bool) or not isinstance(seats, int) or not 1 <= seats <= 1_000_000):
        raise ValueError("license seat count is invalid")
    if subject_type == "organization" and not organization:
        raise ValueError("organizational licenses require an organization")
    issued_at = _timestamp(payload["issued_at"], "issued_at")
    not_before = _timestamp(payload.get("not_before", payload["issued_at"]), "not_before")
    expires_at = None if payload.get("expires_at") is None else _timestamp(payload["expires_at"], "expires_at")
    if not_before < issued_at or (expires_at is not None and expires_at <= not_before):
        raise ValueError("license validity interval is invalid")
    raw_features = payload["features"]
    if not isinstance(raw_features, list) or len(raw_features) > 256:
        raise ValueError("license feature list is invalid")
    features = frozenset(str(item) for item in raw_features)
    if len(features) != len(raw_features) or any(not FEATURE_NAME.fullmatch(item) for item in features):
        raise ValueError("license feature flag is invalid or duplicated")
    return LicenseGrant(license_id, edition, subject, subject_type, organization,
                        deployment_id, seats, issued_at, not_before, expires_at, features)


def _timestamp(value, field: str) -> datetime:
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError(f"license {field} is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"license {field} is invalid") from error
    if parsed.tzinfo is None:
        raise ValueError(f"license {field} must include a UTC offset")
    return parsed.astimezone(UTC)


def _bounded_text(value, field: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{field} is invalid")
    return value.strip()


def _optional_text(value, field: str, limit: int) -> str | None:
    return None if value is None else _bounded_text(value, field, limit)


def _decode_base64url(value, expected: int) -> bytes:
    if not isinstance(value, str) or len(value) > 256:
        raise ValueError("license signature encoding is invalid")
    try:
        decoded = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    except ValueError as error:
        raise ValueError("license signature encoding is invalid") from error
    if len(decoded) != expected:
        raise ValueError("license signature length is invalid")
    return decoded

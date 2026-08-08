from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from application.licensing import (
    LicenseStatus, canonical_signed_content, community_state, evaluate_license,
)
from platform_runtime.licensing import Ed25519KeyRing, LicenseDeployment


class LicensingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.private = Ed25519PrivateKey.generate()
        self.public = self.private.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        self.key_id = "test-2026"
        self.now = datetime(2026, 8, 8, 12, tzinfo=UTC)

    def payload(self, **changes) -> dict:
        payload = {
            "license_id": "license-001", "edition": "enterprise",
            "subject": "Emergency Communications Team",
            "subject_type": "organization", "organization": "Example ARES",
            "deployment_id": "district-4", "seats": 50,
            "issued_at": "2026-01-01T00:00:00Z",
            "not_before": "2026-01-01T00:00:00Z",
            "expires_at": "2027-01-01T00:00:00Z",
            "features": ["custom.reporting"],
        }
        payload.update(changes)
        return payload

    def document(self, payload: dict, key_id: str | None = None) -> bytes:
        key_id = key_id or self.key_id
        signature = self.private.sign(canonical_signed_content(key_id, payload))
        return json.dumps({
            "schema": 1, "key_id": key_id, "payload": payload,
            "signature": base64.urlsafe_b64encode(signature).rstrip(b"=").decode(),
        }).encode()

    def test_valid_signed_organizational_license_grants_edition_and_features(self) -> None:
        state = evaluate_license(
            self.document(self.payload()), Ed25519KeyRing({self.key_id: self.public}), self.now
        )
        self.assertEqual(state.status, LicenseStatus.VALID)
        self.assertEqual(state.edition, "enterprise")
        self.assertEqual(state.organization, "Example ARES")
        self.assertTrue(state.is_enabled("plugins"))
        self.assertTrue(state.is_enabled("custom.reporting"))

    def test_tampering_or_untrusted_key_fails_closed(self) -> None:
        raw = json.loads(self.document(self.payload()))
        raw["payload"]["edition"] = "professional"
        state = evaluate_license(json.dumps(raw), Ed25519KeyRing({self.key_id: self.public}), self.now)
        self.assertEqual(state.status, LicenseStatus.INVALID)
        self.assertEqual(state.features, frozenset())

    def test_expiration_and_not_before_are_enforced_in_utc(self) -> None:
        expired = evaluate_license(
            self.document(self.payload(expires_at="2026-08-01T00:00:00Z")),
            Ed25519KeyRing({self.key_id: self.public}), self.now,
        )
        future = evaluate_license(
            self.document(self.payload(issued_at="2026-09-01T00:00:00Z",
                                       not_before="2026-09-01T00:00:00Z")),
            Ed25519KeyRing({self.key_id: self.public}), self.now,
        )
        self.assertEqual(expired.status, LicenseStatus.EXPIRED)
        self.assertEqual(future.status, LicenseStatus.NOT_YET_VALID)

    def test_missing_license_uses_offline_community_edition(self) -> None:
        state = community_state()
        self.assertEqual(state.status, LicenseStatus.COMMUNITY)
        self.assertTrue(state.is_enabled("dashboard"))
        self.assertFalse(state.is_enabled("plugins"))

    def test_explicit_organizational_deployment_paths_are_loaded(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            license_path, keys_path = root / "site.license", root / "trusted.json"
            license_path.write_bytes(self.document(self.payload()))
            keys_path.write_text(json.dumps({
                "schema": 1,
                "keys": {self.key_id: base64.b64encode(self.public).decode()},
            }))
            deployment = LicenseDeployment(root / "user", {
                "MERCURYSKYPULSE_LICENSE_FILE": str(license_path),
                "MERCURYSKYPULSE_LICENSE_KEYS": str(keys_path),
            }, platform="linux")
            state = deployment.load()
            self.assertEqual(state.status, LicenseStatus.VALID)
            self.assertEqual(state.grant.deployment_id, "district-4")

    def test_machine_paths_are_cross_platform_and_user_path_is_fallback(self) -> None:
        root = Path("/tmp/user-data")
        self.assertEqual(
            LicenseDeployment(root, {}, "darwin").candidates("license.json")[0],
            Path("/Library/Application Support/MercurySkyPulse/license.json"),
        )
        self.assertEqual(
            LicenseDeployment(root, {"PROGRAMDATA": "D:/ProgramData"}, "win32")
            .candidates("license.json")[0],
            Path("D:/ProgramData/MercurySkyPulse/license.json"),
        )
        self.assertEqual(LicenseDeployment(root, {}, "linux").candidates("license.json")[1],
                         root / "license.json")

    def test_explicit_missing_license_is_invalid_not_silent_community(self) -> None:
        deployment = LicenseDeployment(
            Path("/unused"), {"MERCURYSKYPULSE_LICENSE_FILE": "/missing/site.license"},
            platform="linux",
        )
        self.assertEqual(deployment.load().status, LicenseStatus.INVALID)


if __name__ == "__main__":
    unittest.main()

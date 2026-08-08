"""Offline Ed25519 verification and organization-friendly license discovery."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import sys

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from application.licensing import LicenseState, LicenseStatus, community_state, evaluate_license


class Ed25519KeyRing:
    def __init__(self, keys: dict[str, bytes]) -> None:
        self._keys = {
            key_id: Ed25519PublicKey.from_public_bytes(value)
            for key_id, value in keys.items()
        }

    def verify(self, key_id: str, message: bytes, signature: bytes) -> bool:
        key = self._keys.get(key_id)
        if key is None:
            return False
        try:
            key.verify(signature, message)
            return True
        except InvalidSignature:
            return False


class LicenseDeployment:
    """Loads one license and trusted key registry from bounded fixed locations."""

    def __init__(self, user_data_directory: Path,
                 environment: dict[str, str] | None = None,
                 platform: str | None = None) -> None:
        self.user_data_directory = user_data_directory
        self.environment = os.environ if environment is None else environment
        self.platform = sys.platform if platform is None else platform

    def load(self) -> LicenseState:
        try:
            license_path = self._first_existing("MERCURYSKYPULSE_LICENSE_FILE", "license.json")
            if license_path is None:
                return community_state()
            key_path = self._first_existing("MERCURYSKYPULSE_LICENSE_KEYS", "license-public-keys.json")
            keys = {} if key_path is None else self._load_keys(key_path)
            document = self._read_bounded(license_path)
            return evaluate_license(document, Ed25519KeyRing(keys), source=str(license_path))
        except (OSError, ValueError, json.JSONDecodeError) as error:
            return LicenseState(LicenseStatus.INVALID, "community", frozenset(),
                                source=str(locals().get("license_path", "")), reason=str(error))

    def candidates(self, filename: str) -> tuple[Path, ...]:
        machine = self._machine_directory() / filename
        return (machine, self.user_data_directory / filename)

    def _first_existing(self, variable: str, filename: str) -> Path | None:
        explicit = self.environment.get(variable)
        if explicit:
            return Path(explicit).expanduser()
        candidates = self.candidates(filename)
        return next((path for path in candidates if path.is_file()), None)

    def _machine_directory(self) -> Path:
        if self.platform == "darwin":
            return Path("/Library/Application Support/MercurySkyPulse")
        if self.platform == "win32":
            base = self.environment.get("PROGRAMDATA", r"C:\ProgramData")
            return Path(base) / "MercurySkyPulse"
        return Path("/etc/mercury-skypulse")

    def _load_keys(self, path: Path) -> dict[str, bytes]:
        raw = json.loads(self._read_bounded(path))
        if not isinstance(raw, dict) or raw.get("schema") != 1 or not isinstance(raw.get("keys"), dict):
            raise ValueError("trusted license key registry is invalid")
        if len(raw["keys"]) > 32:
            raise ValueError("trusted license key registry is too large")
        keys = {}
        for key_id, encoded in raw["keys"].items():
            if not isinstance(key_id, str) or not key_id or len(key_id) > 64 or not isinstance(encoded, str):
                raise ValueError("trusted license key entry is invalid")
            try:
                value = base64.b64decode(encoded, validate=True)
            except ValueError as error:
                raise ValueError("trusted license public key encoding is invalid") from error
            if len(value) != 32:
                raise ValueError("trusted Ed25519 public key must be 32 bytes")
            keys[key_id] = value
        return keys

    @staticmethod
    def _read_bounded(path: Path) -> bytes:
        with path.open("rb") as stream:
            data = stream.read(64 * 1024 + 1)
        if len(data) > 64 * 1024:
            raise ValueError("license deployment file is too large")
        return data

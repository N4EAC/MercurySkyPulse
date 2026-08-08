"""Password-protected BBS mailbox, role policy, and file catalog."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import hmac
from pathlib import Path
import secrets
import shutil
import time
from uuid import uuid4

from PySide6.QtCore import QObject, Signal

from persistence.chat_repository import ChatRepository


SCRYPT_N = 1 << 14
SCRYPT_R = 8
SCRYPT_P = 1
KEY_BYTES = 32
CHALLENGE_SECONDS = 60
ROLE_RANK = {"user": 1, "operator": 2, "commander": 3}
EVENT_PERMISSION = {
    "bbs_private": "user",
    "bbs_file_request": "user",
    "bbs_bulletin": "operator",
    "bbs_file_announce": "operator",
}


@dataclass(frozen=True, slots=True)
class BbsMessage:
    id: str
    kind: str
    sender: str
    recipient: str | None
    subject: str
    body: str
    created_at: str
    status: str


@dataclass(frozen=True, slots=True)
class BbsFile:
    id: str
    name: str
    size: int
    checksum: str
    owner: str
    local_path: str | None
    availability: str
    created_at: str


class BbsService(QObject):
    folders_changed = Signal(object)
    messages_changed = Signal(object)
    files_changed = Signal(object)
    security_changed = Signal(bool, str)
    roles_changed = Signal(object)
    auth_changed = Signal(str)
    status_changed = Signal(str)
    error_received = Signal(str)

    def __init__(self, client, repository: ChatRepository,
                 file_transfer, storage_directory: Path, parent=None) -> None:
        super().__init__(parent)
        self.client = client
        self.repository = repository
        self.file_transfer = file_transfer
        self.storage_directory = storage_directory
        self.current_folder = "Inbox"
        self._commander_unlocked = False
        self._remote_role: str | None = None
        self._remote_call: str | None = None
        self._pending_password: str | None = None
        self._challenges: dict[str, tuple[str, bytes, float]] = {}
        client.bbs_event_received.connect(self._on_event)
        if hasattr(client, "session_disconnected"):
            client.session_disconnected.connect(self._clear_session)

    def start(self) -> None:
        self.folders_changed.emit(self.repository.list_bbs_folders())
        self.select_folder(self.current_folder)
        self._publish_files()
        self._publish_security()

    def select_folder(self, folder: str) -> None:
        if folder not in {name for _, name in self.repository.list_bbs_folders()}:
            return
        self.current_folder = folder
        self.messages_changed.emit(
            [BbsMessage(*row) for row in self.repository.list_bbs_messages(folder)]
        )

    def enable_protection(self, commander: str, password: str) -> None:
        try:
            already_enabled = self.repository.get_bbs_security()[0]
            if already_enabled and not self._commander_unlocked:
                raise ValueError("Unlock commander controls before changing the password")
            commander = self.client.normalize_callsign(commander)
            self._validate_password(password)
            salt = secrets.token_bytes(16)
            verifier = self._derive(password, salt)
            now = self._now()
            self.repository.set_bbs_security(True, salt, verifier, commander, now)
            self.repository.set_bbs_role(commander, "commander", now)
            self._commander_unlocked = True
            self._publish_security()
            self.status_changed.emit("BBS password protection enabled")
        except ValueError as error:
            self.error_received.emit(str(error))

    def unlock_commander(self, password: str) -> None:
        enabled, salt, verifier, _ = self.repository.get_bbs_security()
        if enabled and salt and verifier and self._password_matches(password, salt, verifier):
            self._commander_unlocked = True
            self._publish_security()
            self.status_changed.emit("Commander controls unlocked")
        else:
            self._commander_unlocked = False
            self.error_received.emit("Commander password is incorrect")

    def disable_protection(self) -> None:
        if not self._commander_unlocked:
            self.error_received.emit("Unlock commander controls first")
            return
        self.repository.set_bbs_security(False, None, None, None, self._now())
        self._commander_unlocked = False
        self._clear_session()
        self._publish_security()
        self.status_changed.emit("BBS password protection disabled; BBS is open")

    def set_role(self, callsign: str, role: str) -> None:
        try:
            if not self._commander_unlocked:
                raise ValueError("Unlock commander controls first")
            callsign = self.client.normalize_callsign(callsign)
            if role not in ROLE_RANK:
                raise ValueError("Unknown role")
            _, _, _, commander = self.repository.get_bbs_security()
            if callsign == commander and role != "commander":
                raise ValueError("The configured commander cannot be demoted")
            self.repository.set_bbs_role(callsign, role, self._now())
            self._publish_security()
            self.status_changed.emit(f"{callsign} role set to {role}")
        except ValueError as error:
            self.error_received.emit(str(error))

    def authenticate(self, callsign: str, password: str) -> None:
        try:
            callsign = self.client.normalize_callsign(callsign)
            if not password or len(password) > 256:
                raise ValueError("Enter the BBS password")
            self._pending_password = password
            self._remote_call = callsign
            self.client.send_file_event(
                "bbs_auth_begin", str(uuid4()), self._now(), callsign=callsign
            )
            self.auth_changed.emit("Authenticating…")
        except (RuntimeError, ValueError) as error:
            self._pending_password = None
            self.error_received.emit(str(error))

    def send_private(self, sender: str, recipient: str, subject: str, body: str) -> None:
        try:
            sender = self.client.normalize_callsign(sender)
            recipient = self.client.normalize_callsign(recipient)
            subject, body = self._validate_content(subject, body)
            message_id, created = str(uuid4()), self._now()
            self.client.send_file_event("bbs_private", message_id, created,
                sender=sender, recipient=recipient, subject=subject, body=body)
            self.repository.save_bbs_message(message_id, "Outbox", "private",
                sender, recipient, subject, body, created, "sent")
            self.status_changed.emit("Private message sent")
            self.select_folder(self.current_folder)
        except (RuntimeError, ValueError) as error:
            self.error_received.emit(str(error))

    def post_bulletin(self, sender: str, subject: str, body: str) -> None:
        try:
            sender = self.client.normalize_callsign(sender)
            subject, body = self._validate_content(subject, body)
            message_id, created = str(uuid4()), self._now()
            self.client.send_file_event("bbs_bulletin", message_id, created,
                sender=sender, subject=subject, body=body)
            self.repository.save_bbs_message(message_id, "Bulletins", "bulletin",
                sender, None, subject, body, created, "posted")
            self.status_changed.emit("Bulletin posted")
            self.select_folder(self.current_folder)
        except (RuntimeError, ValueError) as error:
            self.error_received.emit(str(error))

    def upload(self, owner: str, path_value: str) -> None:
        source = Path(path_value)
        try:
            owner = self.client.normalize_callsign(owner)
            if not source.is_file():
                raise ValueError("Select a regular file")
            size = source.stat().st_size
            if size > 100 * 1024 * 1024:
                raise ValueError("BBS files are limited to 100 MiB")
            self.storage_directory.mkdir(parents=True, exist_ok=True)
            file_id = str(uuid4())
            destination = self.storage_directory / f"{file_id}{source.suffix}"
            shutil.copy2(source, destination)
            checksum, created = self._sha256(destination), self._now()
            self.repository.save_bbs_file(file_id, source.name, size, checksum,
                owner, str(destination), "local", created)
            self.client.send_file_event("bbs_file_announce", file_id, created,
                name=source.name, size=size, sha256=checksum, owner=owner)
            self._publish_files()
            self.status_changed.emit("File uploaded to local BBS and advertised")
        except (OSError, RuntimeError, ValueError) as error:
            self.error_received.emit(str(error))

    def download(self, file_id: str) -> None:
        row = self.repository.get_bbs_file(file_id)
        if not row:
            self.error_received.emit("Select a BBS file")
            return
        record = BbsFile(*row)
        if record.local_path and Path(record.local_path).is_file():
            self.status_changed.emit(f"Already stored locally: {record.local_path}")
            return
        try:
            self.client.send_file_event("bbs_file_request", record.id, self._now())
            self.status_changed.emit(f"Requested {record.name}")
        except RuntimeError as error:
            self.error_received.emit(str(error))

    def _on_event(self, envelope) -> None:
        try:
            values = envelope.values or {}
            if envelope.kind == "bbs_auth_begin":
                self._begin_remote_auth(values)
            elif envelope.kind == "bbs_auth_challenge":
                self._answer_challenge(envelope, values)
            elif envelope.kind == "bbs_auth_proof":
                self._verify_proof(envelope, values)
            elif envelope.kind == "bbs_auth_result":
                self._receive_auth_result(values)
            elif envelope.kind == "bbs_access_denied":
                self.error_received.emit(str(values.get("reason", "BBS access denied"))[:200])
            elif envelope.kind in EVENT_PERMISSION:
                if not self._authorized(EVENT_PERMISSION[envelope.kind]):
                    self._deny(envelope.kind)
                    return
                if envelope.kind == "bbs_private":
                    self._receive_message(envelope, values, "private", "Inbox")
                elif envelope.kind == "bbs_bulletin":
                    self._receive_message(envelope, values, "bulletin", "Bulletins")
                elif envelope.kind == "bbs_file_announce":
                    self._receive_file_announce(envelope, values)
                else:
                    self._serve_file(envelope.message_id)
        except (KeyError, OSError, RuntimeError, TypeError, ValueError) as error:
            self.error_received.emit(f"Invalid BBS event: {error}")

    def _begin_remote_auth(self, values: dict) -> None:
        enabled, salt, _, _ = self.repository.get_bbs_security()
        callsign = self.client.normalize_callsign(str(values["callsign"]))
        if not enabled or not salt:
            self._remote_call, self._remote_role = callsign, "operator"
            self._send_auth_result(True, "operator", "BBS protection is disabled")
            return
        challenge_id, nonce = str(uuid4()), secrets.token_bytes(32)
        self._challenges = {challenge_id: (callsign, nonce, time.monotonic() + CHALLENGE_SECONDS)}
        self.client.send_file_event("bbs_auth_challenge", challenge_id, self._now(),
            nonce=base64.b64encode(nonce).decode("ascii"),
            salt=base64.b64encode(salt).decode("ascii"), algorithm="scrypt-hmac-sha256-v1")

    def _answer_challenge(self, envelope, values: dict) -> None:
        if not self._pending_password or not self._remote_call:
            return
        if values.get("algorithm") != "scrypt-hmac-sha256-v1":
            raise ValueError("Unsupported BBS authentication algorithm")
        salt = base64.b64decode(str(values["salt"]), validate=True)
        nonce = base64.b64decode(str(values["nonce"]), validate=True)
        if len(salt) != 16 or len(nonce) != 32:
            raise ValueError("Invalid BBS authentication challenge")
        key = self._derive(self._pending_password, salt)
        proof = hmac.new(key, self._proof_input(nonce, self._remote_call), hashlib.sha256)
        self._pending_password = None
        self.client.send_file_event("bbs_auth_proof", envelope.message_id, self._now(),
            callsign=self._remote_call, proof=base64.b64encode(proof.digest()).decode("ascii"))

    def _verify_proof(self, envelope, values: dict) -> None:
        challenge = self._challenges.pop(envelope.message_id, None)
        enabled, _, verifier, _ = self.repository.get_bbs_security()
        if not enabled or not verifier or not challenge:
            self._send_auth_result(False, None, "Authentication challenge expired")
            return
        callsign, nonce, deadline = challenge
        supplied_call = self.client.normalize_callsign(str(values["callsign"]))
        try:
            supplied = base64.b64decode(str(values["proof"]), validate=True)
        except ValueError:
            supplied = b""
        expected = hmac.new(verifier, self._proof_input(nonce, callsign), hashlib.sha256).digest()
        if time.monotonic() <= deadline and supplied_call == callsign and hmac.compare_digest(supplied, expected):
            self._remote_call = callsign
            self._remote_role = self.repository.get_bbs_role(callsign)
            self._send_auth_result(True, self._remote_role, "Authenticated")
        else:
            self._remote_call = self._remote_role = None
            self._send_auth_result(False, None, "Authentication failed")

    def _receive_auth_result(self, values: dict) -> None:
        if values.get("ok") is True and str(values.get("role")) in ROLE_RANK:
            role = str(values["role"])
            self.auth_changed.emit(f"Authenticated as {self._remote_call} ({role})")
            self.status_changed.emit(str(values.get("message", "Authenticated"))[:200])
        else:
            self._remote_call = None
            self.auth_changed.emit("Not authenticated")
            self.error_received.emit(str(values.get("message", "Authentication failed"))[:200])

    def _send_auth_result(self, ok: bool, role: str | None, message: str) -> None:
        self.client.send_file_event("bbs_auth_result", str(uuid4()), self._now(),
            ok=ok, role=role, message=message)

    def _authorized(self, required: str) -> bool:
        enabled, _, _, _ = self.repository.get_bbs_security()
        if not enabled:
            return True
        return self._remote_role is not None and ROLE_RANK[self._remote_role] >= ROLE_RANK[required]

    def _deny(self, operation: str) -> None:
        self.client.send_file_event("bbs_access_denied", str(uuid4()), self._now(),
            operation=operation, reason="Authenticate with a role permitted for this operation")
        self.status_changed.emit(f"Rejected unauthorized {operation} request")

    def _clear_session(self) -> None:
        self._remote_role = self._remote_call = self._pending_password = None
        self._challenges.clear()
        self.auth_changed.emit("Not authenticated")

    def _receive_message(self, envelope, values, kind: str, folder: str) -> None:
        sender = self.client.normalize_callsign(str(values["sender"]))
        if self.repository.get_bbs_security()[0] and sender != self._remote_call:
            raise ValueError("sender does not match authenticated callsign")
        recipient = values.get("recipient")
        if recipient is not None:
            recipient = self.client.normalize_callsign(str(recipient))
        subject, body = self._validate_content(str(values["subject"]), str(values["body"]))
        self.repository.save_bbs_message(envelope.message_id, folder, kind, sender,
            recipient, subject, body, envelope.timestamp, "received")
        self.select_folder(self.current_folder)
        self.status_changed.emit(f"Received {kind} from authenticated session")

    def _receive_file_announce(self, envelope, values) -> None:
        name, size = Path(str(values["name"])).name, int(values["size"])
        checksum = str(values["sha256"]).lower()
        owner = self.client.normalize_callsign(str(values["owner"]))
        if self.repository.get_bbs_security()[0] and owner != self._remote_call:
            raise ValueError("owner does not match authenticated callsign")
        if not name or not 0 <= size <= 100 * 1024 * 1024 or len(checksum) != 64:
            raise ValueError("invalid BBS file announcement")
        int(checksum, 16)
        existing = self.repository.get_bbs_file(envelope.message_id)
        if existing and existing[5]:
            raise ValueError("remote file identifier collides with a local upload")
        self.repository.save_bbs_file(envelope.message_id, name, size, checksum,
            owner, None, "remote", envelope.timestamp)
        self._publish_files()

    def _serve_file(self, file_id: str) -> None:
        row = self.repository.get_bbs_file(file_id)
        if not row:
            return
        record = BbsFile(*row)
        if record.local_path:
            path = Path(record.local_path)
            if path.is_file() and self._sha256(path) == record.checksum:
                self.file_transfer.send_raw_file(str(path))

    def _publish_files(self) -> None:
        self.files_changed.emit([BbsFile(*row) for row in self.repository.list_bbs_files()])

    def _publish_security(self) -> None:
        enabled, _, _, commander = self.repository.get_bbs_security()
        state = "Commander unlocked" if self._commander_unlocked else "Commander locked"
        self.security_changed.emit(enabled, f"{state} · {commander or 'not configured'}")
        self.roles_changed.emit(self.repository.list_bbs_roles())

    @staticmethod
    def _validate_password(password: str) -> None:
        if len(password) < 10 or len(password) > 256:
            raise ValueError("Password must contain 10–256 characters")

    @staticmethod
    def _derive(password: str, salt: bytes) -> bytes:
        return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=SCRYPT_N,
            r=SCRYPT_R, p=SCRYPT_P, dklen=KEY_BYTES, maxmem=64 * 1024 * 1024)

    @classmethod
    def _password_matches(cls, password: str, salt: bytes, verifier: bytes) -> bool:
        try:
            return hmac.compare_digest(cls._derive(password, salt), verifier)
        except (UnicodeError, ValueError):
            return False

    @staticmethod
    def _proof_input(nonce: bytes, callsign: str) -> bytes:
        return b"MercurySkyPulse-BBS-v1\0" + nonce + callsign.encode("ascii")

    @staticmethod
    def _validate_content(subject: str, body: str) -> tuple[str, str]:
        subject, body = subject.strip(), body.strip()
        if not subject or len(subject) > 120:
            raise ValueError("Subject must contain 1–120 characters")
        if not body or len(body) > 4096:
            raise ValueError("Body must contain 1–4096 characters")
        return subject, body

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

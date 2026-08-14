"""Session-scoped compressed voice-message transfer above Mercury ARQ."""

from __future__ import annotations

import base64
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
import hashlib
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QObject, QTimer, Signal


MAX_VOICE_BYTES = 256 * 1024
VOICE_CHUNK_BYTES = 384
MERCURY_QUEUE_LOW_WATER_BYTES = 256
VOICE_RESPONSE_TIMEOUT_MS = 90_000
COOLDOWN_SECONDS = 120
ACTIVE_TRANSFER_STATES = frozenset({"queued", "transmitting", "receiving", "verifying"})
FILE_TRANSFER_BUSY_STATES = frozenset({"offered", "transferring", "paused", "verifying"})


@dataclass(frozen=True, slots=True)
class VoiceMessage:
    id: str
    direction: str
    status: str
    path: str
    size: int
    checksum: str
    mime_type: str
    transferred: int = 0

    @property
    def progress(self) -> int:
        return 100 if not self.size else min(100, int(self.transferred * 100 / self.size))


class VoiceMessageService(QObject):
    messages_changed = Signal(object)
    availability_changed = Signal(bool, str)
    error_received = Signal(str)
    delivered = Signal(str)

    def __init__(self, client, storage_directory: Path, parent=None) -> None:
        super().__init__(parent)
        self.client = client
        self.storage_directory = storage_directory
        self._connected = False
        self._peer_compatible = False
        self._good_bitrate_samples = 0
        self._poor_bitrate_samples = 0
        self._link_usable = False
        self._file_busy = False
        self._messages: dict[str, VoiceMessage] = {}
        self._outgoing_id: str | None = None
        self._cooldown_until: datetime | None = None
        self._capability_ack_sent = False
        self._mercury_queued_bytes = 0
        self._awaiting_ack_offset: int | None = None
        self._pump_timer = QTimer(self)
        self._pump_timer.setInterval(250)
        self._pump_timer.timeout.connect(self._pump)
        self._response_timer = QTimer(self)
        self._response_timer.setSingleShot(True)
        self._response_timer.setInterval(VOICE_RESPONSE_TIMEOUT_MS)
        self._response_timer.timeout.connect(self._response_timeout)
        self._cooldown_timer = QTimer(self)
        self._cooldown_timer.setSingleShot(True)
        self._cooldown_timer.timeout.connect(self._publish_availability)
        client.session_connected.connect(self._session_connected)
        client.session_disconnected.connect(self._session_disconnected)
        client.voice_event_received.connect(self._on_event)
        if hasattr(client, "queued_bytes_changed"):
            client.queued_bytes_changed.connect(self.set_mercury_buffer)

    def set_mercury_buffer(self, queued_bytes: int) -> None:
        self._mercury_queued_bytes = max(0, int(queued_bytes))
        if (self._outgoing_id and self._awaiting_ack_offset is None
                and self._mercury_queued_bytes <= MERCURY_QUEUE_LOW_WATER_BYTES):
            self._pump()

    def set_modem_bitrate(self, bitrate_bps: int) -> None:
        if int(bitrate_bps) >= 500:
            self._good_bitrate_samples += 1
            self._poor_bitrate_samples = 0
            if self._good_bitrate_samples >= 3:
                self._link_usable = True
        elif int(bitrate_bps) < 350:
            self._poor_bitrate_samples += 1
            self._good_bitrate_samples = 0
            if self._poor_bitrate_samples >= 2:
                self._link_usable = False
        self._publish_availability()

    def set_file_transfers(self, transfers) -> None:
        self._file_busy = any(
            item.status in FILE_TRANSFER_BUSY_STATES for item in transfers
        )
        self._publish_availability()

    def send_recording(self, path_value: str, mime_type: str) -> bool:
        available, reason = self.availability()
        if not available:
            self.error_received.emit(reason)
            return False
        path = Path(path_value)
        try:
            size = path.stat().st_size
            if not path.is_file() or size < 1 or size > MAX_VOICE_BYTES:
                raise ValueError("Voice recording must contain 1 byte to 256 KiB")
            if mime_type not in {"audio/mp4", "audio/ogg", "audio/webm"}:
                raise ValueError("Unsupported voice recording format")
            message_id = str(uuid4())
            message = VoiceMessage(
                message_id, "outgoing", "queued", str(path), size,
                self._sha256(path), mime_type,
            )
            self._messages[message_id] = message
            self._outgoing_id = message_id
            self._emit()
            self._send("voice_offer", message_id, size=size,
                       sha256=message.checksum, mime=mime_type, duration_ms=10_000)
            self._response_timer.start()
            self._publish_availability()
            return True
        except (OSError, RuntimeError, ValueError) as error:
            self.error_received.emit(str(error))
            return False

    def availability(self) -> tuple[bool, str]:
        if not self._connected:
            return False, "Connect to a station before sending voice"
        if not self._peer_compatible:
            return False, "Connected station does not advertise compatible voice messages"
        if self._file_busy:
            return False, "Voice is unavailable while a file transfer is pending"
        if any(item.status in ACTIVE_TRANSFER_STATES for item in self._messages.values()):
            return False, "Finish the current voice message first"
        if not self._link_usable:
            return False, "Voice requires a sustained link bitrate of at least 500 bps"
        if self._cooldown_until and datetime.now(UTC) < self._cooldown_until:
            seconds = max(1, int((self._cooldown_until - datetime.now(UTC)).total_seconds()))
            return False, f"Voice cooldown: {seconds} seconds remaining"
        return True, "Record a voice message of up to 10 seconds"

    def transfer_busy(self) -> bool:
        return any(item.status in ACTIVE_TRANSFER_STATES for item in self._messages.values())

    def _session_connected(self, *_args) -> None:
        self._connected = True
        self._peer_compatible = False
        self._good_bitrate_samples = self._poor_bitrate_samples = 0
        self._link_usable = False
        self._capability_ack_sent = False
        self._send_capability(ack=False)
        self._publish_availability()

    def _session_disconnected(self) -> None:
        self._connected = self._peer_compatible = self._link_usable = False
        self._pump_timer.stop()
        self._response_timer.stop()
        self._awaiting_ack_offset = None
        for message_id, message in list(self._messages.items()):
            if message.status in ACTIVE_TRANSFER_STATES:
                self._delete(message.path)
                del self._messages[message_id]
        self._outgoing_id = None
        self._cooldown_until = None
        self._cooldown_timer.stop()
        self._capability_ack_sent = False
        self._emit()
        self._publish_availability()

    def _on_event(self, envelope) -> None:
        values = envelope.values or {}
        try:
            if envelope.kind == "voice_capability":
                mime_types = values.get("mime_types", [])
                self._peer_compatible = (
                    values.get("protocol") == 2 and isinstance(mime_types, list)
                    and bool({"audio/mp4", "audio/ogg", "audio/webm"} & set(mime_types))
                )
                if self._peer_compatible and not bool(values.get("ack", False)) \
                        and not self._capability_ack_sent:
                    self._capability_ack_sent = True
                    self._send_capability(ack=True)
            elif envelope.kind == "voice_offer":
                self._receive_offer(envelope.message_id, values)
            elif envelope.kind == "voice_accept":
                message = self._messages.get(envelope.message_id)
                if not message or message.direction != "outgoing" \
                        or message.status != "queued":
                    raise ValueError("unexpected voice acceptance")
                self._response_timer.stop()
                self._update(envelope.message_id, status="transmitting")
                self._outgoing_id = envelope.message_id
                self._pump_timer.start()
                self._pump()
            elif envelope.kind == "voice_chunk":
                self._receive_chunk(envelope.message_id, values)
            elif envelope.kind == "voice_chunk_ack":
                self._receive_chunk_ack(envelope.message_id, values)
            elif envelope.kind == "voice_complete":
                self._receive_complete(envelope.message_id)
            elif envelope.kind == "voice_result":
                self._receive_result(envelope.message_id, values)
        except (KeyError, OSError, RuntimeError, TypeError, ValueError) as error:
            self.error_received.emit(f"Invalid voice message: {error}")
        self._publish_availability()

    def _receive_offer(self, message_id: str, values: dict[str, object]) -> None:
        if self._file_busy or any(item.status in ACTIVE_TRANSFER_STATES for item in self._messages.values()):
            self._send("voice_result", message_id, result="busy")
            return
        size = int(values["size"])
        checksum = str(values["sha256"]).lower()
        mime = str(values["mime"])
        duration = int(values["duration_ms"])
        if (size < 1 or size > MAX_VOICE_BYTES or duration < 1 or duration > 10_000
                or mime not in {"audio/mp4", "audio/ogg", "audio/webm"}
                or len(checksum) != 64 or any(c not in "0123456789abcdef" for c in checksum)):
            raise ValueError("invalid voice offer")
        self.storage_directory.mkdir(parents=True, exist_ok=True)
        suffix = {"audio/mp4": ".m4a", "audio/ogg": ".ogg", "audio/webm": ".webm"}[mime]
        path = self.storage_directory / f".{message_id}{suffix}.part"
        path.write_bytes(b"")
        self._messages[message_id] = VoiceMessage(
            message_id, "incoming", "receiving", str(path), size, checksum, mime
        )
        self._emit()
        self._send("voice_accept", message_id)

    def _receive_chunk(self, message_id: str, values: dict[str, object]) -> None:
        message = self._messages[message_id]
        chunk = base64.b64decode(str(values["data"]), validate=True)
        offset = int(values["offset"])
        if (message.direction != "incoming" or message.status != "receiving"
                or offset != message.transferred or not chunk
                or len(chunk) > VOICE_CHUNK_BYTES
                or offset + len(chunk) > message.size):
            raise ValueError("unexpected voice chunk")
        with Path(message.path).open("ab") as stream:
            stream.write(chunk)
        confirmed = offset + len(chunk)
        self._update(message_id, transferred=confirmed)
        self._send("voice_chunk_ack", message_id, offset=confirmed)

    def _receive_chunk_ack(self, message_id: str, values: dict[str, object]) -> None:
        message = self._messages.get(message_id)
        confirmed = int(values["offset"])
        if (not message or message.direction != "outgoing"
                or message.status != "transmitting"
                or self._awaiting_ack_offset is None
                or confirmed != self._awaiting_ack_offset
                or confirmed <= message.transferred or confirmed > message.size):
            raise ValueError("unexpected voice chunk acknowledgement")
        self._response_timer.stop()
        self._awaiting_ack_offset = None
        self._update(message_id, transferred=confirmed)
        self._pump()

    def _receive_complete(self, message_id: str) -> None:
        message = self._messages[message_id]
        path = Path(message.path)
        if message.transferred != message.size or self._sha256(path) != message.checksum:
            self._delete(message.path)
            del self._messages[message_id]
            self._send("voice_result", message_id, result="failed")
            self._emit()
            return
        final = path.with_name(path.name.removeprefix(".").removesuffix(".part"))
        path.replace(final)
        self._update(message_id, status="received", path=str(final))
        self._send("voice_result", message_id, result="delivered")

    def _receive_result(self, message_id: str, values: dict[str, object]) -> None:
        message = self._messages.get(message_id)
        if not message:
            return
        result = str(values.get("result", "failed"))
        self._pump_timer.stop()
        self._response_timer.stop()
        self._awaiting_ack_offset = None
        if result == "delivered":
            self._update(message_id, status="delivered", transferred=message.size)
            self._cooldown_until = datetime.now(UTC) + timedelta(seconds=COOLDOWN_SECONDS)
            self._cooldown_timer.start(COOLDOWN_SECONDS * 1000)
            self.delivered.emit(message_id)
        else:
            self._update(message_id, status=result)
        self._outgoing_id = None

    def _pump(self) -> None:
        message = self._messages.get(self._outgoing_id or "")
        if not message or message.status != "transmitting" or self._file_busy:
            self._pump_timer.stop()
            return
        if self._awaiting_ack_offset is not None:
            return
        if self._mercury_queued_bytes > MERCURY_QUEUE_LOW_WATER_BYTES:
            return
        try:
            with Path(message.path).open("rb") as stream:
                stream.seek(message.transferred)
                chunk = stream.read(VOICE_CHUNK_BYTES)
            if not chunk:
                self._pump_timer.stop()
                self._update(message.id, status="verifying")
                self._send("voice_complete", message.id)
                self._response_timer.start()
                return
            if not self.client.file_write_ready():
                return
            self._send("voice_chunk", message.id, offset=message.transferred,
                       data=base64.b64encode(chunk).decode("ascii"))
            self._awaiting_ack_offset = message.transferred + len(chunk)
            self._response_timer.start()
        except (OSError, RuntimeError) as error:
            self._pump_timer.stop()
            self._update(message.id, status="failed")
            self.error_received.emit(str(error))

    def _response_timeout(self) -> None:
        message = self._messages.get(self._outgoing_id or "")
        if not message or message.status not in {"queued", "transmitting", "verifying"}:
            return
        self._pump_timer.stop()
        self._awaiting_ack_offset = None
        self._update(message.id, status="failed")
        self._outgoing_id = None
        self.error_received.emit(
            "Voice message timed out before the receiving station confirmed delivery"
        )

    def _send(self, kind: str, message_id: str, **values: object) -> None:
        self.client.send_file_event(kind, message_id, datetime.now(UTC).isoformat(), **values)

    def _send_capability(self, ack: bool) -> None:
        self._send("voice_capability", str(uuid4()), protocol=2,
                   mime_types=["audio/mp4", "audio/ogg", "audio/webm"],
                   maximum_seconds=10, maximum_bytes=MAX_VOICE_BYTES, ack=ack)

    def _update(self, message_id: str, **changes: object) -> None:
        self._messages[message_id] = replace(self._messages[message_id], **changes)
        self._emit()

    def _emit(self) -> None:
        self.messages_changed.emit(list(self._messages.values()))

    def _publish_availability(self) -> None:
        self.availability_changed.emit(*self.availability())

    @staticmethod
    def _sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @staticmethod
    def _delete(path_value: str) -> None:
        try:
            Path(path_value).unlink(missing_ok=True)
        except OSError:
            pass

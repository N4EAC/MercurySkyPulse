"""Application message protocol layered over a raw reliable byte transport."""

from __future__ import annotations

from datetime import UTC, datetime
import re

from PySide6.QtCore import QObject, Signal

from .messaging import FrameDecoder, encode_ack, encode_event, encode_message


CALLSIGN = re.compile(r"^[A-Z0-9][A-Z0-9/-]{0,14}$")


class ApplicationMessagingClient(QObject):
    state_changed = Signal(str)
    control_event = Signal(str)
    session_connected = Signal(str, str, int)
    session_disconnected = Signal()
    message_received = Signal(object)
    message_sent = Signal(str)
    message_delivered = Signal(str)
    file_event_received = Signal(object)
    location_received = Signal(object)
    ping_event_received = Signal(object)
    bbs_event_received = Signal(object)
    presence_received = Signal(object)
    voice_event_received = Signal(object)
    error_received = Signal(str)
    queued_bytes_changed = Signal(int)

    def __init__(self, transport, parent=None) -> None:
        super().__init__(parent)
        self.transport = transport
        self._decoder = FrameDecoder()
        transport.state_changed.connect(self.state_changed)
        transport.control_event.connect(self.control_event)
        transport.session_connected.connect(self.session_connected)
        transport.session_disconnected.connect(self.session_disconnected)
        transport.data_received.connect(self._read_data)
        transport.error_received.connect(self.error_received)
        if hasattr(transport, "queued_bytes_changed"):
            transport.queued_bytes_changed.connect(self.queued_bytes_changed)

    @staticmethod
    def normalize_callsign(value: str) -> str:
        call = value.strip().upper()
        if not CALLSIGN.fullmatch(call):
            raise ValueError("Callsign must be 1–15 letters, numbers, '/', or '-'")
        return call

    def start(self) -> None:
        self.transport.start()

    def stop(self) -> None:
        self.transport.stop()

    def configure_and_listen(self, local_call: str) -> None:
        call = self.normalize_callsign(local_call)
        self.transport.send_control(f"MYCALL {call}")
        self.transport.send_control("LISTEN ON")
        self.state_changed.emit("listening")

    def connect_station(self, local_call: str, remote_call: str) -> None:
        local = self.normalize_callsign(local_call)
        remote = self.normalize_callsign(remote_call)
        self.transport.send_control(f"MYCALL {local}")
        self.transport.send_control("LISTEN ON")
        self.transport.send_control(f"CONNECT {local} {remote}")
        self.state_changed.emit("linking")

    def disconnect_station(self) -> None:
        self.transport.send_control("DISCONNECT")

    def send_message(self, message_id: str, timestamp: str, text: str) -> None:
        self.transport.write(encode_message(message_id, timestamp, text))
        self.message_sent.emit(message_id)

    def send_file_event(self, kind: str, event_id: str, timestamp: str,
                        **values: object) -> None:
        self.transport.write(encode_event(kind, event_id, timestamp, **values))

    def send_presence(self, event_id: str, timestamp: str, state: str,
                      ttl_seconds: int) -> None:
        self.transport.write(encode_event(
            "presence", event_id, timestamp,
            state=state, ttl_seconds=ttl_seconds,
        ))

    def file_write_ready(self) -> bool:
        return self.transport.write_ready()

    def _read_data(self, data: bytes) -> None:
        for envelope in self._decoder.feed(data):
            if envelope.kind == "message":
                self.message_received.emit(envelope)
                try:
                    self.transport.write(encode_ack(
                        envelope.message_id, datetime.now(UTC).isoformat()
                    ))
                except (OSError, RuntimeError) as error:
                    self.error_received.emit(
                        f"Could not acknowledge received message: {error}"
                    )
            elif envelope.kind == "ack":
                self.message_delivered.emit(envelope.message_id)
            elif envelope.kind.startswith("file_"):
                self.file_event_received.emit(envelope)
            elif envelope.kind == "location":
                self.location_received.emit(envelope)
            elif envelope.kind.startswith("ping_"):
                self.ping_event_received.emit(envelope)
            elif envelope.kind.startswith("bbs_"):
                self.bbs_event_received.emit(envelope)
            elif envelope.kind == "presence":
                self.presence_received.emit(envelope)
            elif envelope.kind.startswith("voice_"):
                self.voice_event_received.emit(envelope)

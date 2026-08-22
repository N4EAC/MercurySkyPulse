"""Application message protocol layered over a raw reliable byte transport."""

from __future__ import annotations

from datetime import UTC, datetime
import re
import secrets
from uuid import uuid4

from PySide6.QtCore import QObject, QTimer, Signal

from .messaging import (
    FrameDecoder,
    SESSION_HANDSHAKE_VERSION,
    encode_ack,
    encode_event,
    encode_message,
    encode_session_control,
)


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
    error_received = Signal(str)
    queued_bytes_changed = Signal(int)

    def __init__(self, transport, parent=None, *, call_timeout_ms: int = 60_000,
                 validation_timeout_ms: int = 60_000,
                 validation_maximum_ms: int = 180_000) -> None:
        super().__init__(parent)
        self.transport = transport
        self._decoder = FrameDecoder()
        self._pending_session: tuple[str, str, int] | None = None
        self._probe_id = ""
        self._peer_probe_id = ""
        self._waiting_for_ready = False
        self._outgoing_call = False
        self._validation_queued_bytes: int | None = None
        self._published_state = "disconnected"
        self._call_timer = QTimer(self)
        self._call_timer.setSingleShot(True)
        self._call_timer.setInterval(call_timeout_ms)
        self._call_timer.timeout.connect(self._call_timed_out)
        self._validation_timer = QTimer(self)
        self._validation_timer.setSingleShot(True)
        self._validation_timer.setInterval(validation_timeout_ms)
        self._validation_timer.timeout.connect(self._validation_timed_out)
        self._validation_maximum_timer = QTimer(self)
        self._validation_maximum_timer.setSingleShot(True)
        self._validation_maximum_timer.setInterval(validation_maximum_ms)
        self._validation_maximum_timer.timeout.connect(
            self._validation_maximum_timed_out
        )
        transport.state_changed.connect(self._on_transport_state)
        transport.control_event.connect(self.control_event)
        transport.session_connected.connect(self._on_transport_session_connected)
        transport.session_disconnected.connect(self._on_transport_session_disconnected)
        transport.data_received.connect(self._read_data)
        transport.error_received.connect(self.error_received)
        if hasattr(transport, "queued_bytes_changed"):
            transport.queued_bytes_changed.connect(self._on_queued_bytes_changed)

    @staticmethod
    def normalize_callsign(value: str) -> str:
        call = value.strip().upper()
        if not CALLSIGN.fullmatch(call):
            raise ValueError("Callsign must be 1–15 letters, numbers, '/', or '-'")
        return call

    def start(self) -> None:
        self.transport.start()

    def stop(self) -> None:
        self._clear_session_attempt()
        self.transport.stop()

    def configure_and_listen(self, local_call: str) -> None:
        call = self.normalize_callsign(local_call)
        self.transport.send_control(f"MYCALL {call}")
        self.transport.send_control("LISTEN ON")
        self._set_state("listening")

    def connect_station(self, local_call: str, remote_call: str) -> None:
        local = self.normalize_callsign(local_call)
        remote = self.normalize_callsign(remote_call)
        # Establish the role before any transport callback can report CONNECTED.
        # CQ answers and direct calls share this exact caller-initiated path.
        self._outgoing_call = True
        self.transport.send_control(f"MYCALL {local}")
        self.transport.send_control("LISTEN ON")
        self.transport.send_control(f"CONNECT {local} {remote}")
        self._call_timer.start()
        self._set_state("linking")

    def disconnect_station(self) -> None:
        self._clear_session_attempt()
        self.transport.send_control("DISCONNECT")

    def send_message(self, message_id: str, timestamp: str, text: str) -> None:
        self.transport.write(encode_message(message_id, timestamp, text))
        self.message_sent.emit(message_id)

    def send_file_event(self, kind: str, event_id: str, timestamp: str,
                        **values: object) -> None:
        self.transport.write(encode_event(kind, event_id, timestamp, **values))

    def file_write_ready(self) -> bool:
        return self.transport.write_ready()

    def _read_data(self, data: bytes) -> None:
        for envelope in self._decoder.feed(data):
            if envelope.kind == "session_probe":
                self._acknowledge_session_probe(envelope)
            elif envelope.kind == "session_probe_ack":
                self._accept_session_probe_ack(envelope)
            elif envelope.kind == "session_ready":
                self._accept_session_ready(envelope)
            elif envelope.kind == "message":
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

    def _on_transport_state(self, state: str) -> None:
        # A local Mercury CONNECTED indication is provisional.  Application
        # features remain disabled until the peer returns a bounded MSP probe.
        if state != "connected":
            self._set_state(state)

    def _on_transport_session_connected(
        self, source: str, destination: str, bandwidth: int
    ) -> None:
        self._call_timer.stop()
        self._pending_session = (source, destination, bandwidth)
        self._validation_queued_bytes = None
        self._validation_maximum_timer.start()
        if not self._outgoing_call:
            self._set_state("validating-receiving")
            self.control_event.emit(
                "MSP validation: listening peer is waiting for the caller probe"
            )
            return
        self._set_state("validating-sending")
        self._validation_timer.start()
        self._probe_id = secrets.token_hex(8)
        try:
            self.transport.write(encode_session_control("session_probe", self._probe_id))
        except (OSError, RuntimeError) as error:
            self.error_received.emit(f"Could not validate the station link: {error}")
            self._abort_unconfirmed_session()
            return
        self.control_event.emit("MSP validation: caller probe queued")

    def _acknowledge_session_probe(self, envelope) -> None:
        self.control_event.emit("MSP validation: peer probe received")
        values = envelope.values or {}
        handshake_version = values.get("handshake_version", 1)
        supported_version = (
            isinstance(handshake_version, int)
            and not isinstance(handshake_version, bool)
            and handshake_version in {1, 2, SESSION_HANDSHAKE_VERSION}
        )
        if not supported_version:
            self.error_received.emit(
                "Peer uses an unsupported station-validation handshake"
            )
            self._abort_unconfirmed_session()
            return
        try:
            if handshake_version == SESSION_HANDSHAKE_VERSION:
                self.transport.write(encode_session_control(
                    "session_probe_ack", envelope.message_id
                ))
            else:
                self.transport.write(encode_event(
                    "session_probe_ack", str(uuid4()), datetime.now(UTC).isoformat(),
                    probe_id=envelope.message_id,
                    handshake_version=2,
                ))
        except (OSError, RuntimeError) as error:
            self.error_received.emit(f"Could not confirm the peer station link: {error}")
            self._abort_unconfirmed_session()
            return
        self.control_event.emit("MSP validation: probe acknowledgement queued")
        if self._pending_session and not self._outgoing_call:
            modern_handshake = handshake_version == SESSION_HANDSHAKE_VERSION
            if modern_handshake:
                self._peer_probe_id = envelope.message_id
                self._waiting_for_ready = True
                self._validation_queued_bytes = None
                self._validation_timer.start()
                self.control_event.emit(
                    "MSP validation: waiting for caller readiness confirmation"
                )
            else:
                # Earlier callers do not send session_ready. Preserve mixed-
                # version compatibility after successfully queuing their ACK.
                self.control_event.emit(
                    "MSP validation: legacy peer accepted after acknowledgement"
                )
                self._confirm_pending_session()

    def _accept_session_probe_ack(self, envelope) -> None:
        values = envelope.values or {}
        if (not self._pending_session or not self._probe_id
                or values.get("probe_id") != self._probe_id):
            return
        self.control_event.emit("MSP validation: probe acknowledgement received")
        self._validation_timer.start()
        try:
            self.transport.write(encode_session_control("session_ready", self._probe_id))
        except (OSError, RuntimeError) as error:
            self.error_received.emit(
                f"Could not complete station validation: {error}"
            )
            self._abort_unconfirmed_session()
            return
        self.control_event.emit("MSP validation: caller readiness queued")
        self._confirm_pending_session()

    def _accept_session_ready(self, envelope) -> None:
        values = envelope.values or {}
        if (not self._pending_session or self._outgoing_call
                or not self._waiting_for_ready
                or values.get("probe_id") != self._peer_probe_id
                or values.get("handshake_version") != SESSION_HANDSHAKE_VERSION):
            return
        self.control_event.emit("MSP validation: caller readiness received")
        self._validation_timer.start()
        self._confirm_pending_session()

    def _confirm_pending_session(self) -> None:
        if not self._pending_session:
            return
        session = self._pending_session
        self._validation_timer.stop()
        self._validation_maximum_timer.stop()
        self._pending_session = None
        self._probe_id = ""
        self._peer_probe_id = ""
        self._waiting_for_ready = False
        self._validation_queued_bytes = None
        self._outgoing_call = False
        self._set_state("connected")
        self.control_event.emit("MSP validation: completed")
        self.session_connected.emit(*session)

    def _on_queued_bytes_changed(self, queued: int) -> None:
        self.queued_bytes_changed.emit(queued)
        if not self._pending_session or not self._validation_timer.isActive():
            return
        previous = self._validation_queued_bytes
        self._validation_queued_bytes = queued
        if previous is None:
            self.control_event.emit(
                f"MSP validation: Mercury reports {queued} queued bytes"
            )
            return
        if queued < previous:
            self.control_event.emit(
                f"MSP validation: Mercury queue progressed to {queued} bytes"
            )
            self._validation_timer.start()

    def _call_timed_out(self) -> None:
        if not self._outgoing_call:
            return
        self.error_received.emit("Station did not answer within 60 seconds; call cancelled")
        self._abort_unconfirmed_session()

    def _validation_timed_out(self) -> None:
        if not self._pending_session:
            return
        if not self._outgoing_call and not self._waiting_for_ready:
            return
        if self._validation_queued_bytes:
            self.error_received.emit(
                "Station validation made no Mercury buffer progress; connection cancelled"
            )
        elif self._waiting_for_ready:
            self.error_received.emit(
                "Caller readiness confirmation did not arrive; connection cancelled"
            )
        else:
            self.error_received.emit(
                "Station link was not confirmed by the peer; connection cancelled"
            )
        self._abort_unconfirmed_session()

    def _validation_maximum_timed_out(self) -> None:
        if not self._pending_session:
            return
        if self._outgoing_call:
            message = "Station validation exceeded its safety deadline; connection cancelled"
        else:
            message = "Caller confirmation was not received within 180 seconds; connection cancelled"
        self.error_received.emit(message)
        self._abort_unconfirmed_session()

    def _abort_unconfirmed_session(self) -> None:
        self._clear_session_attempt()
        try:
            self.transport.send_control("DISCONNECT")
        except RuntimeError as error:
            self.error_received.emit(f"Could not cancel the station call: {error}")

    def _on_transport_session_disconnected(self) -> None:
        self._clear_session_attempt()
        # Mercury may report DISCONNECTED after an unanswered call without its
        # raw adapter ever leaving ready.  Publish the application transition
        # explicitly so automatic listening cannot remain stuck at linking.
        if self._published_state not in {"ready", "listening"}:
            self._set_state("ready")
        self.session_disconnected.emit()

    def _clear_session_attempt(self) -> None:
        self._call_timer.stop()
        self._validation_timer.stop()
        self._validation_maximum_timer.stop()
        self._pending_session = None
        self._probe_id = ""
        self._peer_probe_id = ""
        self._waiting_for_ready = False
        self._validation_queued_bytes = None
        self._outgoing_call = False

    def _set_state(self, state: str) -> None:
        if state != self._published_state:
            self._published_state = state
            self.state_changed.emit(state)

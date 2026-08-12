"""Station ping request/response and monotonic RTT measurement."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import math
import time
from uuid import uuid4

from PySide6.QtCore import QObject, QTimer, Signal

from application.modem import ModemStatus


@dataclass(frozen=True, slots=True)
class PingResult:
    rtt_ms: float
    local_snr_db: float
    remote_snr_db: float
    bitrate_bps: int
    modem_mode: str
    timestamp: str


class PingService(QObject):
    result_received = Signal(object)
    state_changed = Signal(str)
    error_received = Signal(str)

    def __init__(
        self,
        client,
        timeout_ms: int = 180_000,
        clock=time.monotonic,
        auto_timeout: bool = True,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.client = client
        self.timeout_ms = timeout_ms
        self.clock = clock
        self.auto_timeout = auto_timeout
        self.latest_status = ModemStatus()
        self._pending_id: str | None = None
        self._started = 0.0
        self._local_status = self.latest_status
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._timeout)
        client.ping_event_received.connect(self._on_event)
        if hasattr(client, "queued_bytes_changed"):
            client.queued_bytes_changed.connect(self._on_queue_activity)

    def update_status(self, status: ModemStatus) -> None:
        self.latest_status = status

    def ping(self) -> None:
        if self._pending_id:
            self.error_received.emit("A ping is already in progress")
            return
        ping_id = str(uuid4())
        self._pending_id = ping_id
        self._started = self.clock()
        self._local_status = self.latest_status
        try:
            self.client.send_file_event(
                "ping_request", ping_id, self._now()
            )
            if self._pending_id:
                if self.auto_timeout:
                    self._timer.start(self.timeout_ms)
                self.state_changed.emit("waiting")
        except RuntimeError as error:
            self._pending_id = None
            self.error_received.emit(str(error))

    def stop(self) -> None:
        self._timer.stop()
        self._pending_id = None

    def _on_event(self, envelope) -> None:
        if envelope.kind == "ping_request":
            self._respond(envelope.message_id)
        elif envelope.kind == "ping_response":
            self._accept_response(envelope)

    def _respond(self, ping_id: str) -> None:
        status = self.latest_status
        try:
            self.client.send_file_event(
                "ping_response",
                ping_id,
                self._now(),
                snr_db=round(status.snr_db, 2),
                bitrate_bps=status.bitrate_bps,
                modem_mode=status.modem_mode,
            )
        except RuntimeError as error:
            self.error_received.emit(str(error))

    def _accept_response(self, envelope) -> None:
        if envelope.message_id != self._pending_id:
            return
        values = envelope.values or {}
        try:
            remote_snr = float(values["snr_db"])
            bitrate = int(values["bitrate_bps"])
            mode = str(values["modem_mode"])
            if not math.isfinite(remote_snr) or not -100 <= remote_snr <= 100:
                raise ValueError("invalid remote SNR")
            if bitrate < 0 or bitrate > 10_000_000:
                raise ValueError("invalid remote bitrate")
            if not mode or len(mode) > 32:
                raise ValueError("invalid remote modem mode")
            rtt_ms = max(0.0, (self.clock() - self._started) * 1000)
            result = PingResult(
                rtt_ms,
                self._local_status.snr_db,
                remote_snr,
                bitrate,
                mode,
                self._now(),
            )
            self._timer.stop()
            self._pending_id = None
            self.result_received.emit(result)
            self.state_changed.emit("complete")
        except (KeyError, TypeError, ValueError) as error:
            self.error_received.emit(f"Invalid ping response: {error}")

    def _timeout(self) -> None:
        self._pending_id = None
        self.state_changed.emit("timeout")
        self.error_received.emit("Ping timed out")

    def _on_queue_activity(self, queued_bytes: int) -> None:
        if self._pending_id and self.auto_timeout and queued_bytes >= 0:
            self._timer.start(self.timeout_ms)

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

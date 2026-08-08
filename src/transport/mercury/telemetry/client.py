"""Read-only Mercury UI WebSocket client."""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QAbstractSocket
from PySide6.QtWebSockets import QWebSocket, QWebSocketProtocol

from .protocol import parse_spectrum_frame, parse_status_message


class MercuryTelemetryClient(QObject):
    status_received = Signal(object)
    spectrum_received = Signal(object)
    state_changed = Signal(str)
    error_received = Signal(str)

    def __init__(self, url: str = "ws://127.0.0.1:10000/websocket", parent=None) -> None:
        super().__init__(parent)
        self.url = QUrl(url)
        self.socket = QWebSocket(
            "MercurySkyPulse", QWebSocketProtocol.VersionLatest, self
        )
        self.socket.connected.connect(self._on_connected)
        self.socket.disconnected.connect(self._on_disconnected)
        self.socket.textMessageReceived.connect(self._on_text)
        self.socket.binaryMessageReceived.connect(self._on_binary)
        self.socket.errorOccurred.connect(self._on_error)

        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_timer.timeout.connect(self._open)
        self._intended_running = False
        self._attempt = 0
        self._state = "disconnected"

    @property
    def state(self) -> str:
        return self._state

    def start(self) -> None:
        self._intended_running = True
        self._attempt = 0
        self._open()

    def stop(self) -> None:
        self._intended_running = False
        self._reconnect_timer.stop()
        self.socket.close()
        self._set_state("disconnected")

    def reconnect_now(self) -> None:
        if not self._intended_running:
            return
        self._attempt = 0
        self._reconnect_timer.stop()
        self.socket.abort()
        self._open()

    def _open(self) -> None:
        if not self._intended_running:
            return
        if self.socket.state() != QAbstractSocket.SocketState.UnconnectedState:
            return
        self._set_state("connecting")
        self.socket.open(self.url)

    def _on_connected(self) -> None:
        self._attempt = 0
        self._set_state("connected")

    def _on_disconnected(self) -> None:
        self._set_state("disconnected")
        if not self._intended_running:
            return
        delay = min(8000, 500 * (2 ** min(self._attempt, 4)))
        self._attempt += 1
        self._reconnect_timer.start(delay)

    def _on_text(self, payload: str) -> None:
        status = parse_status_message(payload)
        if status is not None:
            self.status_received.emit(status)

    def _on_binary(self, payload: bytes) -> None:
        spectrum = parse_spectrum_frame(bytes(payload))
        if spectrum is not None:
            self.spectrum_received.emit(spectrum)

    def _on_error(self, error: QAbstractSocket.SocketError) -> None:
        if error != QAbstractSocket.SocketError.ConnectionRefusedError:
            self.error_received.emit(self.socket.errorString())

    def _set_state(self, state: str) -> None:
        if state == self._state:
            return
        self._state = state
        self.state_changed.emit(state)

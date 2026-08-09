"""Raw Mercury TNC control and reliable-byte transport adapter."""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtNetwork import QAbstractSocket, QTcpSocket


class MercuryTncTransport(QObject):
    state_changed = Signal(str)
    control_event = Signal(str)
    session_connected = Signal(str, str, int)
    session_disconnected = Signal()
    data_received = Signal(bytes)
    error_received = Signal(str)

    def __init__(
        self,
        host: str = "127.0.0.1",
        control_port: int = 8300,
        data_host: str | None = None,
        data_port: int = 8301,
        reconnect_delay_ms: int = 1000,
        maximum_control_line_bytes: int = 4096,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.host, self.control_port = host, control_port
        self.data_host, self.data_port = data_host or host, data_port
        self.reconnect_delay_ms = reconnect_delay_ms
        self.maximum_control_line_bytes = maximum_control_line_bytes
        self.malformed_input_count = 0
        self.control, self.data = QTcpSocket(self), QTcpSocket(self)
        self.control.readyRead.connect(self._read_control)
        self.data.readyRead.connect(lambda: self.data_received.emit(bytes(self.data.readAll())))
        self.control.connected.connect(self._update_ready)
        self.data.connected.connect(self._update_ready)
        self.control.disconnected.connect(self._schedule_reconnect)
        self.data.disconnected.connect(self._schedule_reconnect)
        self.control.errorOccurred.connect(self._socket_error)
        self.data.errorOccurred.connect(self._socket_error)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._connect_sockets)
        self._intended = False
        self._control_buffer = bytearray()
        self._state = "disconnected"

    @property
    def state(self) -> str:
        return self._state

    def start(self) -> None:
        self._intended = True
        self._connect_sockets()

    def stop(self) -> None:
        self._intended = False
        self._timer.stop()
        self.control.close()
        self.data.close()
        self._set_state("disconnected")

    def send_control(self, command: str) -> None:
        if self.control.state() != QAbstractSocket.SocketState.ConnectedState:
            raise RuntimeError("Mercury control socket is not connected")
        self.control.write(command.encode("ascii") + b"\r")

    def write(self, payload: bytes) -> None:
        if self._state != "connected":
            raise RuntimeError("station link is not connected")
        if self.data.write(payload) != len(payload):
            raise RuntimeError("Mercury data socket rejected application bytes")

    def write_ready(self) -> bool:
        return self.data.bytesToWrite() < 32 * 1024

    def _connect_sockets(self) -> None:
        if not self._intended:
            return
        self._set_state("connecting-tnc")
        if self.control.state() == QAbstractSocket.SocketState.UnconnectedState:
            self.control.connectToHost(self.host, self.control_port)
        if self.data.state() == QAbstractSocket.SocketState.UnconnectedState:
            self.data.connectToHost(self.data_host, self.data_port)

    def _update_ready(self) -> None:
        if (self.control.state() == QAbstractSocket.SocketState.ConnectedState
                and self.data.state() == QAbstractSocket.SocketState.ConnectedState):
            self._set_state("ready")

    def _schedule_reconnect(self) -> None:
        if self._intended:
            self._set_state("disconnected")
            self._timer.start(self.reconnect_delay_ms)

    def _socket_error(self, error: QAbstractSocket.SocketError) -> None:
        if error != QAbstractSocket.SocketError.ConnectionRefusedError:
            self.error_received.emit(self.sender().errorString())

    def _read_control(self) -> None:
        self._read_control_bytes(bytes(self.control.readAll()))

    def _read_control_bytes(self, data: bytes) -> None:
        self._control_buffer.extend(data)
        while b"\r" in self._control_buffer:
            raw, _, remainder = self._control_buffer.partition(b"\r")
            self._control_buffer = bytearray(remainder)
            if len(raw) > self.maximum_control_line_bytes:
                self._reject_control_input("Mercury control line exceeded configured limit")
                continue
            line = raw.decode("ascii", errors="replace").strip()
            if line:
                self._handle_control_line(line)
        if len(self._control_buffer) > self.maximum_control_line_bytes:
            self._control_buffer.clear()
            self._reject_control_input("Mercury control buffer exceeded configured limit")

    def _reject_control_input(self, message: str) -> None:
        self.malformed_input_count += 1
        self.error_received.emit(message)

    def _handle_control_line(self, line: str) -> None:
        self.control_event.emit(line)
        if line.startswith("CONNECTED "):
            parts = line.split()
            if len(parts) >= 4:
                try:
                    bandwidth = int(parts[3])
                except ValueError:
                    bandwidth = 0
                self._set_state("connected")
                self.session_connected.emit(parts[1], parts[2], bandwidth)
        elif line == "DISCONNECTED":
            self._set_state("ready")
            self.session_disconnected.emit()

    def _set_state(self, state: str) -> None:
        if state != self._state:
            self._state = state
            self.state_changed.emit(state)

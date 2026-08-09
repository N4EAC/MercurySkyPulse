"""Raw KISS broadcast-byte transport adapter for Mercury."""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtNetwork import QAbstractSocket, QTcpSocket


FEND, FESC, TFEND, TFESC = 0xC0, 0xDB, 0xDC, 0xDD


def kiss_frame(payload: bytes) -> bytes:
    escaped = bytes((0,)) + payload
    escaped = escaped.replace(bytes((FESC,)), bytes((FESC, TFESC)))
    escaped = escaped.replace(bytes((FEND,)), bytes((FESC, TFEND)))
    return bytes((FEND,)) + escaped + bytes((FEND,))


class KissDecoder:
    def __init__(self, maximum_frame_bytes: int = 4096,
                 maximum_buffer_bytes: int = 8192) -> None:
        if maximum_frame_bytes < 1 or maximum_buffer_bytes < maximum_frame_bytes + 2:
            raise ValueError("KISS buffer must hold at least one bounded frame")
        self.maximum_frame_bytes = maximum_frame_bytes
        self.maximum_buffer_bytes = maximum_buffer_bytes
        self.buffer = bytearray()
        self.malformed_frame_count = 0

    def feed(self, data: bytes) -> list[bytes]:
        self.buffer.extend(data)
        if len(self.buffer) > self.maximum_buffer_bytes:
            self.buffer.clear()
            self.malformed_frame_count += 1
            return []
        payloads = []
        while FEND in self.buffer:
            first = self.buffer.find(FEND)
            if first:
                del self.buffer[:first]
                first = 0
            second = self.buffer.find(FEND, first + 1)
            if second < 0:
                if len(self.buffer) - 1 > self.maximum_frame_bytes:
                    self.buffer.clear()
                    self.malformed_frame_count += 1
                break
            frame = bytes(self.buffer[first + 1:second])
            del self.buffer[:second + 1]
            if not frame:
                continue
            if len(frame) > self.maximum_frame_bytes:
                self.malformed_frame_count += 1
                continue
            frame = frame.replace(bytes((FESC, TFEND)), bytes((FEND,)))
            frame = frame.replace(bytes((FESC, TFESC)), bytes((FESC,)))
            if frame[0] & 0x0F == 0:
                payloads.append(frame[1:])
        return payloads


class MercuryBroadcastTransport(QObject):
    payload_received = Signal(bytes)
    state_changed = Signal(str)
    error_received = Signal(str)

    def __init__(self, host="127.0.0.1", port=8100,
                 reconnect_delay_ms=1000, maximum_frame_bytes=4096,
                 maximum_buffer_bytes=8192, parent=None) -> None:
        super().__init__(parent)
        self.socket = QTcpSocket(self)
        self.host, self.port = host, port
        self.decoder = KissDecoder(maximum_frame_bytes, maximum_buffer_bytes)
        self.reconnect_delay_ms = reconnect_delay_ms
        self.socket.readyRead.connect(self._read)
        self.socket.connected.connect(lambda: self.state_changed.emit("ready"))
        self.socket.disconnected.connect(self._reconnect)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.start)
        self.intended = False

    def start(self) -> None:
        self.intended = True
        if self.socket.state() == QAbstractSocket.SocketState.UnconnectedState:
            self.socket.connectToHost(self.host, self.port)

    def stop(self) -> None:
        self.intended = False
        self.timer.stop()
        self.socket.close()

    def send_payload(self, payload: bytes) -> None:
        if self.socket.state() != QAbstractSocket.SocketState.ConnectedState:
            raise RuntimeError("Mercury broadcast socket is not connected")
        frame = kiss_frame(payload)
        if self.socket.write(frame) != len(frame):
            raise RuntimeError("Mercury broadcast socket rejected application bytes")

    def _reconnect(self) -> None:
        self.state_changed.emit("disconnected")
        if self.intended:
            self.timer.start(self.reconnect_delay_ms)

    def _read(self) -> None:
        rejected_before = self.decoder.malformed_frame_count
        for payload in self.decoder.feed(bytes(self.socket.readAll())):
            self.payload_received.emit(payload)
        if self.decoder.malformed_frame_count > rejected_before:
            self.error_received.emit("Malformed or oversized KISS input discarded")

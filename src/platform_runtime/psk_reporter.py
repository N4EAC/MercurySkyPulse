"""Cross-platform PSK Reporter IPFIX encoder and UDP uploader."""

from __future__ import annotations

import secrets
import struct
import time

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QAbstractSocket, QHostAddress, QHostInfo, QUdpSocket

from application.psk_reporter import PskReception


PSK_REPORTER_HOST = "report.pskreporter.info"
PSK_REPORTER_PORT = 4739
RECEIVER_TEMPLATE_ID = 0x9992
SENDER_TEMPLATE_ID = 0x9993
ENTERPRISE = 30351

RECEIVER_TEMPLATE = bytes.fromhex(
    "0003002c 999200040001 "
    "8002ffff0000768f 8004ffff0000768f 8008ffff0000768f "
    "8009ffff0000768f 0000"
)
SENDER_TEMPLATE = bytes.fromhex(
    "00020034 99930006 "
    "8001ffff0000768f 800500040000768f 800affff0000768f "
    "800b00010000768f 8003ffff0000768f 00960004"
)


def _variable(value: str, maximum: int = 254) -> bytes:
    encoded = value.encode("utf-8")
    if not encoded or len(encoded) > maximum:
        raise ValueError("PSK Reporter text field is invalid")
    return bytes((len(encoded),)) + encoded


def _set(set_id: int, payload: bytes) -> bytes:
    length = 4 + len(payload)
    padding = (-length) % 4
    return struct.pack(">HH", set_id, length + padding) + payload + b"\0" * padding


def encode_ipfix(
    receiver_callsign: str,
    receiver_locator: str,
    software: str,
    antenna: str,
    reports: tuple[PskReception, ...],
    sequence: int,
    observation_id: int,
    include_templates: bool,
    exported_at: int | None = None,
) -> bytes:
    """Encode the PSK Reporter cookie-cutter IPFIX profile."""
    if not reports:
        raise ValueError("At least one PSK Reporter reception is required")
    receiver = _set(
        RECEIVER_TEMPLATE_ID,
        _variable(receiver_callsign) + _variable(receiver_locator)
        + _variable(software) + _variable(antenna or "Unspecified"),
    )
    sender_payload = bytearray()
    for report in reports:
        if not 1 <= report.frequency_hz <= 0xFFFFFFFF:
            raise ValueError("PSK Reporter frequency must fit the 4-byte profile")
        sender_payload.extend(_variable(report.sender_callsign))
        sender_payload.extend(struct.pack(">I", report.frequency_hz))
        sender_payload.extend(_variable(report.mode))
        sender_payload.append(1)  # automatically extracted
        sender_payload.extend(_variable(report.sender_locator))
        sender_payload.extend(struct.pack(">I", report.received_at))
    body = (RECEIVER_TEMPLATE + SENDER_TEMPLATE if include_templates else b"")
    body += receiver + _set(SENDER_TEMPLATE_ID, bytes(sender_payload))
    packet = struct.pack(
        ">HHIII", 10, 16 + len(body), int(exported_at or time.time()),
        sequence & 0xFFFFFFFF, observation_id & 0xFFFFFFFF,
    ) + body
    if len(packet) > 1400:
        raise ValueError("PSK Reporter datagram exceeds the safe UDP size")
    return packet


class PskReporterUploader(QObject):
    sent = Signal(int)
    error_received = Signal(str)
    activity_logged = Signal(str)

    def __init__(self, host: str = PSK_REPORTER_HOST,
                 port: int = PSK_REPORTER_PORT, parent=None) -> None:
        super().__init__(parent)
        self.host, self.port = host, int(port)
        self.socket = QUdpSocket(self)
        self.socket.bind(
            QHostAddress.SpecialAddress.AnyIPv4,
            0,
            QAbstractSocket.BindFlag.ShareAddress,
        )
        self.observation_id = secrets.randbits(32)
        self.sequence = 0
        self._pending: tuple[bytes, int] | None = None

    def upload(self, receiver_call: str, receiver_grid: str, software: str,
               antenna: str,
               reports: tuple[PskReception, ...], include_templates: bool) -> None:
        try:
            payload = encode_ipfix(
                receiver_call, receiver_grid, software, antenna, reports, self.sequence,
                self.observation_id, include_templates,
            )
        except ValueError as error:
            self.error_received.emit(str(error))
            return
        self.activity_logged.emit(
            f"IPFIX sequence={self.sequence} observation_id={self.observation_id} "
            f"templates={include_templates} reports={len(reports)} bytes={len(payload)}"
        )
        self._pending = (payload, len(reports))
        QHostInfo.lookupHost(self.host, self._resolved)

    def _resolved(self, info: QHostInfo) -> None:
        pending = self._pending
        self._pending = None
        if pending is None:
            return
        addresses = info.addresses()
        if info.error() != QHostInfo.HostInfoError.NoError or not addresses:
            self.error_received.emit(f"PSK Reporter host lookup failed: {info.errorString()}")
            return
        payload, count = pending
        written = self.socket.writeDatagram(payload, addresses[0], self.port)
        if written != len(payload):
            self.error_received.emit("PSK Reporter UDP upload was not accepted")
            return
        self.activity_logged.emit(
            f"DATAGRAM address={addresses[0].toString()} port={self.port} bytes={written}"
        )
        self.sequence = (self.sequence + count) & 0xFFFFFFFF
        self.sent.emit(count)

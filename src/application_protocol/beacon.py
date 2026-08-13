"""Capability-beacon application protocol over an opaque broadcast transport."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import re
import struct

from PySide6.QtCore import QObject, Signal


HEADER = struct.Struct(">4sBBiiII")
MAGIC = b"MSPB"
CQ_HEADER = struct.Struct(">4sBI")
CQ_MAGIC = b"MSPQ"
CAPABILITIES = {
    "beacon": 1 << 0, "bbs": 1 << 1, "chat": 1 << 2,
    "file-transfer": 1 << 3, "gps-history": 1 << 4,
    "image": 1 << 5, "location": 1 << 6,
}
CALLSIGN = re.compile(r"^[A-Z0-9][A-Z0-9/-]{0,14}$")
GRID = re.compile(r"^[A-R]{2}\d{2}(?:[A-X]{2}(?:\d{2})?)?$")


@dataclass(frozen=True, slots=True)
class BeaconFrame:
    callsign: str
    grid: str
    software_version: str
    capabilities: tuple[str, ...]
    timestamp: str
    latitude: float | None = None
    longitude: float | None = None
    gps_timestamp: str | None = None


@dataclass(frozen=True, slots=True)
class CqFrame:
    callsign: str
    grid: str
    software_version: str
    timestamp: str


def normalize_callsign(value: str) -> str:
    callsign = value.strip().upper()
    if not CALLSIGN.fullmatch(callsign):
        raise ValueError("Callsign must be 1–15 letters, numbers, '/', or '-'")
    return callsign


def encode_beacon(beacon) -> bytes:
    callsign = normalize_callsign(beacon.callsign).encode("ascii")
    grid = str(beacon.grid).upper().encode("ascii")
    version = str(beacon.software_version).encode("ascii")
    if not GRID.fullmatch(grid.decode()) or len(grid) > 8 or not version or len(version) > 32:
        raise ValueError("Invalid beacon grid or software version")
    capability_bits = 0
    for capability in beacon.capabilities:
        if capability not in CAPABILITIES:
            raise ValueError("Unsupported beacon capability")
        capability_bits |= CAPABILITIES[capability]
    has_gps = beacon.latitude is not None and beacon.longitude is not None
    latitude = round(beacon.latitude * 1_000_000) if has_gps else 0
    longitude = round(beacon.longitude * 1_000_000) if has_gps else 0
    if has_gps and not (-90 <= beacon.latitude <= 90 and -180 <= beacon.longitude <= 180):
        raise ValueError("Beacon coordinates are out of range")
    gps_time = int(datetime.fromisoformat(beacon.gps_timestamp).timestamp()) if has_gps and beacon.gps_timestamp else 0
    if has_gps and not gps_time:
        raise ValueError("Missing GPS timestamp")
    beacon_time = int(datetime.fromisoformat(beacon.timestamp).timestamp())
    return (HEADER.pack(MAGIC, 1, 1 if has_gps else 0, latitude, longitude,
                        beacon_time, gps_time)
            + struct.pack(">I", capability_bits)
            + bytes((len(callsign), len(grid), len(version)))
            + callsign + grid + version)


def decode_beacon(data: bytes) -> BeaconFrame:
    minimum = HEADER.size + 7
    if len(data) < minimum:
        raise ValueError("Beacon is truncated")
    magic, version_id, flags, lat_raw, lon_raw, timestamp, gps_timestamp = HEADER.unpack_from(data)
    if magic != MAGIC or version_id != 1 or flags & ~1:
        raise ValueError("Unsupported beacon")
    capability_bits = struct.unpack_from(">I", data, HEADER.size)[0]
    if capability_bits & ~sum(CAPABILITIES.values()):
        raise ValueError("Unknown beacon capabilities")
    lengths_at = HEADER.size + 4
    call_len, grid_len, version_len = data[lengths_at:lengths_at + 3]
    if len(data) != minimum + call_len + grid_len + version_len:
        raise ValueError("Invalid beacon length")
    cursor = minimum
    callsign = normalize_callsign(data[cursor:cursor + call_len].decode("ascii")); cursor += call_len
    grid = data[cursor:cursor + grid_len].decode("ascii"); cursor += grid_len
    software = data[cursor:cursor + version_len].decode("ascii")
    if not GRID.fullmatch(grid) or not software:
        raise ValueError("Invalid beacon grid or software version")
    capabilities = tuple(name for name, bit in CAPABILITIES.items() if capability_bits & bit)
    latitude = longitude = gps_iso = None
    if flags & 1:
        latitude, longitude = lat_raw / 1_000_000, lon_raw / 1_000_000
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180) or not gps_timestamp:
            raise ValueError("Invalid beacon GPS data")
        gps_iso = datetime.fromtimestamp(gps_timestamp, UTC).isoformat()
    return BeaconFrame(callsign, grid, software, capabilities,
                       datetime.fromtimestamp(timestamp, UTC).isoformat(),
                       latitude, longitude, gps_iso)


def encode_cq(cq) -> bytes:
    callsign = normalize_callsign(cq.callsign).encode("ascii")
    grid = str(cq.grid).upper().encode("ascii")
    version = str(cq.software_version).encode("ascii")
    if not GRID.fullmatch(grid.decode()) or len(grid) > 8 or not version or len(version) > 32:
        raise ValueError("Invalid CQ grid or software version")
    timestamp = int(datetime.fromisoformat(cq.timestamp).timestamp())
    return (
        CQ_HEADER.pack(CQ_MAGIC, 1, timestamp)
        + bytes((len(callsign), len(grid), len(version)))
        + callsign + grid + version
    )


def decode_cq(data: bytes) -> CqFrame:
    minimum = CQ_HEADER.size + 3
    if len(data) < minimum:
        raise ValueError("CQ is truncated")
    magic, version_id, timestamp = CQ_HEADER.unpack_from(data)
    if magic != CQ_MAGIC or version_id != 1:
        raise ValueError("Unsupported CQ")
    call_len, grid_len, version_len = data[CQ_HEADER.size:minimum]
    if len(data) != minimum + call_len + grid_len + version_len:
        raise ValueError("Invalid CQ length")
    cursor = minimum
    callsign = normalize_callsign(data[cursor:cursor + call_len].decode("ascii"))
    cursor += call_len
    grid = data[cursor:cursor + grid_len].decode("ascii")
    cursor += grid_len
    software = data[cursor:cursor + version_len].decode("ascii")
    if not GRID.fullmatch(grid) or not software:
        raise ValueError("Invalid CQ grid or software version")
    return CqFrame(
        callsign, grid, software, datetime.fromtimestamp(timestamp, UTC).isoformat()
    )


class BeaconProtocolClient(QObject):
    beacon_received = Signal(object)
    cq_received = Signal(object)
    state_changed = Signal(str)
    error_received = Signal(str)

    def __init__(self, transport, parent=None) -> None:
        super().__init__(parent)
        self.transport = transport
        transport.payload_received.connect(self._receive)
        transport.state_changed.connect(self.state_changed)
        transport.error_received.connect(self.error_received)

    def start(self) -> None:
        self.transport.start()

    def stop(self) -> None:
        self.transport.stop()

    def send_beacon(self, beacon) -> None:
        self.transport.send_payload(encode_beacon(beacon))

    def send_cq(self, cq) -> None:
        self.transport.send_payload(encode_cq(cq))

    def _receive(self, payload: bytes) -> None:
        try:
            if payload.startswith(MAGIC):
                self.beacon_received.emit(decode_beacon(payload))
            elif payload.startswith(CQ_MAGIC):
                self.cq_received.emit(decode_cq(payload))
            else:
                raise ValueError("Unsupported MSP broadcast payload")
        except (UnicodeDecodeError, ValueError) as error:
            self.error_received.emit(f"Invalid broadcast message: {error}")

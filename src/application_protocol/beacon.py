"""Capability-beacon application protocol over an opaque broadcast transport."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import re
import struct

from PySide6.QtCore import QObject, Signal


LEGACY_HEADER = struct.Struct(">4sBBiiII")
COMPACT_HEADER = struct.Struct(">4sBBI")
MAGIC = b"MSPB"
LEGACY_CQ_HEADER = struct.Struct(">4sBI")
COMPACT_CQ_HEADER = struct.Struct(">4sBI")
CQ_MAGIC = b"MSPQ"
DATAC15_HEADER = struct.Struct(">4sBBBI")
COMPACT_VERSION = 3
PREVIOUS_COMPACT_VERSION = 2
COMPACT_SOFTWARE_BYTES = 11
DATAC16_STATION_PAYLOAD_BYTES = 13
DATAC16_CALLSIGN_BYTES = 8
DATAC16_MAX_CALLSIGN_CHARS = 10
DATAC16_BEACON_MARKER = 0x80
DATAC16_CQ_MARKER = 0x40
CALLSIGN_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/-"
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


def _pack_u24(value: int) -> bytes:
    if not 0 <= value <= 0xFFFFFF:
        raise ValueError("Compact coordinate is out of range")
    return value.to_bytes(3, "big")


def _unpack_u24(data: bytes) -> int:
    if len(data) != 3:
        raise ValueError("Compact coordinate is truncated")
    return int.from_bytes(data, "big")


def _encode_coordinate(value: float, minimum: float, maximum: float) -> bytes:
    code = round((value - minimum) * 0xFFFFFF / (maximum - minimum))
    return _pack_u24(code)


def _decode_coordinate(data: bytes, minimum: float, maximum: float) -> float:
    return minimum + _unpack_u24(data) * (maximum - minimum) / 0xFFFFFF


def _encode_grid(grid: str) -> int:
    """Pack a valid 4/6/8-character Maidenhead locator into 31 bits."""
    value = (((ord(grid[0]) - 65) * 18 + ord(grid[1]) - 65) * 10
             + int(grid[2])) * 10 + int(grid[3])
    if len(grid) == 4:
        return value
    value = (value * 24 + ord(grid[4]) - 65) * 24 + ord(grid[5]) - 65
    if len(grid) == 6:
        return 32_400 + value
    return 32_400 + 18_662_400 + (value * 10 + int(grid[6])) * 10 + int(grid[7])


def _decode_grid(code: int) -> str:
    maximum = 32_400 + 18_662_400 + 1_866_240_000
    if not 0 <= code < maximum:
        raise ValueError("Invalid compact beacon grid")
    if code < 32_400:
        length, value = 4, code
    elif code < 32_400 + 18_662_400:
        length, value = 6, code - 32_400
    else:
        length, value = 8, code - 32_400 - 18_662_400
    suffix = ""
    if length == 8:
        value, d8 = divmod(value, 10)
        value, d7 = divmod(value, 10)
        suffix = f"{d7}{d8}"
    if length >= 6:
        value, l6 = divmod(value, 24)
        value, l5 = divmod(value, 24)
        suffix = f"{chr(65 + l5)}{chr(65 + l6)}{suffix}"
    value, d4 = divmod(value, 10)
    value, d3 = divmod(value, 10)
    value, l2 = divmod(value, 18)
    grid = f"{chr(65 + value)}{chr(65 + l2)}{d3}{d4}{suffix}"
    if not GRID.fullmatch(grid):
        raise ValueError("Invalid compact beacon grid")
    return grid


def _encode_compact_callsign(callsign: bytes) -> bytes:
    text = callsign.decode("ascii")
    if len(text) > DATAC16_MAX_CALLSIGN_CHARS:
        raise ValueError("DATAC16 beacon callsign must be at most 10 characters")
    value = 1
    for character in text:
        value = value * len(CALLSIGN_ALPHABET) + CALLSIGN_ALPHABET.index(character)
    # The low marker bit keeps the fixed-size binary field from ending in NUL;
    # Mercury pads shorter station messages with NUL and the KISS adapter strips
    # that padding on receive.
    return ((value << 1) | 1).to_bytes(DATAC16_CALLSIGN_BYTES, "big")


def _decode_compact_callsign(encoded: bytes) -> str:
    if len(encoded) != DATAC16_CALLSIGN_BYTES:
        raise ValueError("Compact callsign is truncated")
    packed = int.from_bytes(encoded, "big")
    if not packed & 1:
        raise ValueError("Invalid compact callsign")
    value = packed >> 1
    characters = []
    while value > 1:
        value, index = divmod(value, len(CALLSIGN_ALPHABET))
        characters.append(CALLSIGN_ALPHABET[index])
    if value != 1 or not characters:
        raise ValueError("Invalid compact callsign")
    callsign = "".join(reversed(characters))
    if len(callsign) > DATAC16_MAX_CALLSIGN_CHARS:
        raise ValueError("Invalid compact callsign")
    return normalize_callsign(callsign)


def encode_beacon(beacon) -> bytes:
    callsign = normalize_callsign(beacon.callsign).encode("ascii")
    grid = str(beacon.grid).upper()
    if not GRID.fullmatch(grid) or not str(beacon.software_version):
        raise ValueError("Invalid beacon grid or software version")
    capability_bits = 0
    for capability in beacon.capabilities:
        if capability not in CAPABILITIES:
            raise ValueError("Unsupported beacon capability")
        capability_bits |= CAPABILITIES[capability]
    has_gps = beacon.latitude is not None and beacon.longitude is not None
    if has_gps and not (-90 <= beacon.latitude <= 90 and -180 <= beacon.longitude <= 180):
        raise ValueError("Beacon coordinates are out of range")
    if has_gps and not beacon.gps_timestamp:
        raise ValueError("Missing GPS timestamp")
    datetime.fromisoformat(beacon.timestamp)
    encoded = (
        bytes((DATAC16_BEACON_MARKER | capability_bits,))
        + _encode_grid(grid).to_bytes(4, "big")
        + _encode_compact_callsign(callsign)
    )
    if len(encoded) != DATAC16_STATION_PAYLOAD_BYTES:
        raise ValueError("Beacon exceeds compact DATAC16 payload")
    return encoded


def decode_beacon(data: bytes) -> BeaconFrame:
    if len(data) == DATAC16_STATION_PAYLOAD_BYTES and data[0] & DATAC16_BEACON_MARKER:
        return _decode_datac16_beacon(data)
    if len(data) >= 5 and data[:4] == MAGIC and data[4] == COMPACT_VERSION:
        return _decode_datac15_beacon(data)
    if len(data) >= 5 and data[:4] == MAGIC and data[4] == PREVIOUS_COMPACT_VERSION:
        return _decode_compact_beacon(data)
    minimum = LEGACY_HEADER.size + 7
    if len(data) < minimum:
        raise ValueError("Beacon is truncated")
    magic, version_id, flags, lat_raw, lon_raw, timestamp, gps_timestamp = LEGACY_HEADER.unpack_from(data)
    if magic != MAGIC or version_id != 1 or flags & ~1:
        raise ValueError("Unsupported beacon")
    capability_bits = struct.unpack_from(">I", data, LEGACY_HEADER.size)[0]
    if capability_bits & ~sum(CAPABILITIES.values()):
        raise ValueError("Unknown beacon capabilities")
    lengths_at = LEGACY_HEADER.size + 4
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


def _decode_compact_beacon(data: bytes) -> BeaconFrame:
    minimum = COMPACT_HEADER.size + 6 + 3
    if len(data) < minimum:
        raise ValueError("Beacon is truncated")
    magic, version_id, flags, timestamp = COMPACT_HEADER.unpack_from(data)
    if magic != MAGIC or version_id != PREVIOUS_COMPACT_VERSION:
        raise ValueError("Unsupported beacon")
    capability_bits = flags & 0x7F
    if capability_bits & ~sum(CAPABILITIES.values()):
        raise ValueError("Unknown beacon capabilities")
    lengths_at = COMPACT_HEADER.size + 6
    call_len, grid_len, version_len = data[lengths_at:minimum]
    if len(data) != minimum + call_len + grid_len + version_len:
        raise ValueError("Invalid beacon length")
    cursor = minimum
    callsign = normalize_callsign(data[cursor:cursor + call_len].decode("ascii"))
    cursor += call_len
    grid = data[cursor:cursor + grid_len].decode("ascii"); cursor += grid_len
    software = data[cursor:cursor + version_len].decode("ascii")
    if not GRID.fullmatch(grid) or not software:
        raise ValueError("Invalid beacon grid or software version")
    latitude = longitude = gps_iso = None
    if flags & 0x80:
        latitude = _decode_coordinate(data[COMPACT_HEADER.size:COMPACT_HEADER.size + 3], -90.0, 90.0)
        longitude = _decode_coordinate(data[COMPACT_HEADER.size + 3:COMPACT_HEADER.size + 6], -180.0, 180.0)
        gps_iso = datetime.fromtimestamp(timestamp, UTC).isoformat()
    capabilities = tuple(name for name, bit in CAPABILITIES.items() if capability_bits & bit)
    return BeaconFrame(
        callsign, grid, software, capabilities,
        datetime.fromtimestamp(timestamp, UTC).isoformat(),
        latitude, longitude, gps_iso,
    )


def _decode_datac15_beacon(data: bytes) -> BeaconFrame:
    if len(data) < DATAC15_HEADER.size:
        raise ValueError("Beacon is truncated")
    magic, version_id, capability_bits, call_len, grid_code = DATAC15_HEADER.unpack_from(data)
    if magic != MAGIC or version_id != COMPACT_VERSION:
        raise ValueError("Unsupported beacon")
    if capability_bits & ~sum(CAPABILITIES.values()):
        raise ValueError("Unknown beacon capabilities")
    if len(data) != DATAC15_HEADER.size + call_len:
        raise ValueError("Invalid beacon length")
    callsign = normalize_callsign(data[DATAC15_HEADER.size:].decode("ascii"))
    capabilities = tuple(name for name, bit in CAPABILITIES.items() if capability_bits & bit)
    return BeaconFrame(
        callsign, _decode_grid(grid_code), "compact", capabilities,
        datetime.now(UTC).isoformat(),
    )


def _decode_datac16_beacon(data: bytes) -> BeaconFrame:
    if len(data) != DATAC16_STATION_PAYLOAD_BYTES:
        raise ValueError("Beacon is truncated")
    capability_bits = data[0] & 0x7F
    if capability_bits & ~sum(CAPABILITIES.values()):
        raise ValueError("Unknown beacon capabilities")
    grid = _decode_grid(int.from_bytes(data[1:5], "big"))
    callsign = _decode_compact_callsign(data[5:])
    capabilities = tuple(name for name, bit in CAPABILITIES.items() if capability_bits & bit)
    return BeaconFrame(
        callsign, grid, "compact", capabilities, datetime.now(UTC).isoformat()
    )


def encode_cq(cq) -> bytes:
    callsign = normalize_callsign(cq.callsign).encode("ascii")
    grid = str(cq.grid).upper()
    if not GRID.fullmatch(grid) or not str(cq.software_version):
        raise ValueError("Invalid CQ grid or software version")
    datetime.fromisoformat(cq.timestamp)
    encoded = (
        bytes((DATAC16_CQ_MARKER,))
        + _encode_grid(grid).to_bytes(4, "big")
        + _encode_compact_callsign(callsign)
    )
    if len(encoded) != DATAC16_STATION_PAYLOAD_BYTES:
        raise ValueError("CQ exceeds compact DATAC16 payload")
    return encoded


def decode_cq(data: bytes) -> CqFrame:
    if (len(data) == DATAC16_STATION_PAYLOAD_BYTES
            and data[0] == DATAC16_CQ_MARKER):
        return _decode_datac16_cq(data)
    if len(data) >= 5 and data[:4] == CQ_MAGIC and data[4] == COMPACT_VERSION:
        return _decode_datac15_cq(data)
    minimum = LEGACY_CQ_HEADER.size + 3
    if len(data) < minimum:
        raise ValueError("CQ is truncated")
    magic, version_id, timestamp = LEGACY_CQ_HEADER.unpack_from(data)
    if magic != CQ_MAGIC or version_id not in (1, PREVIOUS_COMPACT_VERSION):
        raise ValueError("Unsupported CQ")
    call_len, grid_len, version_len = data[LEGACY_CQ_HEADER.size:minimum]
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


def _decode_datac15_cq(data: bytes) -> CqFrame:
    if len(data) < DATAC15_HEADER.size:
        raise ValueError("CQ is truncated")
    magic, version_id, reserved, call_len, grid_code = DATAC15_HEADER.unpack_from(data)
    if magic != CQ_MAGIC or version_id != COMPACT_VERSION or reserved:
        raise ValueError("Unsupported CQ")
    if len(data) != DATAC15_HEADER.size + call_len:
        raise ValueError("Invalid CQ length")
    callsign = normalize_callsign(data[DATAC15_HEADER.size:].decode("ascii"))
    return CqFrame(
        callsign, _decode_grid(grid_code), "compact", datetime.now(UTC).isoformat()
    )


def _decode_datac16_cq(data: bytes) -> CqFrame:
    if len(data) != DATAC16_STATION_PAYLOAD_BYTES or data[0] != DATAC16_CQ_MARKER:
        raise ValueError("CQ is truncated")
    return CqFrame(
        _decode_compact_callsign(data[5:]),
        _decode_grid(int.from_bytes(data[1:5], "big")),
        "compact",
        datetime.now(UTC).isoformat(),
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
        self.transport.send_station_payload(encode_beacon(beacon))

    def send_cq(self, cq) -> None:
        self.transport.send_station_payload(encode_cq(cq))

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

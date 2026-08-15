"""Pure parsers for Mercury's documented UI WebSocket payloads."""

from __future__ import annotations

import json
import math
import struct
from dataclasses import dataclass

from application.modem import ModemStatus, SpectrumFrame


SPECTRUM_MAGIC = 0x4D435259
SPECTRUM_HEADER = struct.Struct("<IHH")
MAX_SPECTRUM_BINS = 4096
MAX_DEVICE_COUNT = 64


@dataclass(frozen=True, slots=True)
class MercuryDevice:
    name: str
    identifier: str


def _finite_float(value: object, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _optional_nonnegative_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if number >= 0 else None


def _optional_positive_int(value: object) -> int | None:
    number = _optional_nonnegative_int(value)
    return number if number is not None and number > 0 else None


def parse_status_message(payload: str | bytes) -> ModemStatus | None:
    try:
        raw = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError):
        return None
    if not isinstance(raw, dict) or raw.get("type") != "status":
        return None
    direction = str(raw.get("direction", "rx")).lower()
    if direction not in {"rx", "tx"}:
        direction = "rx"
    return ModemStatus(
        bitrate_bps=max(0, _safe_int(raw.get("bitrate"))),
        snr_db=_finite_float(raw.get("snr")),
        sync=bool(raw.get("sync", False)),
        direction=direction,
        user_callsign=str(raw.get("user_callsign", ""))[:16],
        destination_callsign=str(raw.get("dest_callsign", ""))[:16],
        client_connected=bool(raw.get("client_tcp_connected", False)),
        bytes_transmitted=max(0, _safe_int(raw.get("bytes_transmitted"))),
        bytes_received=max(0, _safe_int(raw.get("bytes_received"))),
        waterfall_enabled=bool(raw.get("waterfall", False)),
        modem_mode=str(
            raw.get("modem_mode", raw.get("mode", "ARQ" if raw.get("sync") else "idle"))
        )[:32],
        arq_tx_mode=str(raw.get("arq_tx_mode", ""))[:16],
        arq_rx_mode=str(raw.get("arq_rx_mode", ""))[:16],
        tx_gain_db=max(-20.0, min(20.0, _finite_float(raw.get("tx_gain_db")))),
        tx_peak_dbfs=max(-120.0, min(20.0, _finite_float(raw.get("tx_peak_dbfs"), -120.0))),
        radio_frequency_hz=_optional_positive_int(raw.get("radio_frequency_hz")),
        radio_frequency_age_ms=_optional_nonnegative_int(
            raw.get("radio_frequency_age_ms")
        ),
    )


def parse_device_list_message(
    payload: str | bytes,
) -> tuple[str, tuple[MercuryDevice, ...], str] | None:
    """Parse Mercury's bounded capture/playback device-list message."""
    try:
        raw = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError):
        return None
    if not isinstance(raw, dict):
        return None
    message_type = raw.get("type")
    if message_type not in {"capture_dev_list", "playback_dev_list"}:
        return None
    entries = raw.get("list")
    if not isinstance(entries, list) or len(entries) > MAX_DEVICE_COUNT:
        return None
    devices: list[MercuryDevice] = []
    for entry in entries:
        if not isinstance(entry, dict):
            return None
        name = entry.get("name")
        identifier = entry.get("id")
        if not isinstance(name, str) or not isinstance(identifier, str):
            return None
        if not identifier or len(name) > 256 or len(identifier) > 512:
            return None
        devices.append(MercuryDevice(name, identifier))
    return str(message_type), tuple(devices), str(raw.get("selected", ""))[:512]


def parse_spectrum_frame(payload: bytes) -> SpectrumFrame | None:
    if len(payload) < SPECTRUM_HEADER.size:
        return None
    magic, fft_size, sample_rate = SPECTRUM_HEADER.unpack_from(payload)
    if magic != SPECTRUM_MAGIC or fft_size == 0 or fft_size > MAX_SPECTRUM_BINS:
        return None
    expected_size = SPECTRUM_HEADER.size + fft_size * 4
    if len(payload) != expected_size or sample_rate == 0:
        return None
    bins = struct.unpack_from(f"<{fft_size}f", payload, SPECTRUM_HEADER.size)
    if not all(math.isfinite(value) for value in bins):
        return None
    return SpectrumFrame(sample_rate_hz=sample_rate, bins_db=tuple(bins))

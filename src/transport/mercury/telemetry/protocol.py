"""Pure parsers for Mercury's documented UI WebSocket payloads."""

from __future__ import annotations

import json
import math
import struct

from application.modem import ModemStatus, SpectrumFrame


SPECTRUM_MAGIC = 0x4D435259
SPECTRUM_HEADER = struct.Struct("<IHH")
MAX_SPECTRUM_BINS = 4096


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
    )


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

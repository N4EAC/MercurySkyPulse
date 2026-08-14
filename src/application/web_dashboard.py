"""Thread-safe, read-only projections for the local web interface."""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, is_dataclass
from enum import Enum
from datetime import UTC, datetime
from threading import RLock
from typing import Iterable


def _plain(value):
    if is_dataclass(value):
        original = value
        value = asdict(value)
        if hasattr(original, "progress"):
            value["progress"] = original.progress
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


class WebDashboardSnapshot:
    """Copies application projections for a separate HTTP worker thread."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._station = {
            "engine": "starting", "telemetry": "disconnected",
            "link": "disconnected", "modem": "offline", "direction": "idle",
            "snr_db": None, "bitrate_bps": None, "source_call": None,
            "destination_call": None, "bandwidth_hz": None,
        }
        self._conversations: list[dict] = []
        self._messages: list[dict] = []
        self._transfers: list[dict] = []
        self._license = {"status": "community", "edition": "community",
                         "organization": None, "expires_at": None, "features": []}
        self._plugins: list[dict] = []
        self._logs: deque[str] = deque(["Mercury SkyPulse initialized"], maxlen=500)

    def update_station(self, **values) -> None:
        allowed = set(self._station)
        with self._lock:
            self._station.update({key: _plain(value) for key, value in values.items() if key in allowed})

    def update_messages(self, conversations: Iterable, messages: Iterable) -> None:
        with self._lock:
            self._conversations = [_plain(item) for item in conversations][-250:]
            self._messages = [_plain(item) for item in messages][-1000:]

    def update_transfers(self, transfers: Iterable) -> None:
        with self._lock:
            self._transfers = [_plain(item) for item in transfers][-250:]

    def append_log(self, line: str) -> None:
        clean = str(line).replace("\x00", "").strip()
        if clean:
            with self._lock:
                timestamp = datetime.now(UTC).isoformat(timespec="seconds")
                self._logs.append(f"{timestamp} · {clean[:2000]}")

    def update_license(self, state) -> None:
        with self._lock:
            self._license = {
                "status": _plain(state.status), "edition": state.edition,
                "organization": state.organization,
                "expires_at": None if state.expires_at is None else state.expires_at.isoformat(),
                "features": sorted(state.features),
            }

    def update_plugins(self, plugins: Iterable[dict]) -> None:
        with self._lock:
            self._plugins = [_plain(item) for item in plugins][:500]

    def read(self) -> dict[str, object]:
        with self._lock:
            return {
                "station": dict(self._station),
                "conversations": [dict(item) for item in self._conversations],
                "messages": [dict(item) for item in self._messages],
                "transfers": [dict(item) for item in self._transfers],
                "logs": list(self._logs),
                "license": dict(self._license),
                "plugins": [dict(item) for item in self._plugins],
            }

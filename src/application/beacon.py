"""Validated periodic capability beacon over an established Mercury session."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import re

from PySide6.QtCore import QObject, QTimer, Signal

from .location import Location
from persistence.chat_repository import ChatRepository
from application_protocol.beacon import normalize_callsign


INTERVALS_MINUTES = (0, 1, 5, 10, 15, 30, 60)
GRID = re.compile(r"^[A-R]{2}\d{2}(?:[A-X]{2}(?:\d{2})?)?$")
CAPABILITY = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")


@dataclass(frozen=True, slots=True)
class Beacon:
    callsign: str
    grid: str
    software_version: str
    capabilities: tuple[str, ...]
    timestamp: str
    latitude: float | None = None
    longitude: float | None = None
    gps_timestamp: str | None = None


@dataclass(frozen=True, slots=True)
class BeaconConfig:
    callsign: str = ""
    grid: str = ""
    interval_minutes: int = 0
    include_gps: bool = False


def normalize_grid(value: str) -> str:
    grid = value.strip().upper()
    if not GRID.fullmatch(grid):
        raise ValueError("Grid must be a 4, 6, or 8 character Maidenhead locator")
    return grid


class BeaconService(QObject):
    config_changed = Signal(object)
    state_changed = Signal(str)
    beacon_received = Signal(object)
    error_received = Signal(str)

    def __init__(
        self,
        client,
        repository: ChatRepository,
        software_version: str,
        capabilities: tuple[str, ...],
        auto_timer: bool = True,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.client = client
        self.repository = repository
        self.software_version = software_version[:32]
        self.capabilities = self._normalize_capabilities(capabilities)
        self.config = self._load_config()
        self.latest_gps: Location | None = None
        self.auto_timer = auto_timer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._timer_fired)
        client.beacon_received.connect(self._on_beacon)
        client.error_received.connect(self.error_received)

    def start(self) -> None:
        self.client.start()
        self.config_changed.emit(self.config)
        self._schedule()

    def stop(self) -> None:
        self._timer.stop()
        self.client.stop()
        self.state_changed.emit("stopped")

    def disable(self) -> None:
        if self.config.callsign and self.config.grid:
            self.configure(
                self.config.callsign, self.config.grid, 0, self.config.include_gps
            )
        else:
            self.stop()

    def configure(
        self, callsign: str, grid: str, interval_minutes: int, include_gps: bool
    ) -> None:
        try:
            normalized_call = normalize_callsign(callsign)
            normalized_grid = normalize_grid(grid)
            interval = int(interval_minutes)
            if interval not in INTERVALS_MINUTES:
                raise ValueError("Select a supported beacon interval")
            self.config = BeaconConfig(
                normalized_call, normalized_grid, interval, bool(include_gps)
            )
            self.repository.set_setting(
                "beacon.config",
                json.dumps(
                    {
                        "callsign": normalized_call,
                        "grid": normalized_grid,
                        "interval_minutes": interval,
                        "include_gps": bool(include_gps),
                    }
                ),
                self._now(),
            )
            self.config_changed.emit(self.config)
            self._schedule()
        except (TypeError, ValueError) as error:
            self.error_received.emit(str(error))

    def update_location(self, location: Location) -> None:
        if location.source == "gps":
            self.latest_gps = location

    def send_now(self) -> None:
        try:
            self._transmit()
        except (RuntimeError, ValueError) as error:
            self.error_received.emit(str(error))

    def _timer_fired(self) -> None:
        try:
            self._transmit()
        except (RuntimeError, ValueError):
            self.state_changed.emit("waiting-for-broadcast-interface")

    def _transmit(self) -> None:
        if not self.config.callsign or not self.config.grid:
            raise ValueError("Configure a callsign and grid before beaconing")
        timestamp = self._now()
        latitude = longitude = gps_timestamp = None
        if self.config.include_gps and self.latest_gps:
            latitude = round(self.latest_gps.latitude, 6)
            longitude = round(self.latest_gps.longitude, 6)
            gps_timestamp = self.latest_gps.timestamp[:40]
        self.client.send_beacon(
            Beacon(
                self.config.callsign,
                self.config.grid,
                self.software_version,
                self.capabilities,
                timestamp,
                latitude,
                longitude,
                gps_timestamp,
            )
        )
        self.state_changed.emit("sent")

    def _on_beacon(self, beacon: Beacon) -> None:
        self.beacon_received.emit(beacon)

    def _schedule(self) -> None:
        self._timer.stop()
        if self.config.interval_minutes == 0:
            self.state_changed.emit("off")
        else:
            self._timer.setInterval(self.config.interval_minutes * 60 * 1000)
            if self.auto_timer:
                self._timer.start()
            self.state_changed.emit(
                f"every-{self.config.interval_minutes}-minutes"
            )

    def _load_config(self) -> BeaconConfig:
        raw_value = self.repository.get_setting("beacon.config")
        if not raw_value:
            return BeaconConfig()
        try:
            raw = json.loads(raw_value)
            call = normalize_callsign(str(raw["callsign"]))
            grid = normalize_grid(str(raw["grid"]))
            interval = int(raw["interval_minutes"])
            if interval not in INTERVALS_MINUTES:
                raise ValueError
            return BeaconConfig(call, grid, interval, bool(raw["include_gps"]))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            return BeaconConfig()

    @staticmethod
    def _normalize_capabilities(values: tuple[object, ...]) -> tuple[str, ...]:
        normalized = tuple(sorted({str(value).lower() for value in values}))
        if len(normalized) > 16 or any(
            not CAPABILITY.fullmatch(value) for value in normalized
        ):
            raise ValueError("Invalid beacon capabilities")
        return normalized

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

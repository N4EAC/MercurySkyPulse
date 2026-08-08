"""Position validation, APRS conversion, persistence, and explicit sharing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import math
from pathlib import Path
import re
from uuid import uuid4

from PySide6.QtCore import QObject, Signal

from persistence.chat_repository import ChatRepository


APRS_POSITION = re.compile(
    r"^(\d{2})(\d{2}\.\d{2})([NS])/(\d{3})(\d{2}\.\d{2})([EW])$"
)


@dataclass(frozen=True, slots=True)
class Location:
    latitude: float
    longitude: float
    source: str
    timestamp: str
    accuracy_m: float | None = None

    @property
    def aprs(self) -> str:
        return to_aprs(self.latitude, self.longitude)


def validate_coordinates(latitude: float, longitude: float) -> tuple[float, float]:
    if not math.isfinite(latitude) or not -90 <= latitude <= 90:
        raise ValueError("Latitude must be between -90 and 90")
    if not math.isfinite(longitude) or not -180 <= longitude <= 180:
        raise ValueError("Longitude must be between -180 and 180")
    return latitude, longitude


def to_aprs(latitude: float, longitude: float) -> str:
    latitude, longitude = validate_coordinates(latitude, longitude)
    lat_total = round(abs(latitude) * 60 * 100)
    lon_total = round(abs(longitude) * 60 * 100)
    lat_degrees, lat_minute_hundredths = divmod(lat_total, 6000)
    lon_degrees, lon_minute_hundredths = divmod(lon_total, 6000)
    lat_minutes = lat_minute_hundredths / 100
    lon_minutes = lon_minute_hundredths / 100
    return (
        f"{lat_degrees:02d}{lat_minutes:05.2f}{'N' if latitude >= 0 else 'S'}/"
        f"{lon_degrees:03d}{lon_minutes:05.2f}{'E' if longitude >= 0 else 'W'}"
    )


def from_aprs(value: str) -> tuple[float, float]:
    match = APRS_POSITION.fullmatch(value.strip().upper())
    if not match:
        raise ValueError("Use APRS format DDMM.mmN/DDDMM.mmE")
    lat_degrees, lat_minutes, ns, lon_degrees, lon_minutes, ew = match.groups()
    lat_minute_value = float(lat_minutes)
    lon_minute_value = float(lon_minutes)
    if lat_minute_value >= 60 or lon_minute_value >= 60:
        raise ValueError("APRS minutes must be below 60")
    latitude = int(lat_degrees) + lat_minute_value / 60
    longitude = int(lon_degrees) + lon_minute_value / 60
    if ns == "S":
        latitude = -latitude
    if ew == "W":
        longitude = -longitude
    return validate_coordinates(latitude, longitude)


class LocationService(QObject):
    current_changed = Signal(object)
    shared_received = Signal(object)
    gps_state_changed = Signal(str)
    retention_changed = Signal(bool)
    history_changed = Signal(int)
    export_completed = Signal(str)
    error_received = Signal(str)

    def __init__(
        self,
        client,
        repository: ChatRepository,
        receiver,
        exporter=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.client = client
        self.repository = repository
        self.receiver = receiver
        self.exporter = exporter
        self.retention_enabled = (
            repository.get_setting("location.retention_enabled") == "true"
        )
        self.current: Location | None = None
        receiver.position_received.connect(self._on_gps_position)
        receiver.state_changed.connect(self.gps_state_changed)
        receiver.error_received.connect(self.error_received)
        client.location_received.connect(self._on_shared_location)
        self._load_manual()

    def set_manual(self, latitude_text: str, longitude_text: str) -> None:
        try:
            latitude, longitude = validate_coordinates(
                float(latitude_text), float(longitude_text)
            )
            self._set_current(Location(latitude, longitude, "manual", self._now()))
            self.repository.set_setting(
                "location.manual",
                json.dumps({"latitude": latitude, "longitude": longitude}),
                self._now(),
            )
        except (TypeError, ValueError) as error:
            self.error_received.emit(str(error))

    def set_manual_aprs(self, value: str) -> None:
        try:
            latitude, longitude = from_aprs(value)
            self.set_manual(str(latitude), str(longitude))
        except ValueError as error:
            self.error_received.emit(str(error))

    def start_gps(self, serial_port: str = "") -> None:
        self.receiver.start(serial_port.strip())

    def stop_gps(self) -> None:
        self.receiver.stop()

    def set_retention(self, enabled: bool) -> None:
        self.retention_enabled = bool(enabled)
        self.repository.set_setting(
            "location.retention_enabled",
            "true" if self.retention_enabled else "false",
            self._now(),
        )
        self.retention_changed.emit(self.retention_enabled)

    def export_history(self, path_value: str) -> None:
        if not self.exporter:
            self.error_received.emit("GPS export is unavailable")
            return
        try:
            locations = [
                Location(latitude, longitude, "gps", timestamp, accuracy)
                for latitude, longitude, accuracy, timestamp
                in self.repository.list_gps_locations()
            ]
            destination = self.exporter.export(locations, Path(path_value))
            self.export_completed.emit(str(destination))
        except (OSError, ValueError) as error:
            self.error_received.emit(str(error))

    def share(self) -> None:
        if not self.current:
            self.error_received.emit("Set a manual position or acquire GPS first")
            return
        try:
            latitude = round(self.current.latitude, 6)
            longitude = round(self.current.longitude, 6)
            self.client.send_file_event(
                "location",
                str(uuid4()),
                self._now(),
                latitude=latitude,
                longitude=longitude,
                aprs=to_aprs(latitude, longitude),
                source=self.current.source,
                accuracy_m=self.current.accuracy_m,
            )
        except RuntimeError as error:
            self.error_received.emit(str(error))

    def stop(self) -> None:
        self.receiver.stop()

    def _on_gps_position(self, latitude: float, longitude: float, accuracy) -> None:
        try:
            latitude, longitude = validate_coordinates(latitude, longitude)
            accuracy_value = None if accuracy is None else float(accuracy)
            if accuracy_value is not None and (
                not math.isfinite(accuracy_value) or accuracy_value < 0
            ):
                raise ValueError("Accuracy must be a non-negative finite value")
            location = Location(
                latitude, longitude, "gps", self._now(), accuracy_value
            )
            self._set_current(location)
            if self.retention_enabled:
                self.repository.save_gps_location(
                    location.latitude,
                    location.longitude,
                    location.accuracy_m,
                    location.timestamp,
                )
                self.history_changed.emit(self.repository.gps_location_count())
        except (TypeError, ValueError) as error:
            self.error_received.emit(f"Invalid GPS position: {error}")

    def _on_shared_location(self, envelope) -> None:
        values = envelope.values or {}
        try:
            latitude, longitude = validate_coordinates(
                float(values["latitude"]), float(values["longitude"])
            )
            if to_aprs(latitude, longitude) != str(values.get("aprs", "")):
                raise ValueError("APRS coordinates do not match decimal coordinates")
            accuracy = values.get("accuracy_m")
            location = Location(
                latitude,
                longitude,
                "shared",
                envelope.timestamp,
                None if accuracy is None else max(0.0, float(accuracy)),
            )
            self.shared_received.emit(location)
        except (KeyError, TypeError, ValueError) as error:
            self.error_received.emit(f"Invalid shared location: {error}")

    def _load_manual(self) -> None:
        value = self.repository.get_setting("location.manual")
        if not value:
            return
        try:
            raw = json.loads(value)
            latitude, longitude = validate_coordinates(
                float(raw["latitude"]), float(raw["longitude"])
            )
            self.current = Location(latitude, longitude, "manual", self._now())
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            pass

    def publish_current(self) -> None:
        self.retention_changed.emit(self.retention_enabled)
        self.history_changed.emit(self.repository.gps_location_count())
        if self.current:
            self.current_changed.emit(self.current)

    def _set_current(self, location: Location) -> None:
        self.current = location
        self.current_changed.emit(location)

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

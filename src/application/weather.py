"""Opt-in, manual weather preview for chat composition."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import math

from PySide6.QtCore import QObject, Signal

from application.location import validate_coordinates


@dataclass(frozen=True, slots=True)
class WeatherReport:
    text: str
    source_location: str
    observation_time: str


def maidenhead_center(grid_value: str) -> tuple[float, float]:
    grid = grid_value.strip().upper()
    if len(grid) not in {4, 6, 8}:
        raise ValueError("Save a valid station GRID or position before fetching weather")
    lon = (ord(grid[0]) - 65) * 20.0 - 180.0
    lat = (ord(grid[1]) - 65) * 10.0 - 90.0
    if not (0 <= ord(grid[0]) - 65 < 18 and 0 <= ord(grid[1]) - 65 < 18):
        raise ValueError("Save a valid station GRID or position before fetching weather")
    if not (grid[2:4].isdigit()):
        raise ValueError("Save a valid station GRID or position before fetching weather")
    lon += int(grid[2]) * 2.0
    lat += int(grid[3])
    lon_size, lat_size = 2.0, 1.0
    if len(grid) >= 6:
        a, b = ord(grid[4]) - 65, ord(grid[5]) - 65
        if not (0 <= a < 24 and 0 <= b < 24):
            raise ValueError("Save a valid station GRID or position before fetching weather")
        lon_size, lat_size = 2.0 / 24.0, 1.0 / 24.0
        lon += a * lon_size
        lat += b * lat_size
    if len(grid) == 8:
        if not grid[6:8].isdigit():
            raise ValueError("Save a valid station GRID or position before fetching weather")
        lon_size, lat_size = lon_size / 10.0, lat_size / 10.0
        lon += int(grid[6]) * lon_size
        lat += int(grid[7]) * lat_size
    return validate_coordinates(lat + lat_size / 2, lon + lon_size / 2)


class WeatherService(QObject):
    enabled_changed = Signal(bool)
    position_preference_changed = Signal(bool)
    state_changed = Signal(str)
    report_ready = Signal(object)
    chat_report_ready = Signal(str)
    error_received = Signal(str)

    def __init__(self, repository, provider, parent=None) -> None:
        super().__init__(parent)
        self.repository = repository
        self.provider = provider
        self.enabled = repository.get_setting("weather.internet_enabled") == "true"
        saved_position_preference = repository.get_setting("weather.use_station_position")
        self.use_station_position = saved_position_preference != "false"
        self.location = None
        self.grid = ""
        self.report: WeatherReport | None = None
        self._fetching = False
        self._insert_after_fetch = False
        provider.received.connect(self._received)
        provider.error_received.connect(self._error)

    def start(self) -> None:
        self.enabled_changed.emit(self.enabled)
        self.position_preference_changed.emit(self.use_station_position)
        self.state_changed.emit("Ready" if self.enabled else "Internet access disabled")

    def set_use_station_position(self, enabled: bool) -> None:
        self.use_station_position = bool(enabled)
        self.repository.set_setting(
            "weather.use_station_position",
            "true" if self.use_station_position else "false",
            datetime.now(UTC).isoformat(),
        )
        self.position_preference_changed.emit(self.use_station_position)

    def configure(self, enabled: bool) -> None:
        self.enabled = bool(enabled)
        self.repository.set_setting(
            "weather.internet_enabled", "true" if self.enabled else "false",
            datetime.now(UTC).isoformat(),
        )
        self.enabled_changed.emit(self.enabled)
        self.state_changed.emit("Ready" if self.enabled else "Internet access disabled")

    def update_location(self, location) -> None:
        self.location = location

    def update_grid(self, config) -> None:
        self.grid = str(config.grid)

    def fetch(self) -> None:
        self._begin_fetch(insert_into_chat=False)

    def fetch_for_chat(self) -> None:
        self._begin_fetch(insert_into_chat=True)

    def _begin_fetch(self, insert_into_chat: bool) -> None:
        try:
            if not self.enabled:
                raise ValueError("Enable internet weather access before fetching")
            if self._fetching:
                raise ValueError("A weather request is already in progress")
            if self.use_station_position and self.location is not None:
                latitude, longitude = validate_coordinates(
                    float(self.location.latitude), float(self.location.longitude)
                )
            else:
                latitude, longitude = maidenhead_center(self.grid)
            self._fetching = True
            self._insert_after_fetch = insert_into_chat
            self.state_changed.emit("Fetching weather…")
            self.provider.fetch(latitude, longitude)
        except (TypeError, ValueError) as error:
            self.error_received.emit(str(error))

    def _received(self, data: bytes) -> None:
        try:
            raw = json.loads(data)
            current = raw["current_condition"][0]
            area = raw.get("nearest_area", [{}])[0]
            condition = self._value(current, "weatherDesc", nested=True)
            if not condition:
                raise ValueError("weather condition is missing")
            temperature = self._bounded_number(current.get("temp_C"), -100, 100)
            humidity = self._bounded_number(current.get("humidity"), 0, 100)
            wind_speed = self._bounded_number(current.get("windspeedKmph"), 0, 500)
            pressure = self._bounded_number(current.get("pressure"), 800, 1200)
            wind_direction = self._clean_text(current.get("winddir16Point", ""), 4)
            location = self._value(area, "areaName", nested=True) or "station position"
            observed = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
            text = (
                f"WX {self.grid or 'POSITION'} {condition} {temperature:g}°C "
                f"RH {humidity:g}% WIND {wind_direction or '?'} {wind_speed:g} km/h "
                f"PRESS {pressure:g} hPa · fetched {observed} · wttr.in"
            )
            if len(text) > 320:
                raise ValueError("Weather report exceeds the chat preview limit")
            self.report = WeatherReport(text, location[:80], observed)
            self._fetching = False
            self.report_ready.emit(self.report)
            if self._insert_after_fetch:
                self.chat_report_ready.emit(self.report.text)
            self._insert_after_fetch = False
            self.state_changed.emit(f"Weather received for {self.report.source_location}")
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as error:
            self._fetching = False
            self._insert_after_fetch = False
            self.state_changed.emit("Ready" if self.enabled else "Internet access disabled")
            self.error_received.emit(f"Weather response could not be read: {error}")

    def _error(self, message: str) -> None:
        self._fetching = False
        self._insert_after_fetch = False
        self.state_changed.emit("Ready" if self.enabled else "Internet access disabled")
        self.error_received.emit(message)

    @staticmethod
    def _value(container: dict, key: str, nested: bool = False) -> str:
        value = container.get(key, "")
        if nested:
            value = value[0].get("value", "") if isinstance(value, list) and value else ""
        return WeatherService._clean_text(value, 80)

    @staticmethod
    def _clean_text(value, maximum: int) -> str:
        return " ".join(str(value).split())[:maximum]

    @staticmethod
    def _bounded_number(value, minimum: float, maximum: float) -> float:
        number = float(value)
        if not math.isfinite(number) or not minimum <= number <= maximum:
            raise ValueError("weather value is outside its valid range")
        return number

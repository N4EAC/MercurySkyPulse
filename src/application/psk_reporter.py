"""Opt-in PSK Reporter reception aggregation service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import random
import time

from PySide6.QtCore import QObject, QTimer, Signal

from application.beacon import normalize_grid
from application_protocol.beacon import normalize_callsign


FLUSH_BASE_MS = 300_000
FLUSH_JITTER_MS = 30_000
DEDUP_SECONDS = 300
MAX_FREQUENCY_AGE_MS = 30_000
MAX_QUEUED_REPORTS = 16


@dataclass(frozen=True, slots=True)
class PskReporterConfig:
    enabled: bool = False
    antenna: str = ""


@dataclass(frozen=True, slots=True)
class PskReception:
    sender_callsign: str
    sender_locator: str
    frequency_hz: int
    mode: str
    received_at: int


class PskReporterService(QObject):
    config_changed = Signal(object)
    state_changed = Signal(str)
    error_received = Signal(str)
    activity_logged = Signal(str)

    def __init__(self, beacon_service, telemetry, repository, uploader,
                 software_version: str,
                 random_delay=None, parent=None) -> None:
        super().__init__(parent)
        self.beacon_service = beacon_service
        self.repository = repository
        self.uploader = uploader
        self.telemetry = telemetry
        self.software = f"MercurySkyPulse {software_version}"[:254]
        self.config = self._load_config()
        self._reports: list[PskReception] = []
        self._last_seen: dict[tuple[str, int], float] = {}
        self._template_packets = 0
        self._last_template_at = 0.0
        self._frequency_hz: int | None = None
        self._frequency_age_ms: int | None = None
        self._random_delay = random_delay or (lambda: random.randint(0, FLUSH_JITTER_MS))
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.flush)
        beacon_service.beacon_received.connect(self.observe)
        telemetry.status_received.connect(self._status_received)
        uploader.sent.connect(self._sent)
        uploader.error_received.connect(self.error_received)
        uploader.error_received.connect(
            lambda message: self._log(f"ERROR destination=report.pskreporter.info:4739 message={message}")
        )
        if hasattr(uploader, "activity_logged"):
            uploader.activity_logged.connect(self._log)

    def start(self) -> None:
        self.config_changed.emit(self.config)
        self.state_changed.emit("enabled" if self.config.enabled else "disabled")

    def stop(self) -> None:
        self._timer.stop()

    def configure(self, enabled: bool, antenna: str) -> None:
        try:
            clean_antenna = antenna.strip()
            if len(clean_antenna.encode("utf-8")) > 254 or any(
                character in clean_antenna for character in "\r\n\0"
            ):
                raise ValueError("Antenna description is invalid")
            if enabled:
                normalize_callsign(self.beacon_service.config.callsign)
                normalize_grid(self.beacon_service.config.grid)
            self.config = PskReporterConfig(bool(enabled), clean_antenna)
            self.repository.set_setting(
                "psk_reporter.config",
                json.dumps({
                    "enabled": self.config.enabled,
                    "antenna": self.config.antenna,
                }),
                datetime.now(UTC).isoformat(),
            )
            self.config_changed.emit(self.config)
            self.state_changed.emit("enabled" if enabled else "disabled")
            self._log(
                f"CONFIG enabled={self.config.enabled} "
                f"antenna={self.config.antenna or 'Unspecified'}"
            )
            if not enabled:
                self._timer.stop()
                self._reports.clear()
        except (TypeError, ValueError) as error:
            self.error_received.emit(str(error))

    def observe(self, beacon) -> None:
        if not self.config.enabled:
            return
        if (
            self._frequency_hz is None
            or self._frequency_age_ms is None
            or self._frequency_age_ms > MAX_FREQUENCY_AGE_MS
        ):
            self.state_changed.emit("waiting-for-frequency")
            self._log("SKIP reason=frequency-unavailable-or-stale")
            return
        now = time.monotonic()
        key = (beacon.callsign, self._frequency_hz)
        if now - self._last_seen.get(key, -DEDUP_SECONDS) < DEDUP_SECONDS:
            return
        try:
            received_at = int(datetime.fromisoformat(beacon.timestamp).timestamp())
            report = PskReception(
                normalize_callsign(beacon.callsign), normalize_grid(beacon.grid),
                self._frequency_hz, "OFDM", received_at,
            )
        except (TypeError, ValueError) as error:
            self.error_received.emit(f"PSK Reporter ignored beacon: {error}")
            return
        self._last_seen[key] = now
        self._reports.append(report)
        self._log(
            "QUEUE "
            f"sender_callsign={report.sender_callsign} "
            f"sender_grid={report.sender_locator} "
            f"frequency_hz={report.frequency_hz} mode={report.mode} "
            f"information_source=automatically-extracted "
            f"received_at={report.received_at}"
        )
        self.state_changed.emit(f"queued-{len(self._reports)}")
        if len(self._reports) >= MAX_QUEUED_REPORTS:
            self.flush()
            return
        if not self._timer.isActive():
            self._timer.start(FLUSH_BASE_MS + int(self._random_delay()))

    def flush(self) -> None:
        if not self.config.enabled or not self._reports:
            return
        reports = tuple(self._reports)
        self._reports.clear()
        now = time.monotonic()
        include_templates = (
            self._template_packets < 3 or now - self._last_template_at >= 3600
        )
        if include_templates:
            self._template_packets += 1
            self._last_template_at = now
        receiver = self.beacon_service.config
        self._log(
            "UPLOAD "
            "destination=report.pskreporter.info:4739 "
            f"receiver_callsign={receiver.callsign} receiver_grid={receiver.grid} "
            f"software={self.software} "
            f"antenna={self.config.antenna or 'Unspecified'} "
            f"templates={include_templates} reports={len(reports)}"
        )
        for report in reports:
            self._log(
                "REPORT "
                f"sender_callsign={report.sender_callsign} "
                f"sender_grid={report.sender_locator} "
                f"frequency_hz={report.frequency_hz} mode={report.mode} "
                "information_source=automatically-extracted "
                f"received_at={report.received_at}"
            )
        self.uploader.upload(
            receiver.callsign, receiver.grid, self.software,
            self.config.antenna or "Unspecified", reports,
            include_templates,
        )
        self.state_changed.emit("uploading")

    def _sent(self, count: int) -> None:
        self.state_changed.emit(f"sent-{count}")
        self._log(f"SENT reports={count} transport=UDP")

    def _log(self, message: str) -> None:
        timestamp = datetime.now(UTC).isoformat(timespec="seconds")
        self.activity_logged.emit(f"{timestamp} {message}")

    def _status_received(self, status) -> None:
        self._frequency_hz = status.radio_frequency_hz
        self._frequency_age_ms = status.radio_frequency_age_ms
        if self.config.enabled and self._frequency_hz is not None:
            self.state_changed.emit(
                f"frequency-{self._frequency_hz}-{self._frequency_age_ms or 0}"
            )

    def _load_config(self) -> PskReporterConfig:
        try:
            raw = json.loads(self.repository.get_setting("psk_reporter.config") or "{}")
            antenna = str(raw.get("antenna", ""))[:254]
            enabled = bool(raw.get("enabled", False))
            return PskReporterConfig(enabled, antenna)
        except (json.JSONDecodeError, TypeError, ValueError):
            return PskReporterConfig()

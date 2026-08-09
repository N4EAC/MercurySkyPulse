"""Radio-station setup and bounded Mercury tuning workflows."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, QTimer, Signal


TUNE_MIN_DBFS = -60
TUNE_MAX_DBFS = 0
TUNE_TIMEOUT_MS = 12_000


@dataclass(frozen=True, slots=True)
class HamlibRig:
    model_id: int
    manufacturer: str
    model: str
    version: str
    status: str
    macro: str

    @property
    def label(self) -> str:
        return f"{self.manufacturer} {self.model} (#{self.model_id})"


@dataclass(frozen=True, slots=True)
class RadioStationConfig:
    model_id: int | None = None
    device: str = ""
    serial_speed: int = 0
    input_device: str = ""
    output_device: str = ""


class RadioStationService(QObject):
    catalog_changed = Signal(object)
    serial_ports_changed = Signal(object)
    config_changed = Signal(object)
    tune_level_changed = Signal(int)
    tune_state_changed = Signal(bool, str)
    status_changed = Signal(str)
    error_received = Signal(str)

    def __init__(self, client, repository, catalog_provider, runtime,
                 station_devices,
                 managed: bool, parent=None) -> None:
        super().__init__(parent)
        self.client = client
        self.repository = repository
        self.catalog_provider = catalog_provider
        self.runtime = runtime
        self.station_devices = station_devices
        self.managed = managed
        self._catalog: tuple[HamlibRig, ...] = ()
        self._config = self._load_config()
        self._tune_level = self._load_tune_level()
        self._tuning = False
        self._link_state = "disconnected"
        self._tune_timer = QTimer(self)
        self._tune_timer.setSingleShot(True)
        self._tune_timer.setInterval(TUNE_TIMEOUT_MS)
        self._tune_timer.timeout.connect(self._tune_timeout)
        catalog_provider.models_loaded.connect(self._set_catalog)
        catalog_provider.error_received.connect(self.error_received)
        station_devices.serial_ports_loaded.connect(self.serial_ports_changed)
        client.control_event.connect(self._on_control_event)
        if hasattr(client, "state_changed"):
            client.state_changed.connect(self._set_link_state)
        if hasattr(client, "session_disconnected"):
            client.session_disconnected.connect(self._disconnect_stop)

    @property
    def config(self) -> RadioStationConfig:
        return self._config

    @property
    def tune_level(self) -> int:
        return self._tune_level

    def start(self) -> None:
        self.config_changed.emit(self._config)
        self.tune_level_changed.emit(self._tune_level)
        self.catalog_provider.load()
        self.station_devices.load()

    def apply(self, model_id: int | None, device: str, serial_speed: int = 0,
              input_device: str = "", output_device: str = "") -> None:
        try:
            if not self.managed:
                raise ValueError(
                    "Radio configuration is managed at the external Mercury host"
                )
            if model_id is not None and model_id not in {
                rig.model_id for rig in self._catalog
            }:
                raise ValueError("Select a radio from Mercury's Hamlib catalog")
            clean_device = device.strip()
            if len(clean_device) > 512 or any(character in clean_device for character in "\r\n\0"):
                raise ValueError("Radio device/address is invalid")
            clean_input = self._validate_device(input_device, "Audio input")
            clean_output = self._validate_device(output_device, "Audio output")
            speed = int(serial_speed)
            if speed not in {0, 1200, 2400, 4800, 9600, 19200, 38400,
                             57600, 115200, 230400}:
                raise ValueError("Select a supported CAT serial speed")
            config = RadioStationConfig(
                model_id, clean_device, speed, clean_input, clean_output
            )
            now = "radio-setup"
            self.repository.set_setting(
                "radio.model_id", "" if model_id is None else str(model_id), now
            )
            self.repository.set_setting("radio.device", clean_device, now)
            self.repository.set_setting("radio.serial_speed", str(speed), now)
            self.repository.set_setting("radio.input_device", clean_input, now)
            self.repository.set_setting("radio.output_device", clean_output, now)
            self.runtime.configure_station(
                model_id, clean_device or None, speed,
                clean_input or None, clean_output or None,
            )
            self._config = config
            self.config_changed.emit(config)
            self.status_changed.emit("Station I/O configuration saved; restarting Mercury")
        except (RuntimeError, ValueError) as error:
            self.error_received.emit(str(error))

    def apply_radio(self, model_id: int | None, device: str,
                    serial_speed: int = 0) -> None:
        self.apply(
            model_id, device, serial_speed,
            self._config.input_device, self._config.output_device,
        )

    def apply_audio(self, input_device: str, output_device: str) -> None:
        self.apply(
            self._config.model_id, self._config.device, self._config.serial_speed,
            input_device, output_device,
        )

    def set_tune_level(self, level_dbfs: int) -> None:
        try:
            level = int(level_dbfs)
            if not TUNE_MIN_DBFS <= level <= TUNE_MAX_DBFS:
                raise ValueError("Tune level must be between -60 and 0 dBFS")
            self._tune_level = level
            self.repository.set_setting("radio.tune_dbfs", str(level), "radio-setup")
            self.tune_level_changed.emit(level)
            if self._tuning:
                self.client.set_tune_level(level)
        except (RuntimeError, ValueError) as error:
            self.error_received.emit(str(error))

    def start_tune(self) -> None:
        try:
            if self._link_state in {"connected", "linking"}:
                raise ValueError("Disconnect the active station link before tuning")
            self.client.start_tune(self._tune_level)
            self._tuning = True
            self._tune_timer.start()
            self.tune_state_changed.emit(True, "Tuning; automatic stop in 12 seconds")
        except (RuntimeError, ValueError) as error:
            self._tuning = False
            self._tune_timer.stop()
            self.error_received.emit(str(error))

    def stop_tune(self) -> None:
        self._stop_tune("Tune stopped", report_errors=True)

    def stop(self) -> None:
        self._stop_tune("Tune stopped during shutdown", report_errors=False)

    def _tune_timeout(self) -> None:
        self._stop_tune("Tune stopped after 12-second safety timeout", report_errors=True)

    def _disconnect_stop(self) -> None:
        if not self._tuning:
            return
        self._stop_tune("Tune stopped because the station session disconnected", False)

    def _stop_tune(self, message: str, report_errors: bool) -> None:
        was_tuning = self._tuning
        self._tuning = False
        self._tune_timer.stop()
        if was_tuning:
            try:
                self.client.stop_tune()
            except RuntimeError as error:
                if report_errors:
                    self.error_received.emit(str(error))
        self.tune_state_changed.emit(False, message)

    def _on_control_event(self, event: str) -> None:
        if self._tuning and event == "WRONG":
            self._tuning = False
            self._tune_timer.stop()
            self.tune_state_changed.emit(False, "Mercury refused the tune request")
            self.error_received.emit(
                "Mercury refused tuning; disconnect ARQ traffic and verify radio setup"
            )

    def _set_link_state(self, state: str) -> None:
        self._link_state = state
        if self._tuning and state in {"connected", "linking"}:
            self._stop_tune("Tune stopped because a station link became active", False)
        elif self._tuning and state == "disconnected":
            self._tuning = False
            self._tune_timer.stop()
            self.tune_state_changed.emit(
                False, "Mercury control disconnected; its 60-second tune failsafe remains"
            )
            self.error_received.emit(
                "Could not send TUNE OFF after control disconnect; verify the transmitter unkeyed"
            )

    def _set_catalog(self, rigs) -> None:
        self._catalog = tuple(rigs)
        self.catalog_changed.emit(self._catalog)

    @staticmethod
    def _validate_device(value: str, label: str) -> str:
        cleaned = value.strip()
        if len(cleaned) > 512 or any(character in cleaned for character in "\r\n\0"):
            raise ValueError(f"{label} device is invalid")
        return cleaned

    def _load_config(self) -> RadioStationConfig:
        raw_model = self.repository.get_setting("radio.model_id")
        try:
            model_id = int(raw_model) if raw_model else None
        except ValueError:
            model_id = None
        try:
            serial_speed = int(
                self.repository.get_setting("radio.serial_speed") or "0"
            )
        except ValueError:
            serial_speed = 0
        return RadioStationConfig(
            model_id, self.repository.get_setting("radio.device") or "",
            serial_speed,
            self.repository.get_setting("radio.input_device") or "",
            self.repository.get_setting("radio.output_device") or "",
        )

    def _load_tune_level(self) -> int:
        try:
            value = int(self.repository.get_setting("radio.tune_dbfs") or "-20")
        except ValueError:
            value = -20
        return max(TUNE_MIN_DBFS, min(TUNE_MAX_DBFS, value))

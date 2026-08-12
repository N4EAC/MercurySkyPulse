"""Radio-station setup and bounded Mercury tuning workflows."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, QTimer, Signal


TX_TEST_MIN_GAIN_DB = -20
TX_TEST_MAX_GAIN_DB = 0
TX_TEST_DURATION_MS = 12_000
TX_TEST_BEACON_INTERVAL_MS = 3_000


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
    audio_inputs_changed = Signal(object)
    audio_outputs_changed = Signal(object)
    config_changed = Signal(object)
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
        catalog_provider.models_loaded.connect(self._set_catalog)
        catalog_provider.error_received.connect(self.error_received)
        station_devices.serial_ports_loaded.connect(self.serial_ports_changed)
        if hasattr(station_devices, "audio_inputs_loaded"):
            station_devices.audio_inputs_loaded.connect(self.audio_inputs_changed)
        if hasattr(station_devices, "audio_outputs_loaded"):
            station_devices.audio_outputs_loaded.connect(self.audio_outputs_changed)

    @property
    def config(self) -> RadioStationConfig:
        return self._config

    def start(self) -> None:
        self.config_changed.emit(self._config)
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

    def stop(self) -> None:
        pass

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


class TxLevelTestService(QObject):
    """Bounded real-beacon TX gain test through documented Mercury interfaces."""

    level_changed = Signal(float)
    peak_changed = Signal(float)
    state_changed = Signal(bool, str)
    error_received = Signal(str)

    def __init__(self, beacon_service, telemetry, link_client, parent=None) -> None:
        super().__init__(parent)
        self.beacon_service = beacon_service
        self.telemetry = telemetry
        self._active = False
        self._level_db = float(TX_TEST_MIN_GAIN_DB)
        self._link_state = "disconnected"
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(TX_TEST_BEACON_INTERVAL_MS)
        self._pulse_timer.timeout.connect(self._send_beacon)
        self._deadline = QTimer(self)
        self._deadline.setSingleShot(True)
        self._deadline.setInterval(TX_TEST_DURATION_MS)
        self._deadline.timeout.connect(self._timeout)
        link_client.state_changed.connect(self._link_state_changed)
        telemetry.status_received.connect(self._status_received)
        telemetry.state_changed.connect(self._telemetry_state_changed)

    @property
    def active(self) -> bool:
        return self._active

    def set_level(self, level_db: float) -> None:
        try:
            level = float(level_db)
            if not TX_TEST_MIN_GAIN_DB <= level <= TX_TEST_MAX_GAIN_DB:
                raise ValueError("TX test gain must be between -20 and 0 dB")
            if self._link_state in {"connected", "linking"}:
                raise ValueError("Disconnect the active station link before changing TX gain")
            self.telemetry.set_tx_gain_db(level)
            self._level_db = level
            self.level_changed.emit(level)
        except (RuntimeError, TypeError, ValueError) as error:
            self.error_received.emit(str(error))

    def start(self) -> None:
        try:
            if self._active:
                return
            if self._link_state in {"connected", "linking"}:
                raise ValueError("Disconnect the active station link before starting the TX test")
            config = self.beacon_service.config
            if not config.callsign or not config.grid:
                raise ValueError("Save the station callsign and GRID before starting the TX test")
            self.telemetry.set_tx_gain_db(self._level_db)
            self.beacon_service.transmit_test_beacon()
            self._active = True
            self._pulse_timer.start()
            self._deadline.start()
            self.state_changed.emit(True, "TX level test active; automatic stop in 12 seconds")
        except (RuntimeError, TypeError, ValueError) as error:
            self._active = False
            self._pulse_timer.stop()
            self._deadline.stop()
            self.state_changed.emit(False, "TX level test could not start")
            self.error_received.emit(str(error))

    def stop(self) -> None:
        was_active = self._active
        self._active = False
        self._pulse_timer.stop()
        self._deadline.stop()
        if was_active:
            self.state_changed.emit(False, "TX level test stopped")

    def _send_beacon(self) -> None:
        try:
            self.beacon_service.transmit_test_beacon()
        except (RuntimeError, ValueError) as error:
            self.stop()
            self.error_received.emit(str(error))

    def _timeout(self) -> None:
        self.stop()
        self.state_changed.emit(False, "TX level test stopped after 12-second safety timeout")

    def _link_state_changed(self, state: str) -> None:
        self._link_state = state
        if self._active and state in {"connected", "linking"}:
            self.stop()
            self.error_received.emit("TX level test stopped because a station link became active")

    def _status_received(self, status) -> None:
        if not self._active:
            self._level_db = max(
                float(TX_TEST_MIN_GAIN_DB),
                min(float(TX_TEST_MAX_GAIN_DB), float(status.tx_gain_db)),
            )
            self.level_changed.emit(self._level_db)
        self.peak_changed.emit(float(status.tx_peak_dbfs))

    def _telemetry_state_changed(self, state: str) -> None:
        if self._active and state != "connected":
            self.stop()
            self.error_received.emit("TX level test stopped because Mercury telemetry disconnected")

"""Separate station configuration window prepared for additional setup tabs."""

from PySide6.QtCore import Qt, QSettings, Signal
from PySide6.QtGui import QCloseEvent, QHideEvent, QShowEvent
from PySide6.QtWidgets import QDialog, QTabWidget, QVBoxLayout

from application.location import to_maidenhead
from .audio_setup_page import AudioSetupPage
from .location_page import LocationPage
from .radio_page import RadioPage
from .reporting_setup_page import ReportingSetupPage
from .user_setup_page import UserSetupPage
from .weather_setup_page import WeatherSetupPage


class SetupWindow(QDialog):
    audio_diagnostics_changed = Signal(bool)

    def __init__(self, radio_service, beacon_service, location_service,
                 tx_level_service=None, psk_reporter_service=None,
                 weather_service=None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("MercurySkyPulse Setup")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setMinimumSize(760, 600)
        self.resize(940, 760)
        self.radio_service = radio_service
        self.beacon_service = beacon_service
        self.location_service = location_service
        self.tx_level_service = tx_level_service
        self.psk_reporter_service = psk_reporter_service
        self.weather_service = weather_service
        self._settings = QSettings()

        self.tabs = QTabWidget()
        self.radio_page = RadioPage()
        self.audio_page = AudioSetupPage()
        self.user_page = UserSetupPage()
        self.gps_page = LocationPage()
        self.reporting_page = ReportingSetupPage()
        self.weather_page = WeatherSetupPage()
        self.tabs.addTab(self.radio_page, "Radio")
        self.tabs.addTab(self.audio_page, "Audio")
        self.tabs.addTab(self.user_page, "User")
        self.tabs.addTab(self.gps_page, "GPS")
        self.tabs.addTab(self.reporting_page, "Reporting")
        self.tabs.addTab(self.weather_page, "Weather")
        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)

        self._connect_services()
        self.tabs.currentChanged.connect(self._update_audio_diagnostics)
        geometry = self._settings.value("setup/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        self.gps_page.set_selected_serial_port(location_service.saved_gps_port)

    def _connect_services(self) -> None:
        radio = self.radio_service
        self.radio_page.apply_requested.connect(radio.apply_radio)
        self.radio_page.refresh_devices_requested.connect(radio.station_devices.load)
        self.audio_page.apply_requested.connect(radio.apply_audio)
        radio.catalog_changed.connect(self.radio_page.set_catalog)
        radio.serial_ports_changed.connect(self.radio_page.set_serial_ports)
        radio.serial_ports_changed.connect(self.gps_page.set_serial_ports)
        radio.audio_inputs_changed.connect(
            lambda devices: self.audio_page.set_devices("capture_dev_list", devices)
        )
        radio.audio_outputs_changed.connect(
            lambda devices: self.audio_page.set_devices("playback_dev_list", devices)
        )
        radio.config_changed.connect(self.radio_page.set_config)
        radio.config_changed.connect(self.audio_page.set_config)
        radio.status_changed.connect(self.radio_page.set_status)
        radio.error_received.connect(self.radio_page.show_error)

        if self.tx_level_service:
            tx = self.tx_level_service
            self.radio_page.tx_level_requested.connect(tx.set_level)
            self.radio_page.tx_test_start_requested.connect(tx.start)
            self.radio_page.tx_test_stop_requested.connect(tx.stop)
            tx.level_changed.connect(self.radio_page.set_tx_gain)
            tx.peak_changed.connect(self.radio_page.set_tx_peak)
            tx.state_changed.connect(self.radio_page.set_tx_test_state)
            tx.error_received.connect(self.radio_page.show_error)

        beacon = self.beacon_service
        self.user_page.save_requested.connect(self._save_identity)
        beacon.config_changed.connect(self.user_page.set_config)
        beacon.error_received.connect(self.user_page.show_error)

        if self.psk_reporter_service:
            reporter = self.psk_reporter_service
            self.reporting_page.save_requested.connect(reporter.configure)
            reporter.config_changed.connect(self.reporting_page.set_config)
            reporter.state_changed.connect(self.reporting_page.set_state)
            reporter.error_received.connect(self.reporting_page.show_error)
            reporter.activity_logged.connect(self.reporting_page.append_activity)

        if self.weather_service:
            weather = self.weather_service
            self.weather_page.enabled_requested.connect(weather.configure)
            self.weather_page.position_preference_requested.connect(
                weather.set_use_station_position
            )
            self.weather_page.fetch_requested.connect(weather.fetch)
            weather.enabled_changed.connect(self.weather_page.set_enabled)
            weather.position_preference_changed.connect(
                self.weather_page.set_position_preference
            )
            weather.state_changed.connect(self.weather_page.set_state)
            weather.report_ready.connect(self.weather_page.set_report)
            weather.error_received.connect(self.weather_page.show_error)
        else:
            self.weather_page.setEnabled(False)

        location = self.location_service
        page = self.gps_page
        page.manual_requested.connect(location.set_manual)
        page.aprs_requested.connect(location.set_manual_aprs)
        page.gps_start_requested.connect(location.start_gps)
        page.gps_stop_requested.connect(location.stop_gps)
        page.retention_requested.connect(location.set_retention)
        page.export_requested.connect(location.export_history)
        location.current_changed.connect(self._position_changed)
        location.gps_state_changed.connect(page.set_gps_state)
        location.retention_changed.connect(page.set_retention)
        location.history_changed.connect(page.set_history_count)
        location.export_completed.connect(page.show_export_completed)
        location.error_received.connect(page.show_error)

    def set_audio_devices(self, kind: str, devices, selected: str = "") -> None:
        self.audio_page.set_devices(kind, devices, selected)

    def _save_identity(self, callsign: str, grid: str) -> None:
        config = self.beacon_service.config
        self.beacon_service.configure(
            callsign, grid, config.interval_minutes, config.include_gps
        )

    def _position_changed(self, location) -> None:
        self.gps_page.set_current(location)
        self.user_page.grid.setText(to_maidenhead(location.latitude, location.longitude))
        self.user_page.status.setText("GRID calculated from the current position; review and save")

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt API
        if self.tx_level_service:
            self.tx_level_service.stop()
        self._settings.setValue("setup/geometry", self.saveGeometry())
        self._settings.sync()
        super().closeEvent(event)

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        self._update_audio_diagnostics()

    def hideEvent(self, event: QHideEvent) -> None:  # noqa: N802 - Qt API
        self.audio_page.set_diagnostics_active(False)
        self.audio_diagnostics_changed.emit(False)
        super().hideEvent(event)

    def _update_audio_diagnostics(self, _index: int = -1) -> None:
        active = self.isVisible() and self.tabs.currentWidget() is self.audio_page
        self.audio_page.set_diagnostics_active(active)
        self.audio_diagnostics_changed.emit(active)

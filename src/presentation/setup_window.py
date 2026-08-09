"""Separate station configuration window prepared for additional setup tabs."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QTabWidget, QVBoxLayout

from application.location import to_maidenhead
from .audio_setup_page import AudioSetupPage
from .location_page import LocationPage
from .radio_page import RadioPage
from .user_setup_page import UserSetupPage


class SetupWindow(QDialog):
    def __init__(self, radio_service, beacon_service, location_service, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("MercurySkyPulse Setup")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setMinimumSize(760, 600)
        self.resize(940, 760)
        self.radio_service = radio_service
        self.beacon_service = beacon_service
        self.location_service = location_service

        self.tabs = QTabWidget()
        self.radio_page = RadioPage()
        self.audio_page = AudioSetupPage()
        self.user_page = UserSetupPage()
        self.gps_page = LocationPage()
        self.tabs.addTab(self.radio_page, "Radio")
        self.tabs.addTab(self.audio_page, "Audio")
        self.tabs.addTab(self.user_page, "User")
        self.tabs.addTab(self.gps_page, "GPS")
        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)

        self._connect_services()

    def _connect_services(self) -> None:
        radio = self.radio_service
        self.radio_page.apply_requested.connect(radio.apply_radio)
        self.radio_page.refresh_devices_requested.connect(radio.station_devices.load)
        self.radio_page.tune_level_requested.connect(radio.set_tune_level)
        self.radio_page.tune_start_requested.connect(radio.start_tune)
        self.radio_page.tune_stop_requested.connect(radio.stop_tune)
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
        radio.tune_level_changed.connect(self.radio_page.set_tune_level)
        radio.tune_state_changed.connect(self.radio_page.set_tune_state)
        radio.status_changed.connect(self.radio_page.set_status)
        radio.error_received.connect(self.radio_page.show_error)

        beacon = self.beacon_service
        self.user_page.save_requested.connect(self._save_identity)
        beacon.config_changed.connect(self.user_page.set_config)
        beacon.error_received.connect(self.user_page.show_error)

        location = self.location_service
        page = self.gps_page
        page.manual_requested.connect(location.set_manual)
        page.aprs_requested.connect(location.set_manual_aprs)
        page.gps_start_requested.connect(location.start_gps)
        page.gps_stop_requested.connect(location.stop_gps)
        page.share_requested.connect(location.share)
        page.retention_requested.connect(location.set_retention)
        page.export_requested.connect(location.export_history)
        location.current_changed.connect(self._position_changed)
        location.shared_received.connect(page.set_received)
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

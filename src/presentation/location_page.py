"""Manual, GPS, APRS, and explicit location-sharing UI."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QFormLayout,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from PySide6.QtCore import Signal


class LocationPage(QWidget):
    manual_requested = Signal(str, str)
    aprs_requested = Signal(str)
    gps_start_requested = Signal(str)
    gps_stop_requested = Signal()
    share_requested = Signal()
    retention_requested = Signal(bool)
    export_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        title = QLabel("Position & Location Sharing")
        title.setObjectName("PageTitle")
        root.addWidget(title)
        privacy = QLabel(
            "Your position stays local until you explicitly choose Share Location."
        )
        privacy.setObjectName("Muted")
        root.addWidget(privacy)

        manual_card = QFrame()
        manual_card.setObjectName("Card")
        manual_layout = QFormLayout(manual_card)
        self.latitude = QLineEdit()
        self.latitude.setPlaceholderText("40.7128")
        self.longitude = QLineEdit()
        self.longitude.setPlaceholderText("-74.0060")
        self.aprs = QLineEdit()
        self.aprs.setPlaceholderText("4042.77N/07400.36W")
        manual_layout.addRow("Latitude", self.latitude)
        manual_layout.addRow("Longitude", self.longitude)
        manual_layout.addRow("APRS coordinates", self.aprs)
        manual_buttons = QHBoxLayout()
        apply_decimal = QPushButton("Set Manual Position")
        apply_aprs = QPushButton("Use APRS Coordinates")
        manual_buttons.addWidget(apply_decimal)
        manual_buttons.addWidget(apply_aprs)
        manual_layout.addRow(manual_buttons)
        root.addWidget(manual_card)

        gps_card = QFrame()
        gps_card.setObjectName("Card")
        gps_layout = QFormLayout(gps_card)
        self.serial_port = QComboBox()
        self.serial_port.setEditable(True)
        self.serial_port.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.serial_port.addItem("System location (no serial receiver)", "")
        self.serial_port.lineEdit().setPlaceholderText(
            "Select a receiver or enter a port such as COM5"
        )
        gps_layout.addRow("GPS receiver", self.serial_port)
        gps_buttons = QHBoxLayout()
        start_gps = QPushButton("Start GPS")
        stop_gps = QPushButton("Stop GPS")
        self.gps_state = QLabel("GPS: stopped")
        self.gps_state.setObjectName("StatusPill")
        gps_buttons.addWidget(start_gps)
        gps_buttons.addWidget(stop_gps)
        gps_buttons.addWidget(self.gps_state)
        gps_layout.addRow(gps_buttons)
        history_row = QHBoxLayout()
        self.retain_history = QCheckBox("Retain GPS location updates")
        self.history_count = QLabel("0 retained points")
        export = QPushButton("Export Track…")
        history_row.addWidget(self.retain_history)
        history_row.addWidget(self.history_count)
        history_row.addWidget(export)
        gps_layout.addRow(history_row)
        root.addWidget(gps_card)

        current_card = QFrame()
        current_card.setObjectName("Card")
        current_layout = QVBoxLayout(current_card)
        self.current = QLabel("No local position")
        self.current.setObjectName("SectionTitle")
        self.received = QLabel("No shared station position received")
        self.received.setWordWrap(True)
        share = QPushButton("Share Location")
        share.setObjectName("PrimaryButton")
        current_layout.addWidget(self.current)
        current_layout.addWidget(self.received)
        current_layout.addWidget(share)
        root.addWidget(current_card)
        root.addStretch(1)

        apply_decimal.clicked.connect(
            lambda: self.manual_requested.emit(
                self.latitude.text(), self.longitude.text()
            )
        )
        apply_aprs.clicked.connect(lambda: self.aprs_requested.emit(self.aprs.text()))
        start_gps.clicked.connect(
            lambda: self.gps_start_requested.emit(self.selected_serial_port())
        )
        stop_gps.clicked.connect(self.gps_stop_requested)
        share.clicked.connect(self.share_requested)
        self.retain_history.toggled.connect(self.retention_requested)
        export.clicked.connect(self._choose_export)

    def set_serial_ports(self, ports) -> None:
        current = self.selected_serial_port()
        self.serial_port.blockSignals(True)
        self.serial_port.clear()
        self.serial_port.addItem("System location (no serial receiver)", "")
        for port in ports:
            self.serial_port.addItem(port.label, port.identifier)
        index = self.serial_port.findData(current)
        if index >= 0:
            self.serial_port.setCurrentIndex(index)
        elif current:
            self.serial_port.setEditText(current)
        self.serial_port.blockSignals(False)

    def selected_serial_port(self) -> str:
        index = self.serial_port.currentIndex()
        if index >= 0 and self.serial_port.currentText() == self.serial_port.itemText(index):
            identifier = self.serial_port.itemData(index)
            if identifier is not None:
                return str(identifier).strip()
        return self.serial_port.currentText().strip()

    def set_current(self, location) -> None:
        self.latitude.setText(f"{location.latitude:.6f}")
        self.longitude.setText(f"{location.longitude:.6f}")
        self.aprs.setText(location.aprs)
        accuracy = (
            "" if location.accuracy_m is None else f" · ±{location.accuracy_m:.0f} m"
        )
        self.current.setText(
            f"Current: {location.aprs} · {location.source}{accuracy}"
        )

    def set_received(self, location) -> None:
        self.received.setText(
            f"Station shared: {location.aprs} "
            f"({location.latitude:.6f}, {location.longitude:.6f})"
        )

    def set_gps_state(self, state: str) -> None:
        self.gps_state.setText(f"GPS: {state}")

    def set_retention(self, enabled: bool) -> None:
        self.retain_history.blockSignals(True)
        self.retain_history.setChecked(enabled)
        self.retain_history.blockSignals(False)

    def set_history_count(self, count: int) -> None:
        self.history_count.setText(
            f"{count} retained {'point' if count == 1 else 'points'}"
        )

    def show_export_completed(self, path: str) -> None:
        self.gps_state.setText(f"Exported: {Path(path).name}")
        self.gps_state.setToolTip(path)

    def _choose_export(self) -> None:
        path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export GPS track",
            "MercurySkyPulse-track.gpx",
            "GPX track (*.gpx);;Google Earth KML (*.kml);;"
            "GeoJSON (*.geojson);;CSV coordinates (*.csv)",
        )
        if not path:
            return
        destination = Path(path)
        if not destination.suffix:
            extensions = {
                "GPX track (*.gpx)": ".gpx",
                "Google Earth KML (*.kml)": ".kml",
                "GeoJSON (*.geojson)": ".geojson",
                "CSV coordinates (*.csv)": ".csv",
            }
            destination = destination.with_suffix(extensions.get(selected_filter, ".gpx"))
        self.export_requested.emit(str(destination))

    def show_error(self, message: str) -> None:
        self.gps_state.setText(message)
        self.gps_state.setToolTip(message)

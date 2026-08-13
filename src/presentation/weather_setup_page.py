"""Manual, consent-based internet weather preview."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)


class WeatherSetupPage(QWidget):
    enabled_requested = Signal(bool)
    position_preference_requested = Signal(bool)
    fetch_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        consent = QFrame()
        consent.setObjectName("Card")
        consent_layout = QVBoxLayout(consent)
        self.enabled = QCheckBox("Allow manual internet weather requests")
        detail = QLabel(
            "When you press Fetch or WX in Chat, MSP sends the selected station "
            "coordinates to wttr.in. MSP never uses IP location or fetches automatically."
        )
        detail.setWordWrap(True)
        detail.setObjectName("Muted")
        consent_layout.addWidget(self.enabled)
        self.use_station_position = QCheckBox(
            "Use current GPS/manual position when available"
        )
        self.use_station_position.setToolTip(
            "When off, weather always uses the geographic center of the saved GRID"
        )
        consent_layout.addWidget(self.use_station_position)
        consent_layout.addWidget(detail)
        root.addWidget(consent)

        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        self.fetch = QPushButton("Fetch Current Weather")
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText("No weather has been fetched.")
        self.preview.setMaximumHeight(130)
        self.status = QLabel("Internet access disabled")
        self.status.setObjectName("StatusPill")
        layout.addWidget(self.fetch)
        layout.addWidget(self.preview)
        layout.addWidget(self.status)
        root.addWidget(card)
        root.addStretch(1)

        self.enabled.toggled.connect(self.enabled_requested)
        self.use_station_position.toggled.connect(
            self.position_preference_requested
        )
        self.fetch.clicked.connect(self.fetch_requested)

    def set_enabled(self, enabled: bool) -> None:
        self.enabled.blockSignals(True)
        self.enabled.setChecked(enabled)
        self.enabled.blockSignals(False)
        self.fetch.setEnabled(enabled)

    def set_position_preference(self, enabled: bool) -> None:
        self.use_station_position.blockSignals(True)
        self.use_station_position.setChecked(enabled)
        self.use_station_position.blockSignals(False)

    def set_report(self, report) -> None:
        self.preview.setPlainText(report.text)

    def set_state(self, state: str) -> None:
        self.status.setText(state)

    def show_error(self, message: str) -> None:
        self.status.setText(message)
        self.status.setToolTip(message)

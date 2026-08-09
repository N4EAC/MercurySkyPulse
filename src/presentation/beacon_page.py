"""Periodic station beacon configuration and monitoring UI."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from application.beacon import INTERVALS_MINUTES


class BeaconPage(QWidget):
    configure_requested = Signal(int, bool)
    send_requested = Signal()
    disable_requested = Signal()

    def __init__(self, capabilities: tuple[str, ...], parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        title = QLabel("Station Beacon")
        title.setObjectName("PageTitle")
        root.addWidget(title)
        note = QLabel(
            "Periodic beacons use Mercury's connectionless KISS broadcast channel."
        )
        note.setObjectName("Muted")
        root.addWidget(note)

        card = QFrame()
        card.setObjectName("Card")
        form = QFormLayout(card)
        self.interval = QComboBox()
        for minutes in INTERVALS_MINUTES:
            label = "Off" if minutes == 0 else f"Every {minutes} minute{'s' if minutes != 1 else ''}"
            self.interval.addItem(label, minutes)
        self.include_gps = QCheckBox("Include latest GPS fix when available")
        form.addRow("Interval", self.interval)
        form.addRow("Optional GPS", self.include_gps)
        form.addRow("Capabilities", QLabel(", ".join(capabilities)))
        buttons = QHBoxLayout()
        save = QPushButton("Save Beacon")
        save.setObjectName("PrimaryButton")
        send = QPushButton("Send Now")
        stop = QPushButton("Turn Off")
        buttons.addWidget(save)
        buttons.addWidget(send)
        buttons.addWidget(stop)
        form.addRow(buttons)
        root.addWidget(card)

        status_card = QFrame()
        status_card.setObjectName("Card")
        status_layout = QVBoxLayout(status_card)
        self.state = QLabel("Beacon: off")
        self.state.setObjectName("StatusPill")
        self.received = QLabel("No station beacon received")
        self.received.setWordWrap(True)
        status_layout.addWidget(self.state)
        status_layout.addWidget(self.received)
        root.addWidget(status_card)
        root.addStretch(1)

        save.clicked.connect(self._configure)
        send.clicked.connect(self.send_requested)
        stop.clicked.connect(self.disable_requested)

    def set_config(self, config) -> None:
        index = self.interval.findData(config.interval_minutes)
        self.interval.setCurrentIndex(max(index, 0))
        self.include_gps.setChecked(config.include_gps)

    def set_state(self, state: str) -> None:
        self.state.setText(f"Beacon: {state}")

    def set_received(self, beacon) -> None:
        gps = ""
        if beacon.latitude is not None:
            gps = f" · GPS {beacon.latitude:.6f}, {beacon.longitude:.6f}"
        self.received.setText(
            f"{beacon.callsign} · {beacon.grid} · v{beacon.software_version} · "
            f"{', '.join(beacon.capabilities)}{gps}"
        )

    def show_error(self, message: str) -> None:
        self.state.setText(message)
        self.state.setToolTip(message)

    def _configure(self) -> None:
        self.configure_requested.emit(
            int(self.interval.currentData()),
            self.include_gps.isChecked(),
        )

"""Station ping request and modem-path result UI."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class PingPage(QWidget):
    ping_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        title = QLabel("Station Ping")
        title.setObjectName("PageTitle")
        root.addWidget(title)
        note = QLabel(
            "Ping measures the connected Mercury application path and exchanges modem telemetry."
        )
        note.setObjectName("Muted")
        root.addWidget(note)
        send = QPushButton("Ping Connected Station")
        send.setObjectName("PrimaryButton")
        root.addWidget(send)

        card = QFrame()
        card.setObjectName("Card")
        grid = QGridLayout(card)
        self.values = {}
        for row, (key, label) in enumerate(
            (
                ("rtt", "Round-trip time"),
                ("local_snr", "Local SNR"),
                ("remote_snr", "Remote SNR"),
                ("bitrate", "Remote bitrate"),
                ("mode", "Remote modem mode"),
            )
        ):
            grid.addWidget(QLabel(label), row, 0)
            value = QLabel("—")
            value.setObjectName("MetricValue")
            grid.addWidget(value, row, 1)
            self.values[key] = value
        root.addWidget(card)
        self.state = QLabel("Ping: idle")
        self.state.setObjectName("StatusPill")
        root.addWidget(self.state)
        root.addStretch(1)
        send.clicked.connect(self.ping_requested)

    def set_result(self, result) -> None:
        self.values["rtt"].setText(f"{result.rtt_ms:.1f} ms")
        self.values["local_snr"].setText(f"{result.local_snr_db:.1f} dB")
        self.values["remote_snr"].setText(f"{result.remote_snr_db:.1f} dB")
        self.values["bitrate"].setText(f"{result.bitrate_bps:,} bps")
        self.values["mode"].setText(result.modem_mode)

    def set_state(self, state: str) -> None:
        self.state.setText(f"Ping: {state}")

    def show_error(self, message: str) -> None:
        self.state.setText(message)
        self.state.setToolTip(message)

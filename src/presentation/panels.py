"""Station status and operational dock panels."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from application.modem import ModemStatus
from application.location import to_maidenhead


def _label(text: str, object_name: str | None = None) -> QLabel:
    widget = QLabel(text)
    if object_name:
        widget.setObjectName(object_name)
    return widget


class ActivityPanel(QWidget):
    log_added = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setMaximumBlockCount(1000)
        self.output.setPlaceholderText("Mercury process events will appear here.")
        self.output.setPlainText("Mercury SkyPulse initialized")
        layout.addWidget(self.output)

    def append_log(self, line: str) -> None:
        self.output.appendPlainText(line)
        self.log_added.emit(line)


class FrequencyPanel(QWidget):
    """Read-only radio frequency obtained from Mercury's Hamlib cache."""

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.addWidget(_label("Radio Frequency", "SectionTitle"))
        self.frequency = _label("— MHz", "MetricValue")
        self.frequency.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.frequency)
        self.detail = _label("Waiting for Mercury Hamlib telemetry", "Muted")
        self.detail.setWordWrap(True)
        self.detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.detail)
        layout.addStretch(1)

    def update_status(self, status: ModemStatus) -> None:
        if status.radio_frequency_hz is None:
            self.frequency.setText("— MHz")
            self.detail.setText("Frequency unavailable from Mercury")
            return
        self.frequency.setText(f"{status.radio_frequency_hz / 1_000_000:.6f} MHz")
        self.detail.setText("Read only · Mercury Hamlib")


class StationSummaryPanel(QWidget):
    """Compact, always-visible operating state without setup controls."""

    def __init__(self) -> None:
        super().__init__()
        layout = QGridLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        for column in range(5):
            layout.setColumnStretch(column, 1)
        self.values: dict[str, QLabel] = {}
        for index, (key, title, initial) in enumerate((
            ("engine", "Mercury", "Starting"),
            ("telemetry", "Telemetry", "Disconnected"),
            ("modem", "Modem", "Offline"),
            ("radio", "Radio", "Receiving"),
            ("snr", "SNR", "— dB"),
            ("bitrate", "Bitrate", "— bps"),
            ("frequency", "Frequency", "Unavailable"),
            ("datac_mode", "ARQ Payload", "Unavailable"),
            ("link", "ARQ", "Disconnected"),
            ("peer", "Station", "None"),
            ("transfer", "Transfer", "Idle"),
            ("grid", "GRID", "Unavailable"),
            ("next_beacon", "Next Beacon", "Manual"),
            ("reporting", "Reporting", "Disabled"),
            ("bbs", "BBS", "Ready"),
        )):
            item = QFrame()
            item.setObjectName("Card")
            item_layout = QVBoxLayout(item)
            item_layout.setContentsMargins(10, 5, 10, 5)
            heading = _label(title, "Muted")
            value = _label(initial, "StatusPill")
            value.setAlignment(Qt.AlignmentFlag.AlignCenter)
            item_layout.addWidget(heading)
            item_layout.addWidget(value)
            layout.addWidget(item, index // 5, index % 5)
            self.values[key] = value

    def set_value(self, key: str, value: str) -> None:
        if key in self.values:
            self.values[key].setText(value)

    def update_status(self, status: ModemStatus) -> None:
        self.set_value("modem", "Linked" if status.sync else "Listening")
        self.set_value("radio", "Transmitting" if status.direction == "tx" else "Receiving")
        self.set_value("snr", f"{status.snr_db:.1f} dB")
        self.set_value("bitrate", f"{status.bitrate_bps:,} bps")
        tx_mode = status.arq_tx_mode.strip().upper()
        rx_mode = status.arq_rx_mode.strip().upper()
        if tx_mode and rx_mode:
            payload_mode = tx_mode if tx_mode == rx_mode else f"TX {tx_mode} · RX {rx_mode}"
        elif tx_mode or rx_mode:
            payload_mode = f"TX {tx_mode}" if tx_mode else f"RX {rx_mode}"
        else:
            payload_mode = "Unavailable"
        self.set_value("datac_mode", payload_mode)
        self.values["datac_mode"].setToolTip(
            "Mercury-reported ARQ payload modes; control frames use Mercury's fixed control mode"
        )
        self.set_value(
            "frequency",
            "Unavailable" if status.radio_frequency_hz is None
            else f"{status.radio_frequency_hz / 1_000_000:.6f} MHz",
        )

    def set_engine_state(self, state: str) -> None:
        labels = {
            "missing": "Not found",
            "restart-wait": "Restarting",
            "restarting": "Restarting",
        }
        self.set_value("engine", labels.get(state, state.title()))

    def set_telemetry_state(self, state: str) -> None:
        self.set_value("telemetry", state.title())
        if state != "connected":
            self.set_value("modem", "Offline")

    def set_next_beacon(self, milliseconds: int | None) -> None:
        if milliseconds is None:
            self.set_value("next_beacon", "Manual")
            self._set_next_beacon_warning(False)
            return
        total_seconds = max(0, (milliseconds + 999) // 1000)
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        countdown = (
            f"{hours}:{minutes:02d}:{seconds:02d}"
            if hours else f"{minutes:02d}:{seconds:02d}"
        )
        self.set_value("next_beacon", countdown)
        self._set_next_beacon_warning(
            1 <= total_seconds <= 10 and total_seconds % 2 == 0
        )

    def set_next_beacon_paused(self) -> None:
        self.set_value("next_beacon", "Paused")
        self._set_next_beacon_warning(False)

    def _set_next_beacon_warning(self, visible: bool) -> None:
        value = self.values.get("next_beacon")
        if value is not None:
            value.setStyleSheet("color: #ff3131;" if visible else "")


class OperationalLocationPanel(QWidget):
    """Read current/received positions and explicitly share with the active peer."""

    share_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        self.peer = _label("Connected station: none", "StatusPill")
        self.current = _label("No valid local position", "SectionTitle")
        self.current.setWordWrap(True)
        self.received = _label("No position received from a station", "Muted")
        self.received.setWordWrap(True)
        self.share = QPushButton("Send Location to Connected Station")
        self.share.setObjectName("PrimaryButton")
        self.share.clicked.connect(self.share_requested)
        layout.addWidget(self.peer)
        layout.addWidget(self.current)
        layout.addWidget(self.received)
        layout.addWidget(self.share)
        layout.addStretch(1)

    def set_peer(self, peer: str) -> None:
        clean = peer.strip().upper()
        self.peer.setText(f"Connected station: {clean or 'none'}")

    def set_current(self, location) -> None:
        grid = to_maidenhead(location.latitude, location.longitude)
        accuracy = "" if location.accuracy_m is None else f" · ±{location.accuracy_m:.0f} m"
        self.current.setText(
            f"{grid} · {location.latitude:.6f}, {location.longitude:.6f}"
            f" · {location.source}{accuracy}"
        )

    def set_received(self, location) -> None:
        grid = to_maidenhead(location.latitude, location.longitude)
        self.received.setText(
            f"Received: {grid} · {location.latitude:.6f}, {location.longitude:.6f}"
        )

    def show_error(self, message: str) -> None:
        self.peer.setText(message)
        self.peer.setToolTip(message)


class ReportingActivityPanel(QWidget):
    """Operational PSK Reporter status and bounded activity projection."""

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        self.status = _label("PSK Reporter disabled", "StatusPill")
        self.activity = QPlainTextEdit()
        self.activity.setReadOnly(True)
        self.activity.setMaximumBlockCount(500)
        self.activity.setPlaceholderText("PSK Reporter activity will appear here.")
        layout.addWidget(self.status)
        layout.addWidget(self.activity, 1)

    def set_state(self, state: str) -> None:
        labels = {
            "enabled": "Enabled",
            "disabled": "Disabled",
            "uploading": "Uploading",
            "waiting-for-frequency": "Waiting for frequency",
        }
        if state.startswith("queued-"):
            self.status.setText(f"{state.partition('-')[2]} queued")
        elif state.startswith("sent-"):
            self.status.setText(f"{state.partition('-')[2]} sent")
        elif state.startswith("frequency-"):
            self.status.setText("Enabled · frequency available")
        else:
            self.status.setText(labels.get(state, state))

    def append_activity(self, message: str) -> None:
        self.activity.appendPlainText(message)

    def show_error(self, message: str) -> None:
        self.status.setText(message)
        self.status.setToolTip(message)

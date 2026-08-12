"""Dashboard, visualization, and dock panels."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from application.modem import ModemStatus


def _label(text: str, object_name: str | None = None) -> QLabel:
    widget = QLabel(text)
    if object_name:
        widget.setObjectName(object_name)
    return widget


class MetricCard(QFrame):
    def __init__(self, title: str, value: str, caption: str) -> None:
        super().__init__()
        self.setObjectName("Card")
        self.setMinimumSize(180, 112)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 15, 18, 15)
        layout.setSpacing(6)
        layout.addWidget(_label(title, "SectionTitle"))
        layout.addStretch(1)
        self.value_label = _label(value, "MetricValue")
        self.caption_label = _label(caption, "MetricCaption")
        layout.addWidget(self.value_label)
        layout.addWidget(self.caption_label)

    def set_metric(self, value: str, caption: str | None = None) -> None:
        self.value_label.setText(value)
        if caption is not None:
            self.caption_label.setText(caption)


class Dashboard(QWidget):
    """Central modem telemetry dashboard."""

    def __init__(self) -> None:
        super().__init__()
        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(28, 24, 28, 28)
        outer.setSpacing(16)

        heading = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(3)
        title_box.addWidget(_label("MercurySkyPulse", "PageTitle"))
        title_box.addWidget(_label("Supervised Mercury telemetry", "Muted"))
        heading.addLayout(title_box)
        heading.addStretch(1)
        self.state_pill = _label("STARTING", "StatusPill")
        self.state_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.addWidget(self.state_pill)
        outer.addLayout(heading)

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(16)
        self.engine_card = MetricCard("Mercury", "Starting", "Internal process")
        self.modem_card = MetricCard("Modem", "Offline", "Waiting for status")
        self.snr_card = MetricCard("SNR", "— dB", "Signal-to-noise ratio")
        self.bitrate_card = MetricCard("Bitrate", "— bps", "Current reported rate")
        self.frequency_card = MetricCard("Radio", "— MHz", "Frequency unavailable")
        for index, card in enumerate(
            (self.engine_card, self.modem_card, self.snr_card, self.bitrate_card,
             self.frequency_card)
        ):
            grid.addWidget(card, index // 2, index % 2)
        outer.addLayout(grid)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setWidget(content)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.scroll)

    def show_section(self, section: str) -> None:
        target = {
            "overview": self.engine_card,
            "signal": self.snr_card,
        }.get(section.casefold(), self.engine_card)
        self.scroll.ensureWidgetVisible(target, 20, 20)

    def set_engine_state(self, state: str) -> None:
        labels = {
            "missing": ("Not found", "Set MERCURY_EXECUTABLE or build the sibling checkout"),
            "starting": ("Starting", "Launching internal Mercury process"),
            "running": ("Running", "Process supervision active"),
            "crashed": ("Crashed", "Automatic restart enabled"),
            "restart-wait": ("Restarting", "Waiting before restart"),
            "restarting": ("Restarting", "Manual restart requested"),
            "stopping": ("Stopping", "Requesting clean shutdown"),
            "stopped": ("Stopped", "Mercury process is not running"),
        }
        value, caption = labels.get(state, (state.title(), "Mercury process"))
        self.engine_card.set_metric(value, caption)
        self.state_pill.setText(value.upper())

    def set_telemetry_state(self, state: str) -> None:
        if state != "connected":
            self.modem_card.set_metric("Offline", f"Telemetry: {state}")

    def update_status(self, status: ModemStatus) -> None:
        modem_state = "Linked" if status.sync else "Listening"
        direction = "Transmitting" if status.direction == "tx" else "Receiving"
        self.modem_card.set_metric(modem_state, direction)
        self.snr_card.set_metric(f"{status.snr_db:.1f} dB")
        self.bitrate_card.set_metric(f"{status.bitrate_bps:,} bps")
        if status.radio_frequency_hz is None:
            self.frequency_card.set_metric("— MHz", "Frequency unavailable")
        else:
            age = (status.radio_frequency_age_ms or 0) / 1000
            self.frequency_card.set_metric(
                f"{status.radio_frequency_hz / 1_000_000:.6f} MHz",
                f"Mercury Hamlib · {age:.1f} s old",
            )

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
        self.output.setPlainText("MercurySkyPulse initialized")
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
        age = (status.radio_frequency_age_ms or 0) / 1000
        self.detail.setText(f"Read only · Mercury Hamlib · {age:.1f} s old")


class NavigationPanel(QWidget):
    destination_requested = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(_label("Workspace", "SectionTitle"))
        self.navigation = QListWidget()
        self.navigation.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        for label in ("Overview", "Signal", "Activity", "Diagnostics"):
            QListWidgetItem(label, self.navigation)
        self.navigation.setCurrentRow(0)
        self.navigation.currentTextChanged.connect(self.destination_requested)
        layout.addWidget(self.navigation, 1)


def create_navigation_panel() -> NavigationPanel:
    return NavigationPanel()

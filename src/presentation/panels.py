"""Dashboard, visualization, and dock panels."""

from __future__ import annotations

from collections import deque
import math

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from application.modem import ModemStatus, SpectrumFrame


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


class SpectrumWidget(QWidget):
    """Lightweight live spectrum plot; stores only the latest frame."""

    def __init__(self) -> None:
        super().__init__()
        self._frame: SpectrumFrame | None = None
        self.setMinimumHeight(150)

    def set_frame(self, frame: SpectrumFrame) -> None:
        self._frame = frame
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(8, 8, -8, -8)
        painter.fillRect(rect, QColor(18, 24, 32, 150))

        grid_pen = QPen(QColor(110, 125, 145, 55), 1)
        painter.setPen(grid_pen)
        for division in range(1, 5):
            y = rect.top() + rect.height() * division / 5
            painter.drawLine(rect.left(), int(y), rect.right(), int(y))
        for division in range(1, 8):
            x = rect.left() + rect.width() * division / 8
            painter.drawLine(int(x), rect.top(), int(x), rect.bottom())

        if not self._frame or len(self._frame.bins_db) < 2:
            painter.setPen(QColor(150, 160, 175))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "Waiting for spectrum")
            return

        bins = self._frame.bins_db
        floor_db, ceiling_db = -120.0, 10.0
        path = QPainterPath()
        for index, value in enumerate(bins):
            normalized = max(0.0, min(1.0, (value - floor_db) / (ceiling_db - floor_db)))
            x = rect.left() + rect.width() * index / (len(bins) - 1)
            y = rect.bottom() - rect.height() * normalized
            point = QPointF(x, y)
            if index == 0:
                path.moveTo(point)
            else:
                path.lineTo(point)
        painter.setPen(QPen(QColor("#64a0ff"), 1.6))
        painter.drawPath(path)


def _heat_color(value: float) -> QColor:
    normalized = max(0.0, min(1.0, (value + 120.0) / 110.0))
    if normalized < 0.33:
        t = normalized / 0.33
        return QColor(int(8 + 20 * t), int(12 + 55 * t), int(28 + 105 * t))
    if normalized < 0.66:
        t = (normalized - 0.33) / 0.33
        return QColor(int(28 + 205 * t), int(67 + 80 * t), int(133 - 70 * t))
    t = (normalized - 0.66) / 0.34
    return QColor(233, int(147 + 100 * t), int(63 + 175 * t))


class WaterfallWidget(QWidget):
    """Bounded rolling spectrum history rendered as a waterfall."""

    def __init__(self, max_rows: int = 180) -> None:
        super().__init__()
        self._rows: deque[tuple[float, ...]] = deque(maxlen=max_rows)
        self.setMinimumHeight(180)

    def add_frame(self, frame: SpectrumFrame) -> None:
        if frame.bins_db:
            self._rows.append(frame.bins_db)
            self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        del event
        painter = QPainter(self)
        rect = self.rect().adjusted(8, 8, -8, -8)
        painter.fillRect(rect, QColor(12, 17, 24))
        if not self._rows:
            painter.setPen(QColor(150, 160, 175))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "Waiting for waterfall data")
            return

        rows = tuple(self._rows)
        row_height = max(1.0, rect.height() / len(rows))
        for row_index, bins in enumerate(reversed(rows)):
            y = rect.top() + row_index * row_height
            step = max(1, math.ceil(len(bins) / max(1, rect.width())))
            sampled = bins[::step]
            cell_width = rect.width() / max(1, len(sampled))
            for index, value in enumerate(sampled):
                painter.fillRect(
                    int(rect.left() + index * cell_width),
                    int(y),
                    max(1, math.ceil(cell_width)),
                    max(1, math.ceil(row_height)),
                    _heat_color(value),
                )


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
        self.spectrum_enabled = QCheckBox("Spectrum")
        self.spectrum_enabled.setChecked(True)
        self.waterfall_enabled = QCheckBox("Waterfall")
        self.waterfall_enabled.setChecked(True)
        heading.addWidget(self.spectrum_enabled)
        heading.addWidget(self.waterfall_enabled)
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
        for index, card in enumerate(
            (self.engine_card, self.modem_card, self.snr_card, self.bitrate_card)
        ):
            grid.addWidget(card, index // 2, index % 2)
        outer.addLayout(grid)

        self.spectrum_card = QFrame()
        self.spectrum_card.setObjectName("Card")
        spectrum_layout = QVBoxLayout(self.spectrum_card)
        spectrum_layout.setContentsMargins(14, 14, 14, 14)
        spectrum_layout.addWidget(_label("Spectrum", "SectionTitle"))
        self.spectrum = SpectrumWidget()
        spectrum_layout.addWidget(self.spectrum)
        outer.addWidget(self.spectrum_card)

        self.waterfall_card = QFrame()
        self.waterfall_card.setObjectName("Card")
        waterfall_layout = QVBoxLayout(self.waterfall_card)
        waterfall_layout.setContentsMargins(14, 14, 14, 14)
        waterfall_layout.addWidget(_label("Waterfall", "SectionTitle"))
        self.waterfall = WaterfallWidget()
        waterfall_layout.addWidget(self.waterfall)
        outer.addWidget(self.waterfall_card, 1)
        self.spectrum_enabled.toggled.connect(self.spectrum_card.setVisible)
        self.waterfall_enabled.toggled.connect(self.waterfall_card.setVisible)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)

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

    def update_spectrum(self, frame: SpectrumFrame) -> None:
        if self.spectrum_enabled.isChecked():
            self.spectrum.set_frame(frame)
        if self.waterfall_enabled.isChecked():
            self.waterfall.add_frame(frame)


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


def create_navigation_panel() -> QWidget:
    panel = QWidget()
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(10, 10, 10, 10)
    layout.addWidget(_label("Workspace", "SectionTitle"))
    navigation = QListWidget()
    navigation.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    for label in ("Overview", "Signal", "Waterfall", "Activity", "Diagnostics"):
        QListWidgetItem(label, navigation)
    navigation.setCurrentRow(0)
    layout.addWidget(navigation, 1)
    return panel


def create_inspector_panel() -> QWidget:
    panel = QWidget()
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(12, 12, 12, 12)
    layout.setSpacing(12)
    layout.addWidget(_label("Mercury integration", "SectionTitle"))
    layout.addWidget(_label("Read-only telemetry", "MetricValue"))
    layout.addWidget(
        _label(
            "The child process is supervised and restarts automatically after crashes. "
            "Messaging and data transport are not enabled.",
            "Muted",
        )
    )
    layout.addItem(QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))
    return panel

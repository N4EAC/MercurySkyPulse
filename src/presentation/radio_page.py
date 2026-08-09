"""Searchable Hamlib radio setup and bounded tune controls."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from application.radio import TUNE_MAX_DBFS, TUNE_MIN_DBFS


class RadioPage(QWidget):
    apply_requested = Signal(object, str, int)
    refresh_devices_requested = Signal()
    layout_changed = Signal()
    tune_level_requested = Signal(int)
    tune_start_requested = Signal()
    tune_stop_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("RadioPage")
        self._rigs = ()
        self._configured_model_id = None

        title = QLabel("Radio Station Setup")
        title.setObjectName("PageTitle")
        setup = QGroupBox("Radio and CAT / PTT through Mercury")
        setup_layout = QVBoxLayout(setup)
        self.direct_control = QCheckBox("Enable Mercury Hamlib CAT/PTT control")
        self.direct_control.toggled.connect(self._set_setup_enabled)
        setup_layout.addWidget(self.direct_control)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search radio manufacturer or model…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter_rigs)
        setup_layout.addWidget(self.search)
        self.radio_list = QListWidget()
        self.radio_list.setMinimumHeight(220)
        self.radio_list.setAlternatingRowColors(True)
        setup_layout.addWidget(self.radio_list, 1)
        form = QFormLayout()
        self.device = QComboBox()
        self.device.setEditable(True)
        self.device.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.device.lineEdit().setPlaceholderText(
            "Select a COM/USB port or enter serial device / ip:port"
        )
        form.addRow("CAT device/address", self.device)
        self.serial_speed = QComboBox()
        for speed in (0, 1200, 2400, 4800, 9600, 19200, 38400,
                      57600, 115200, 230400):
            self.serial_speed.addItem(
                "Hamlib model default" if speed == 0 else f"{speed} baud", speed
            )
        form.addRow("CAT serial speed", self.serial_speed)
        setup_layout.addLayout(form)
        self.apply_button = QPushButton("Save Radio and Restart Mercury")
        self.apply_button.clicked.connect(self._apply)
        self.refresh_devices = QPushButton("Refresh COM / USB Ports")
        self.refresh_devices.clicked.connect(self.refresh_devices_requested)
        setup_layout.addWidget(self.refresh_devices)

        tune = QGroupBox("Antenna Tuning Carrier")
        tune_layout = QVBoxLayout(tune)
        warning = QLabel(
            "Keys PTT and sends Mercury's 1000 Hz carrier. The application sends "
            "TUNE OFF after 12 seconds; Mercury retains its independent 60-second failsafe."
        )
        warning.setWordWrap(True)
        tune_layout.addWidget(warning)
        slider_row = QHBoxLayout()
        slider_row.addWidget(QLabel("Tune level"))
        self.tune_slider = QSlider(Qt.Orientation.Horizontal)
        self.tune_slider.setRange(TUNE_MIN_DBFS, TUNE_MAX_DBFS)
        self.tune_slider.setTickInterval(10)
        self.tune_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.tune_slider.valueChanged.connect(self._tune_value_changed)
        slider_row.addWidget(self.tune_slider, 1)
        self.tune_value = QLabel("-20 dBFS")
        self.tune_value.setMinimumWidth(70)
        slider_row.addWidget(self.tune_value)
        tune_layout.addLayout(slider_row)
        self.tune_button = QPushButton("Tune")
        self.tune_button.setCheckable(True)
        self.tune_button.toggled.connect(self._toggle_tune)
        tune_layout.addWidget(self.tune_button)

        self.status = QLabel("Radio catalog has not been loaded")
        self.status.setWordWrap(True)
        self.status.setStyleSheet("color: palette(mid);")

        self.content = QWidget()
        content_layout = QVBoxLayout(self.content)
        content_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        content_layout.addWidget(title)
        content_layout.addWidget(setup, 1)
        content_layout.addWidget(self.apply_button)
        content_layout.addWidget(tune)
        content_layout.addWidget(self.status)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll_area.setWidget(self.content)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.scroll_area)
        self._set_setup_enabled(False)

    def set_catalog(self, rigs) -> None:
        self._rigs = tuple(rigs)
        self._rebuild_list()
        self.status.setText(f"{len(self._rigs)} Hamlib radio models reported by Mercury")
        self.status.setStyleSheet("color: palette(mid);")

    def set_config(self, config) -> None:
        self._configured_model_id = config.model_id
        enabled = config.model_id is not None
        self.direct_control.setChecked(enabled)
        self.device.setCurrentText(config.device)
        speed_index = self.serial_speed.findData(config.serial_speed)
        self.serial_speed.setCurrentIndex(max(0, speed_index))
        for index in range(self.radio_list.count()):
            item = self.radio_list.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == config.model_id:
                self.radio_list.setCurrentItem(item)
                break

    def set_serial_ports(self, ports) -> None:
        current = self._combo_value(self.device)
        self.device.blockSignals(True)
        self.device.clear()
        self.device.addItem("Mercury / Hamlib default", "")
        for port in ports:
            self.device.addItem(port.label, port.identifier)
        self._select_combo_value(self.device, current)
        self.device.blockSignals(False)
        self._refresh_layout()

    def set_tune_level(self, level: int) -> None:
        self.tune_slider.blockSignals(True)
        self.tune_slider.setValue(level)
        self.tune_slider.blockSignals(False)
        self.tune_value.setText(f"{level} dBFS")

    def set_tune_state(self, active: bool, message: str) -> None:
        self.tune_button.blockSignals(True)
        self.tune_button.setChecked(active)
        self.tune_button.setText("Stop Tune" if active else "Tune")
        self.tune_button.blockSignals(False)
        self.status.setText(message)

    def set_status(self, message: str) -> None:
        self.status.setText(message)
        self.status.setStyleSheet("color: palette(mid);")

    def show_error(self, message: str) -> None:
        self.status.setText(message)
        self.status.setStyleSheet("color: #c33;")

    def _set_setup_enabled(self, enabled: bool) -> None:
        self.search.setEnabled(enabled)
        self.radio_list.setEnabled(enabled)
        self.device.setEnabled(enabled)
        self.serial_speed.setEnabled(enabled)

    @staticmethod
    def _editable_device_combo(placeholder: str) -> QComboBox:
        combo = QComboBox()
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        combo.lineEdit().setPlaceholderText(placeholder)
        combo.addItem("Mercury default", "")
        return combo

    @staticmethod
    def _select_combo_value(combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)
        else:
            combo.setCurrentText(value)

    @staticmethod
    def _combo_value(combo: QComboBox) -> str:
        index = combo.currentIndex()
        if index >= 0 and combo.currentText() == combo.itemText(index):
            return str(combo.itemData(index) or "")
        return combo.currentText()

    def _refresh_layout(self) -> None:
        self.content.layout().activate()
        self.content.adjustSize()
        self.layout_changed.emit()

    def _filter_rigs(self, value: str) -> None:
        needle = value.strip().casefold()
        for index in range(self.radio_list.count()):
            item = self.radio_list.item(index)
            item.setHidden(bool(needle) and needle not in item.text().casefold())

    def _rebuild_list(self) -> None:
        selected = self.radio_list.currentItem()
        selected_id = (
            selected.data(Qt.ItemDataRole.UserRole)
            if selected else self._configured_model_id
        )
        self.radio_list.clear()
        for rig in self._rigs:
            item = QListWidgetItem(f"{rig.manufacturer} — {rig.model}  [#{rig.model_id}, {rig.status}]")
            item.setData(Qt.ItemDataRole.UserRole, rig.model_id)
            item.setToolTip(f"{rig.macro} · Hamlib backend {rig.version}")
            self.radio_list.addItem(item)
            if rig.model_id == selected_id:
                self.radio_list.setCurrentItem(item)
        self._filter_rigs(self.search.text())

    def _apply(self) -> None:
        model_id = None
        if self.direct_control.isChecked():
            item = self.radio_list.currentItem()
            model_id = None if item is None else item.data(Qt.ItemDataRole.UserRole)
        self.apply_requested.emit(
            model_id, self._combo_value(self.device),
            int(self.serial_speed.currentData()),
        )

    def _tune_value_changed(self, value: int) -> None:
        self.tune_value.setText(f"{value} dBFS")
        self.tune_level_requested.emit(value)

    def _toggle_tune(self, active: bool) -> None:
        self.tune_button.setText("Stop Tune" if active else "Tune")
        if active:
            self.tune_start_requested.emit()
        else:
            self.tune_stop_requested.emit()

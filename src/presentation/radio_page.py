"""Searchable Mercury-owned Hamlib radio setup controls."""

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

class RadioPage(QWidget):
    apply_requested = Signal(object, str, int)
    refresh_devices_requested = Signal()
    layout_changed = Signal()
    tx_level_requested = Signal(float)
    tx_test_start_requested = Signal()
    tx_test_stop_requested = Signal()

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

        tx_test = QGroupBox("TX Level Test")
        tx_layout = QVBoxLayout(tx_test)
        tx_row = QHBoxLayout()
        tx_row.addWidget(QLabel("Modem TX gain"))
        self.tx_gain = QSlider(Qt.Orientation.Horizontal)
        self.tx_gain.setRange(-20, 0)
        self.tx_gain.setValue(-20)
        self.tx_gain.setTickInterval(5)
        self.tx_gain.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.tx_gain.valueChanged.connect(self._tx_gain_changed)
        tx_row.addWidget(self.tx_gain, 1)
        self.tx_gain_value = QLabel("-20 dB")
        self.tx_gain_value.setMinimumWidth(58)
        tx_row.addWidget(self.tx_gain_value)
        tx_layout.addLayout(tx_row)

        peak_row = QHBoxLayout()
        peak_row.addWidget(QLabel("Mercury TX peak"))
        self.tx_peak = QLabel("— dBFS")
        peak_row.addWidget(self.tx_peak)
        peak_row.addStretch(1)
        tx_layout.addLayout(peak_row)

        self.tx_test_button = QPushButton("Start TX Level Test")
        self.tx_test_button.setCheckable(True)
        self.tx_test_button.toggled.connect(self._toggle_tx_test)
        tx_layout.addWidget(self.tx_test_button)

        self.status = QLabel("Radio catalog has not been loaded")
        self.status.setWordWrap(True)
        self.status.setStyleSheet("color: palette(mid);")

        self.content = QWidget()
        content_layout = QVBoxLayout(self.content)
        content_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        content_layout.addWidget(title)
        content_layout.addWidget(setup, 1)
        content_layout.addWidget(self.apply_button)
        content_layout.addWidget(tx_test)
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

    def set_status(self, message: str) -> None:
        self.status.setText(message)
        self.status.setStyleSheet("color: palette(mid);")

    def set_tx_gain(self, level_db: float) -> None:
        if self.tx_gain.isSliderDown():
            return
        level = max(-20, min(0, round(float(level_db))))
        self.tx_gain.blockSignals(True)
        self.tx_gain.setValue(level)
        self.tx_gain.blockSignals(False)
        self.tx_gain_value.setText(f"{level} dB")

    def set_tx_peak(self, peak_dbfs: float) -> None:
        peak = float(peak_dbfs)
        self.tx_peak.setText("— dBFS" if peak <= -119.9 else f"{peak:.1f} dBFS")

    def set_tx_test_state(self, active: bool, message: str) -> None:
        self.tx_test_button.blockSignals(True)
        self.tx_test_button.setChecked(active)
        self.tx_test_button.setText(
            "Stop TX Level Test" if active else "Start TX Level Test"
        )
        self.tx_test_button.blockSignals(False)
        self.tx_gain.setEnabled(active or not self.tx_test_button.isChecked())
        self.status.setText(message)

    def show_error(self, message: str) -> None:
        self.status.setText(message)
        self.status.setStyleSheet("color: #c33;")

    def _set_setup_enabled(self, enabled: bool) -> None:
        self.search.setEnabled(enabled)
        self.radio_list.setEnabled(enabled)
        self.device.setEnabled(enabled)
        self.serial_speed.setEnabled(enabled)

    def _tx_gain_changed(self, value: int) -> None:
        self.tx_gain_value.setText(f"{value} dB")
        self.tx_level_requested.emit(float(value))

    def _toggle_tx_test(self, active: bool) -> None:
        self.tx_test_button.setText(
            "Stop TX Level Test" if active else "Start TX Level Test"
        )
        if active:
            self.tx_test_start_requested.emit()
        else:
            self.tx_test_stop_requested.emit()

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

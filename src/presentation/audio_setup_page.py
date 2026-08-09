"""Mercury-native capture and playback device configuration."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QFormLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class AudioSetupPage(QWidget):
    apply_requested = Signal(str, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        title = QLabel("Audio Devices")
        title.setObjectName("PageTitle")
        layout.addWidget(title)
        note = QLabel(
            "Device choices are reported by the running Mercury modem. Saved IDs "
            "remain editable when an interface is temporarily unavailable."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        self.input_device = self._combo("Mercury default input or device ID")
        self.output_device = self._combo("Mercury default output or device ID")
        form.addRow("Audio input (capture)", self.input_device)
        form.addRow("Audio output (playback)", self.output_device)
        layout.addLayout(form)
        save = QPushButton("Save Audio and Restart Mercury")
        save.setObjectName("PrimaryButton")
        save.clicked.connect(
            lambda: self.apply_requested.emit(
                self._value(self.input_device), self._value(self.output_device)
            )
        )
        layout.addWidget(save)
        layout.addStretch(1)

    def set_config(self, config) -> None:
        self.input_device.setCurrentText(config.input_device)
        self.output_device.setCurrentText(config.output_device)

    def set_devices(self, kind: str, devices, selected: str = "") -> None:
        combo = self.input_device if kind == "capture_dev_list" else self.output_device
        current = self._value(combo) or selected
        combo.clear()
        combo.addItem("Mercury default", "")
        for device in devices:
            combo.addItem(device.name, device.identifier)
        index = combo.findData(current)
        combo.setCurrentIndex(index) if index >= 0 else combo.setCurrentText(current)

    @staticmethod
    def _combo(placeholder: str) -> QComboBox:
        combo = QComboBox()
        combo.setEditable(True)
        combo.lineEdit().setPlaceholderText(placeholder)
        combo.addItem("Mercury default", "")
        return combo

    @staticmethod
    def _value(combo: QComboBox) -> str:
        index = combo.currentIndex()
        if index >= 0 and combo.currentText() == combo.itemText(index):
            return str(combo.itemData(index) or "")
        return combo.currentText().strip()

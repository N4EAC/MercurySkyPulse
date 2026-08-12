"""PSK Reporter opt-in configuration."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox, QFormLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton,
    QVBoxLayout, QWidget,
)


class ReportingSetupPage(QWidget):
    save_requested = Signal(bool, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        title = QLabel("Reception Reporting")
        title.setObjectName("PageTitle")
        layout.addWidget(title)
        self.enabled = QCheckBox("Enable PSK Reporter uploads")
        layout.addWidget(self.enabled)
        form = QFormLayout()
        self.frequency = QLabel("Unavailable")
        form.addRow("Radio frequency", self.frequency)
        self.antenna = QLineEdit()
        self.antenna.setMaxLength(254)
        self.antenna.setPlaceholderText("Receiving antenna")
        form.addRow("Antenna", self.antenna)
        layout.addLayout(form)
        save = QPushButton("Save Reporting Settings")
        save.setObjectName("PrimaryButton")
        save.clicked.connect(
            lambda: self.save_requested.emit(
                self.enabled.isChecked(), self.antenna.text()
            )
        )
        layout.addWidget(save)
        self.status = QLabel("PSK Reporter is disabled")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        log_label = QLabel("PSK Reporter Activity")
        log_label.setObjectName("SectionTitle")
        layout.addWidget(log_label)
        self.activity = QPlainTextEdit()
        self.activity.setReadOnly(True)
        self.activity.setMaximumBlockCount(500)
        self.activity.setMinimumHeight(190)
        self.activity.setPlaceholderText(
            "Queued reports, transmitted fields, and upload results will appear here."
        )
        layout.addWidget(self.activity, 1)

    def set_config(self, config) -> None:
        self.enabled.setChecked(config.enabled)
        self.antenna.setText(config.antenna)

    def set_state(self, state: str) -> None:
        labels = {
            "enabled": "PSK Reporter enabled; received beacons will be queued",
            "disabled": "PSK Reporter is disabled",
            "uploading": "Uploading queued reception reports",
            "waiting-for-frequency": "Waiting for a current frequency from Mercury",
        }
        if state.startswith("queued-"):
            count = state.partition("-")[2]
            self.status.setText(f"{count} reception report(s) queued")
        elif state.startswith("sent-"):
            count = state.partition("-")[2]
            self.status.setText(f"{count} reception report(s) sent")
        elif state.startswith("frequency-"):
            _, frequency, age = state.split("-", 2)
            self.frequency.setText(
                f"{int(frequency) / 1_000_000:.6f} MHz · {int(age) / 1000:.1f} s old"
            )
            self.status.setText("PSK Reporter enabled")
        else:
            self.status.setText(labels.get(state, state))

    def show_error(self, message: str) -> None:
        self.status.setText(message)

    def append_activity(self, message: str) -> None:
        self.activity.appendPlainText(message)

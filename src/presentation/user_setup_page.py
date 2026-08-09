"""Local station identity configuration."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFormLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget


class UserSetupPage(QWidget):
    save_requested = Signal(str, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        title = QLabel("Station User")
        title.setObjectName("PageTitle")
        layout.addWidget(title)
        form = QFormLayout()
        self.callsign = QLineEdit()
        self.callsign.setMaxLength(15)
        self.callsign.setPlaceholderText("N0CALL")
        self.grid = QLineEdit()
        self.grid.setMaxLength(8)
        self.grid.setPlaceholderText("FN30AS")
        form.addRow("Callsign", self.callsign)
        form.addRow("Maidenhead grid", self.grid)
        layout.addLayout(form)
        save = QPushButton("Save Station Identity")
        save.setObjectName("PrimaryButton")
        save.clicked.connect(lambda: self.save_requested.emit(
            self.callsign.text(), self.grid.text()
        ))
        layout.addWidget(save)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        layout.addStretch(1)

    def set_config(self, config) -> None:
        self.callsign.setText(config.callsign)
        self.grid.setText(config.grid)
        self.status.setText("Station identity saved")

    def show_error(self, message: str) -> None:
        self.status.setText(message)

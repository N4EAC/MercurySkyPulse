"""Local, offline operator-announcement preferences."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)


class AnnouncementSetupPage(QWidget):
    save_requested = Signal(bool, str)
    preview_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        title = QLabel("Voice Announcements")
        title.setObjectName("PageTitle")
        layout.addWidget(title)
        self.enabled = QCheckBox("Enable local voice announcements")
        layout.addWidget(self.enabled)
        form = QFormLayout()
        self.voice = QComboBox()
        self.voice.addItem("Male", "male")
        self.voice.addItem("Female", "female")
        form.addRow("Voice", self.voice)
        layout.addLayout(form)
        detail = QLabel(
            "Announcements play only on this computer through the default audio "
            "output. They are never transmitted over Mercury or RF."
        )
        detail.setObjectName("Muted")
        detail.setWordWrap(True)
        layout.addWidget(detail)
        save = QPushButton("Save Announcement Settings")
        save.setObjectName("PrimaryButton")
        save.clicked.connect(self._save)
        layout.addWidget(save)
        preview = QPushButton("Test Voice")
        preview.clicked.connect(self.preview_requested)
        layout.addWidget(preview)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        layout.addStretch(1)

    def _save(self) -> None:
        self.save_requested.emit(
            self.enabled.isChecked(), str(self.voice.currentData())
        )

    def set_config(self, enabled: bool, voice: str) -> None:
        self.enabled.setChecked(enabled)
        index = self.voice.findData(voice)
        self.voice.setCurrentIndex(max(index, 0))
        self.status.setText("Voice announcement settings saved")

    def show_error(self, message: str) -> None:
        self.status.setText(message)

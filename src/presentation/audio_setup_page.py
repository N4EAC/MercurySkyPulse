"""Mercury-native audio configuration and read-only path diagnostics."""

import math

from PySide6.QtCore import QElapsedTimer, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


NO_ENERGY_DBFS = -100.0
NO_ENERGY_WARNING_MS = 5_000


class AudioSetupPage(QWidget):
    apply_requested = Signal(str, str)
    voice_apply_requested = Signal(str, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        title = QLabel("Audio Devices")
        title.setObjectName("PageTitle")
        layout.addWidget(title)
        note = QLabel(
            "Mercury-reported device IDs are preferred. Local operating-system "
            "device names provide a fallback when Mercury omits a capture or "
            "playback list; saved IDs remain editable."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        self.input_device = self._combo("Mercury default input or device ID")
        self.output_device = self._combo("Mercury default output or device ID")
        form.addRow("Audio input (capture)", self.input_device)
        self.capture_id = QLabel("Native capture ID: Mercury default")
        self.capture_id.setWordWrap(True)
        self.capture_id.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow("Selected capture endpoint", self.capture_id)
        form.addRow("Audio output (playback)", self.output_device)
        self.playback_id = QLabel("Native playback ID: Mercury default")
        self.playback_id.setWordWrap(True)
        self.playback_id.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow("Selected playback endpoint", self.playback_id)
        layout.addLayout(form)
        save = QPushButton("Save Audio and Restart Mercury")
        save.setObjectName("PrimaryButton")
        save.clicked.connect(
            lambda: self.apply_requested.emit(
                self._value(self.input_device), self._value(self.output_device)
            )
        )
        layout.addWidget(save)

        voice = QGroupBox("Voice Message Audio")
        voice_form = QFormLayout(voice)
        self.voice_input_device = self._combo("System default microphone")
        self.voice_output_device = self._combo("System default speaker")
        voice_form.addRow("Voice microphone", self.voice_input_device)
        voice_form.addRow("Voice playback", self.voice_output_device)
        self.voice_save_button = QPushButton("Save Voice Devices")
        self.voice_save_button.clicked.connect(self._save_voice_devices)
        voice_form.addRow(self.voice_save_button)
        self.voice_save_status = QLabel()
        self.voice_save_status.setObjectName("Muted")
        voice_form.addRow("Saved configuration", self.voice_save_status)
        self.voice_input_level = QProgressBar()
        self.voice_input_level.setRange(0, 100)
        self.voice_input_level.setValue(0)
        self.voice_input_level.setFormat("Open this Audio tab to monitor the microphone")
        voice_form.addRow("Live microphone", self.voice_input_level)
        self.voice_active_devices = QLabel("Voice endpoints: system defaults")
        self.voice_active_devices.setWordWrap(True)
        self.voice_active_devices.setObjectName("Muted")
        voice_form.addRow(self.voice_active_devices)
        layout.addWidget(voice)

        diagnostics = QGroupBox("Live Audio Diagnostics")
        diagnostic_layout = QVBoxLayout(diagnostics)
        diagnostic_form = QFormLayout()
        diagnostic_form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )
        self.capture_meter = QProgressBar()
        self.capture_meter.setRange(0, 120)
        self.capture_meter.setValue(0)
        self.capture_meter.setFormat("Waiting for Mercury spectrum…")
        diagnostic_form.addRow("Capture energy", self.capture_meter)
        self.snr_meter = QProgressBar()
        self.snr_meter.setRange(0, 50)
        self.snr_meter.setValue(0)
        self.snr_meter.setFormat("Decoded SNR unavailable")
        diagnostic_form.addRow("Decoded signal SNR", self.snr_meter)
        diagnostic_layout.addLayout(diagnostic_form)
        self.capture_state = QLabel("Open this Audio tab to test the RX capture path")
        self.capture_state.setWordWrap(True)
        self.capture_state.setObjectName("Muted")
        self.capture_state.setMinimumHeight(self.capture_state.sizeHint().height())
        diagnostic_layout.addWidget(self.capture_state)
        self.spectrum_format = QLabel("RX spectrum format: waiting for telemetry")
        self.spectrum_format.setWordWrap(True)
        self.spectrum_format.setObjectName("Muted")
        self.spectrum_format.setMinimumHeight(self.spectrum_format.sizeHint().height())
        diagnostic_layout.addWidget(self.spectrum_format)
        layout.addWidget(diagnostics)
        layout.addStretch(1)

        self.input_device.currentIndexChanged.connect(self._update_identifiers)
        self.input_device.currentTextChanged.connect(self._update_identifiers)
        self.output_device.currentIndexChanged.connect(self._update_identifiers)
        self.output_device.currentTextChanged.connect(self._update_identifiers)
        self._diagnostic_timer = QTimer(self)
        self._diagnostic_timer.setInterval(1_000)
        self._diagnostic_timer.timeout.connect(self._check_capture_energy)
        self._energy_clock = QElapsedTimer()
        self._diagnostics_active = False
        self._frames_seen = False

    def set_config(self, config) -> None:
        self.input_device.setCurrentText(config.input_device)
        self.output_device.setCurrentText(config.output_device)
        self._update_identifiers()

    def set_devices(self, kind: str, devices, selected: str = "") -> None:
        combo = self.input_device if kind == "capture_dev_list" else self.output_device
        current = self._value(combo) or selected
        combo.clear()
        combo.addItem("Mercury default", "")
        for device in devices:
            combo.addItem(device.name, device.identifier)
        index = combo.findData(current)
        combo.setCurrentIndex(index) if index >= 0 else combo.setCurrentText(current)
        self._update_identifiers()

        voice_combo = (
            self.voice_input_device if kind == "capture_dev_list"
            else self.voice_output_device
        )
        voice_current = self._value(voice_combo)
        voice_combo.clear()
        voice_combo.addItem("System default", "")
        for device in devices:
            voice_combo.addItem(device.name, device.identifier)
        voice_index = voice_combo.findData(voice_current)
        if voice_index >= 0:
            voice_combo.setCurrentIndex(voice_index)
        elif voice_current:
            voice_combo.setEditText(voice_current)

    def set_voice_devices(self, input_device: str, output_device: str) -> None:
        self.voice_input_device.setCurrentText(input_device)
        self.voice_output_device.setCurrentText(output_device)

    def set_voice_input_level(self, dbfs: float) -> None:
        bounded = max(-100.0, min(0.0, float(dbfs)))
        self.voice_input_level.setValue(round(bounded + 100.0))
        self.voice_input_level.setFormat(f"{bounded:.1f} dBFS")

    def set_active_voice_devices(self, input_device: str, output_device: str) -> None:
        self.voice_active_devices.setText(
            f"Active microphone: {input_device or 'system default'} · "
            f"Playback: {output_device or 'system default'}"
        )

    def _save_voice_devices(self) -> None:
        self.voice_apply_requested.emit(
            self._value(self.voice_input_device), self._value(self.voice_output_device)
        )
        self.voice_save_status.setText("Voice audio devices saved")

    def set_diagnostics_active(self, active: bool) -> None:
        self._diagnostics_active = bool(active)
        self._frames_seen = False
        self._energy_clock.start()
        if active:
            self.capture_state.setText("Listening for Mercury RX spectrum telemetry…")
            self._diagnostic_timer.start()
        else:
            self._diagnostic_timer.stop()

    def update_spectrum(self, frame) -> None:
        if not self._diagnostics_active or not frame.bins_db:
            return
        finite = [value for value in frame.bins_db if math.isfinite(value)]
        if not finite:
            return
        peak_dbfs = max(-120.0, min(0.0, max(finite)))
        self._frames_seen = True
        self.capture_meter.setValue(round(peak_dbfs + 120.0))
        self.capture_meter.setFormat(f"{peak_dbfs:.1f} dBFS inferred peak")
        self.spectrum_format.setText(
            f"RX spectrum: {frame.sample_rate_hz:,} Hz · {len(frame.bins_db):,} bins"
        )
        if peak_dbfs > NO_ENERGY_DBFS:
            self._energy_clock.restart()
            self.capture_state.setText(
                "Capture energy detected — Mercury is receiving non-silent samples"
            )
        else:
            self._check_capture_energy()

    def update_status(self, status) -> None:
        snr = max(-20.0, min(30.0, float(status.snr_db)))
        self.snr_meter.setValue(round(snr + 20.0))
        self.snr_meter.setFormat(f"{status.snr_db:.1f} dB · {status.direction.upper()}")

    def _check_capture_energy(self) -> None:
        if not self._diagnostics_active or self._energy_clock.elapsed() < NO_ENERGY_WARNING_MS:
            return
        if not self._frames_seen:
            self.capture_state.setText(
                "No RX spectrum telemetry. Verify Mercury is running and telemetry is connected."
            )
        else:
            self.capture_state.setText(
                "No capture energy above -100 dBFS for 5 seconds. Verify the Windows "
                "recording endpoint, Virtual Cable direction, mute/privacy settings, "
                "and 48 kHz shared-mode format."
            )

    def _update_identifiers(self, *_args) -> None:
        self.capture_id.setText(
            f"{self.input_device.currentText() or 'Mercury default'}\n"
            f"Native ID: {self._value(self.input_device) or 'Mercury default'}"
        )
        self.playback_id.setText(
            f"{self.output_device.currentText() or 'Mercury default'}\n"
            f"Native ID: {self._value(self.output_device) or 'Mercury default'}"
        )

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

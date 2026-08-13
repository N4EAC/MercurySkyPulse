"""Cross-platform Qt capture and playback for short MSP voice messages."""

from __future__ import annotations

import math
from pathlib import Path
import struct
from tempfile import gettempdir
from uuid import uuid4

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtMultimedia import (
    QAudioFormat, QAudioInput, QAudioOutput, QAudioSource,
    QMediaCaptureSession, QMediaDevices,
    QMediaFormat, QMediaPlayer, QMediaRecorder,
)


class VoiceAudioEngine(QObject):
    recording_changed = Signal(bool, int)
    recording_ready = Signal(str, str)
    playback_changed = Signal(bool)
    error_received = Signal(str)
    input_level_changed = Signal(float)
    devices_configured = Signal(str, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._capture = QMediaCaptureSession(self)
        self._recorder = QMediaRecorder(self)
        self._input = QAudioInput(self)
        self._capture.setAudioInput(self._input)
        self._capture.setRecorder(self._recorder)
        self._output = QAudioOutput(self)
        self._player = QMediaPlayer(self)
        self._player.setAudioOutput(self._output)
        self._path = ""
        self._mime = "audio/mp4"
        self._level_source = None
        self._level_stream = None
        self._configured_input = ""
        self._configured_output = ""
        self._limit = QTimer(self)
        self._limit.setSingleShot(True)
        self._limit.setInterval(10_000)
        self._limit.timeout.connect(self.stop_recording)
        self._recorder.durationChanged.connect(
            lambda value: self.recording_changed.emit(True, min(10_000, int(value)))
        )
        self._recorder.recorderStateChanged.connect(self._recorder_state)
        self._recorder.errorOccurred.connect(
            lambda _error, message: self.error_received.emit(str(message))
        )
        self._player.playbackStateChanged.connect(
            lambda state: self.playback_changed.emit(
                state == QMediaPlayer.PlaybackState.PlayingState
            )
        )
        self._player.errorOccurred.connect(
            lambda _error, message: self.error_received.emit(str(message))
        )

    def configure(self, input_name: str, output_name: str) -> None:
        diagnostics_active = self._level_source is not None
        if diagnostics_active:
            self.stop_input_diagnostics()
        capture = self._find(QMediaDevices.audioInputs(), input_name)
        playback = self._find(QMediaDevices.audioOutputs(), output_name)
        capture = capture or QMediaDevices.defaultAudioInput()
        playback = playback or QMediaDevices.defaultAudioOutput()
        self._input.setDevice(capture)
        self._output.setDevice(playback)
        self._configured_input = capture.description()
        self._configured_output = playback.description()
        self.devices_configured.emit(self._configured_input, self._configured_output)
        if diagnostics_active:
            self.start_input_diagnostics()

    def start_input_diagnostics(self) -> None:
        self.stop_input_diagnostics()
        device = self._input.device()
        audio_format = device.preferredFormat()
        self._level_source = QAudioSource(device, audio_format, self)
        self._level_stream = self._level_source.start()
        if self._level_stream is None:
            self.error_received.emit("Could not open the selected voice microphone")
            return
        self._level_stream.readyRead.connect(
            lambda: self._read_input_level(audio_format)
        )

    def stop_input_diagnostics(self) -> None:
        if self._level_source is not None:
            self._level_source.stop()
            self._level_source.deleteLater()
        self._level_source = self._level_stream = None
        self.input_level_changed.emit(-100.0)

    def start_recording(self) -> None:
        if self._recorder.recorderState() == QMediaRecorder.RecorderState.RecordingState:
            return
        self.stop_input_diagnostics()
        media_format = QMediaFormat()
        media_format.setFileFormat(QMediaFormat.FileFormat.MPEG4)
        media_format.setAudioCodec(QMediaFormat.AudioCodec.AAC)
        if not media_format.isSupported(QMediaFormat.ConversionMode.Encode):
            media_format.setFileFormat(QMediaFormat.FileFormat.Ogg)
            media_format.setAudioCodec(QMediaFormat.AudioCodec.Vorbis)
            self._mime, suffix = "audio/ogg", ".ogg"
        else:
            self._mime, suffix = "audio/mp4", ".m4a"
        self._path = str(Path(gettempdir()) / f"msp-voice-{uuid4()}{suffix}")
        self._recorder.setMediaFormat(media_format)
        self._recorder.setAudioBitRate(12_000)
        self._recorder.setAudioSampleRate(8_000)
        self._recorder.setOutputLocation(QUrl.fromLocalFile(self._path))
        self._recorder.record()
        self._limit.start()

    def stop_recording(self) -> None:
        self._limit.stop()
        if self._recorder.recorderState() == QMediaRecorder.RecorderState.RecordingState:
            self._recorder.stop()

    def discard_recording(self) -> None:
        self.stop_recording()
        if self._path:
            Path(self._path).unlink(missing_ok=True)
        self._path = ""

    def play(self, path_value: str) -> None:
        self._player.setSource(QUrl.fromLocalFile(path_value))
        self._player.play()

    def stop_playback(self) -> None:
        self._player.stop()

    def _recorder_state(self, state) -> None:
        recording = state == QMediaRecorder.RecorderState.RecordingState
        self.recording_changed.emit(recording, int(self._recorder.duration()))
        if not recording and self._path and Path(self._path).is_file():
            self.recording_ready.emit(self._path, self._mime)

    def _read_input_level(self, audio_format: QAudioFormat) -> None:
        if self._level_stream is None:
            return
        data = bytes(self._level_stream.readAll())
        peak = self._normalized_peak(data, audio_format.sampleFormat())
        dbfs = -100.0 if peak <= 0 else max(-100.0, 20.0 * math.log10(peak))
        self.input_level_changed.emit(dbfs)

    @staticmethod
    def _normalized_peak(data: bytes, sample_format) -> float:
        if not data:
            return 0.0
        if sample_format == QAudioFormat.SampleFormat.UInt8:
            return max(abs(value - 128) / 128.0 for value in data)
        formats = {
            QAudioFormat.SampleFormat.Int16: ("h", 2, 32768.0),
            QAudioFormat.SampleFormat.Int32: ("i", 4, 2147483648.0),
            QAudioFormat.SampleFormat.Float: ("f", 4, 1.0),
        }
        details = formats.get(sample_format)
        if details is None:
            return 0.0
        code, width, scale = details
        usable = len(data) - len(data) % width
        if not usable:
            return 0.0
        return min(1.0, max(abs(value) / scale for (value,) in struct.iter_unpack("<" + code, data[:usable])))

    @staticmethod
    def _find(devices, name: str):
        clean = name.strip().casefold()
        if not clean:
            return None
        return next(
            (device for device in devices if device.description().strip().casefold() == clean),
            None,
        )

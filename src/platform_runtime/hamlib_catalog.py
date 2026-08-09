"""Enumerate the Hamlib models compiled into a selected Mercury executable."""

from __future__ import annotations

from pathlib import Path
import re

from PySide6.QtCore import QObject, QProcess, Signal

from application.radio import HamlibRig
from .mercury_process import discover_mercury_executable


RIG_LINE = re.compile(
    r"^\s*(\d+)\s{2,}(.+?)\s{2,}(.+?)\s{2,}(\S+)\s{2,}(\S+)\s{2,}(\S+)\s*$"
)
MAX_CATALOG_BYTES = 2 * 1024 * 1024


def parse_hamlib_catalog(output: str) -> tuple[HamlibRig, ...]:
    rigs = []
    seen = set()
    for line in output.splitlines():
        match = RIG_LINE.match(line)
        if not match:
            continue
        model_id = int(match.group(1))
        if model_id in seen:
            continue
        seen.add(model_id)
        rigs.append(HamlibRig(model_id, *(value.strip() for value in match.groups()[1:])))
    return tuple(rigs)


class MercuryHamlibCatalog(QObject):
    models_loaded = Signal(object)
    error_received = Signal(str)

    def __init__(self, executable: Path | None = None, parent=None) -> None:
        super().__init__(parent)
        self.executable = executable
        self._process: QProcess | None = None

    def load(self) -> None:
        if self._process is not None:
            return
        executable = discover_mercury_executable(self.executable)
        if executable is None:
            self.error_received.emit(
                "Mercury executable not found; Hamlib radio catalog is unavailable. "
                "Install Mercury beside the packaged application, set "
                "MERCURY_EXECUTABLE, or add Mercury to PATH"
            )
            return
        process = QProcess(self)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.finished.connect(self._finished)
        process.errorOccurred.connect(self._failed)
        self._process = process
        process.start(str(executable), ["-K"])

    def _finished(self, _exit_code: int, _exit_status) -> None:
        process, self._process = self._process, None
        if process is None:
            return
        raw = bytes(process.readAllStandardOutput())
        process.deleteLater()
        if len(raw) > MAX_CATALOG_BYTES:
            self.error_received.emit("Mercury Hamlib catalog exceeded the safety limit")
            return
        rigs = parse_hamlib_catalog(raw.decode("utf-8", errors="replace"))
        if not rigs:
            self.error_received.emit("Mercury returned no usable Hamlib radio models")
            return
        self.models_loaded.emit(rigs)

    def _failed(self, _error) -> None:
        process, self._process = self._process, None
        message = "Mercury could not enumerate its Hamlib radio models"
        if process is not None:
            message = f"{message}: {process.errorString()}"
            process.deleteLater()
        self.error_received.emit(message)

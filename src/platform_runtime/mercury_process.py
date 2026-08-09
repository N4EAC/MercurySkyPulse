"""Supervise Mercury as an independent child process."""

from __future__ import annotations

from dataclasses import dataclass, replace
import os
from pathlib import Path
import shutil
import sys

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal


@dataclass(frozen=True, slots=True)
class MercuryProcessConfig:
    managed: bool = True
    executable: Path | None = None
    ui_port: int = 10000
    radio_model: int | None = None
    radio_address: str | None = None
    radio_serial_speed: int = 0
    input_device: str | None = None
    output_device: str | None = None
    config_file: Path | None = None
    extra_arguments: tuple[str, ...] = ()
    restart_delays_ms: tuple[int, ...] = (1000, 2000, 4000, 8000, 15000, 30000)


def discover_mercury_executable(configured: Path | None = None) -> Path | None:
    """Find Mercury without modifying or building its checkout."""
    candidates: list[Path] = []
    if configured:
        candidates.append(configured.expanduser())
    if env_path := os.environ.get("MERCURY_EXECUTABLE"):
        candidates.append(Path(env_path).expanduser())

    sibling_name = "mercury.exe" if os.name == "nt" else "mercury"
    if getattr(sys, "frozen", False):
        application_directory = Path(sys.executable).resolve().parent
        candidates.append(application_directory / "mercury" / sibling_name)
        candidates.append(application_directory / sibling_name)

    project_root = Path(__file__).resolve().parents[2]
    candidates.append(project_root.parent / "mercury" / sibling_name)

    if path_match := shutil.which("mercury"):
        candidates.append(Path(path_match))

    for candidate in candidates:
        try:
            resolved = candidate.resolve(strict=True)
        except (OSError, RuntimeError):
            continue
        if resolved.is_file() and os.access(resolved, os.X_OK):
            return resolved
    return None


class MercuryProcessSupervisor(QObject):
    """Launch, monitor, and restart a Mercury process with bounded backoff."""

    state_changed = Signal(str)
    output_received = Signal(str)
    restart_scheduled = Signal(int)
    executable_resolved = Signal(str)

    def __init__(
        self,
        config: MercuryProcessConfig | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.config = config or MercuryProcessConfig()
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read_output)
        self.process.started.connect(self._on_started)
        self.process.errorOccurred.connect(self._on_error)
        self.process.finished.connect(self._on_finished)

        self._restart_timer = QTimer(self)
        self._restart_timer.setSingleShot(True)
        self._restart_timer.timeout.connect(self._spawn)
        self._stable_timer = QTimer(self)
        self._stable_timer.setSingleShot(True)
        self._stable_timer.setInterval(30000)
        self._stable_timer.timeout.connect(self._mark_stable)
        self._intended_running = False
        self._restart_attempt = 0
        self._resolved_executable: Path | None = None
        self._state = "stopped"

    @property
    def state(self) -> str:
        return self._state

    @property
    def executable(self) -> Path | None:
        return self._resolved_executable

    def start(self) -> None:
        if not self.config.managed:
            self._intended_running = False
            self._set_state("external")
            return
        self._intended_running = True
        self._restart_attempt = 0
        self._restart_timer.stop()
        if self.process.state() == QProcess.ProcessState.NotRunning:
            self._spawn()

    def restart_now(self) -> None:
        if not self.config.managed:
            self._set_state("external")
            return
        self._intended_running = True
        self._restart_attempt = 0
        self._restart_timer.stop()
        if self.process.state() == QProcess.ProcessState.NotRunning:
            self._spawn()
            return
        self._set_state("restarting")
        self.process.terminate()
        QTimer.singleShot(2500, self._kill_for_restart_if_needed)

    def configure_radio(self, model_id: int | None, address: str | None,
                        serial_speed: int = 0) -> None:
        """Apply documented Hamlib startup options and restart owned Mercury."""
        self.configure_station(
            model_id, address, serial_speed,
            self.config.input_device, self.config.output_device,
        )

    def configure_station(self, model_id: int | None, address: str | None,
                          serial_speed: int = 0,
                          input_device: str | None = None,
                          output_device: str | None = None) -> None:
        """Apply documented CAT/audio configuration and restart owned Mercury."""
        if not self.config.managed:
            raise RuntimeError("Cannot configure radio on an externally managed Mercury")
        if model_id is not None and model_id <= 0:
            raise ValueError("Hamlib radio model must be a positive integer")
        if address is not None and (
            len(address) > 512 or any(character in address for character in "\r\n\0")
        ):
            raise ValueError("Radio address is invalid")
        if serial_speed not in {0, 1200, 2400, 4800, 9600, 19200, 38400,
                                57600, 115200, 230400}:
            raise ValueError("Unsupported CAT serial speed")
        for label, device in (("Input", input_device), ("Output", output_device)):
            if device is not None and (
                len(device) > 512 or any(character in device for character in "\r\n\0")
            ):
                raise ValueError(f"{label} audio device is invalid")
        self.config = replace(
            self.config, radio_model=model_id, radio_address=address or None,
            radio_serial_speed=serial_speed,
            input_device=input_device or None, output_device=output_device or None,
        )
        self.restart_now()

    def stop(self) -> None:
        self._intended_running = False
        self._restart_timer.stop()
        self._stable_timer.stop()
        if self.process.state() == QProcess.ProcessState.NotRunning:
            self._set_state("stopped")
            return
        self._set_state("stopping")
        self.process.terminate()
        QTimer.singleShot(3000, self._kill_if_needed)

    def shutdown_blocking(self, timeout_ms: int = 5000) -> None:
        """Stop the owned child before the host event loop is destroyed."""
        self._intended_running = False
        self._restart_timer.stop()
        self._stable_timer.stop()
        if self.process.state() == QProcess.ProcessState.NotRunning:
            self._set_state("stopped")
            return
        self._set_state("stopping")
        self.process.terminate()
        if not self.process.waitForFinished(timeout_ms):
            self.process.kill()
            self.process.waitForFinished(2000)
        self._set_state("stopped")

    def _spawn(self) -> None:
        if not self._intended_running:
            return
        executable = discover_mercury_executable(self.config.executable)
        if executable is None:
            self._resolved_executable = None
            self._set_state("missing")
            return

        self._resolved_executable = executable
        self.executable_resolved.emit(str(executable))
        arguments = ["-G", "-U", str(self.config.ui_port)]
        if self.config.config_file is not None:
            self._write_application_config()
            arguments.extend(("-C", str(self.config.config_file)))
        if self.config.radio_model is not None:
            arguments.extend(("-R", str(self.config.radio_model)))
        if self.config.radio_address:
            arguments.extend(("-A", self.config.radio_address))
        arguments.extend(self.config.extra_arguments)
        environment = QProcessEnvironment.systemEnvironment()
        self.process.setProcessEnvironment(environment)
        self.process.setWorkingDirectory(str(executable.parent))
        self.process.setProgram(str(executable))
        self.process.setArguments(arguments)
        self._set_state("starting")
        self.process.start()

    def _write_application_config(self) -> None:
        path = self.config.config_file
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        contents = (
            "[main]\n"
            f"radio_serial_speed = {self.config.radio_serial_speed}\n"
            + (
                f'input_device = "{self._escape_ini(self.config.input_device)}"\n'
                if self.config.input_device else ""
            )
            + (
                f'output_device = "{self._escape_ini(self.config.output_device)}"\n'
                if self.config.output_device else ""
            )
        )
        temporary.write_text(contents, encoding="utf-8")
        temporary.replace(path)

    @staticmethod
    def _escape_ini(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')

    def _on_started(self) -> None:
        self._stable_timer.start()
        self._set_state("running")

    def _on_error(self, error: QProcess.ProcessError) -> None:
        self.output_received.emit(f"Mercury process error: {error.name}")

    def _on_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        self._stable_timer.stop()
        unexpected = self._intended_running and self._state != "restarting"
        if self._state == "restarting" and self._intended_running:
            self._spawn()
            return
        if not unexpected:
            self._set_state("stopped")
            return

        self._set_state("crashed")
        self.output_received.emit(
            f"Mercury exited unexpectedly (code={exit_code}, status={exit_status.name})"
        )
        self._schedule_restart()

    def _mark_stable(self) -> None:
        if self.process.state() == QProcess.ProcessState.Running:
            self._restart_attempt = 0

    def _schedule_restart(self) -> None:
        if not self._intended_running:
            return
        index = min(self._restart_attempt, len(self.config.restart_delays_ms) - 1)
        delay = self.config.restart_delays_ms[index]
        self._restart_attempt += 1
        self._set_state("restart-wait")
        self.restart_scheduled.emit(delay)
        self._restart_timer.start(delay)

    def _read_output(self) -> None:
        raw = bytes(self.process.readAllStandardOutput())
        text = raw.decode("utf-8", errors="replace")
        for line in text.splitlines():
            if line.strip():
                self.output_received.emit(line.rstrip())

    def _kill_if_needed(self) -> None:
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()

    def _kill_for_restart_if_needed(self) -> None:
        if self._state == "restarting" and self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()

    def _set_state(self, state: str) -> None:
        if state == self._state:
            return
        self._state = state
        self.state_changed.emit(state)

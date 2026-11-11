"""Operator-only RX harness using MSP diagnostics and the executable override.

No application composition root, station database, TNC client or broadcast client
is loaded. Importing this module never opens an audio device or starts Mercury.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
EXPECTED_SHA = "44886b01c98d0bc2f1845d6e912e885a04f6d4e3df4da646d760cfebce9ef430"
ARTIFACTS = ROOT / "run" / "coreaudio-254"
PORTS = (18300, 18301, 18100, 19000)


def utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def checked_binary() -> Path:
    from platform_runtime.mercury_process import discover_mercury_executable
    override = os.environ.get("MERCURY_EXECUTABLE", "")
    if not override:
        raise ValueError("MERCURY_EXECUTABLE must select the #254 patch binary")
    target = Path(override).resolve(strict=True)
    if discover_mercury_executable() != target:
        raise ValueError("Mercury override did not resolve exactly; refusing fallback")
    if hashlib.sha256(target.read_bytes()).hexdigest() != EXPECTED_SHA:
        raise ValueError("Binary differs from the validated #254 build; refusing launch")
    return target


def configuration(capture: str = "", playback: str = "") -> str:
    for value in (capture, playback):
        if value and not re.fullmatch(r"[0-9]{1,10}", value):
            raise ValueError("Select a current Mercury-enumerated CoreAudio device ID")
    return (
        "[main]\nui_enabled = true\nui_port = 19000\nui_protocol = ws\n"
        "waterfall_enabled = true\nsound_system = coreaudio\ncapture_channel = left\n"
        f'input_device = "{capture}"\noutput_device = "{playback}"\n'
        "arq_tcp_base_port = 18300\nbroadcast_tcp_port = 18100\n"
        "verbose = true\nfreedv_verbosity = 0\n"
        '[ptt]\nmethod = none\ndevice = ""\nhamlib_model = 0\n'
    )


def parse_devices(output: str) -> dict[str, list[tuple[str, str]]]:
    result = {"capture": [], "playback": []}
    kind = None
    for line in output.splitlines():
        if line.strip() in ("capture devices:", "playback devices:"):
            kind = line.split()[0]
        match = re.match(r"device: name: '(.*)'  id: '([0-9]+)'  default:", line)
        if kind and match:
            result[kind].append((match[1], match[2]))
    return result


def check_ports(ports=(*PORTS, 8300, 8301, 8100, 10000)) -> None:
    # Check normal MSP ports too: the operator must close the normal application.
    for port in ports:
        with socket.socket() as probe:
            # Allow departed connections in TIME_WAIT, not live listeners.
            # Never connect to a modem merely to check whether its port is busy.
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(("127.0.0.1", port))
            except OSError as error:
                raise ValueError(f"Port {port} is occupied; close other Mercury/MSP instances") from error


def collect(directory: Path) -> Path:
    directory = directory.resolve(strict=True)
    if directory.parent != ARTIFACTS.resolve() or not (directory / "manifest.json").is_file():
        raise ValueError("Select a session directory under run/coreaudio-254")
    errors = []
    starts = 0
    launches = 0
    for path in sorted(directory.glob("*.log")):
        for line in path.read_text(errors="replace").splitlines():
            if path.name == "activity.log" and "OPERATOR START" in line:
                starts += 1
            if path.name != "activity.log" and "Mercury engine initialised" in line:
                launches += 1
            if any(term in line for term in (
                "capture stalled", "capture reopen failed", "AudioDeviceStart",
                "PTT ON", "TX enabled", "FORCED STOP", "Launch refused:", "Process exit:",
            )):
                errors.append(f"{path.name}: {line}")
    report = directory / "RECEPTION_REPORT.txt"
    report.write_text(
        f"Collected {utc()}\nStart attempts: {starts}\n"
        f"Engine initializations: {launches}; restart initializations: {max(0, launches - 1)} (target: 10).\n"
        "Initialization is not a capture pass; review RX CONFIRMED and shutdown evidence.\n"
        "See activity.log for timed RX completion and each restart marker.\n"
        "Spectrum frames are evidence of published RX samples, not proof of RF decode.\n"
        "No automatic pass verdict: review logs and operator notes.\n"
        "Matching error lines may occur in both raw and Activity logs.\n\n"
        + "\n".join(errors) + "\n", encoding="utf-8",
    )
    archive = directory.with_name(directory.name + "-" + str(time.time_ns()) + ".zip")
    with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(directory.iterdir()):
            if path.is_file() and not path.is_symlink():
                bundle.write(path, path.name)
    return archive


def launch(window_ready=None) -> int:
    from PySide6.QtCore import QProcess, QTimer
    from PySide6.QtWidgets import QApplication, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget
    from platform_runtime.mercury_process import MercuryProcessConfig, MercuryProcessSupervisor
    from presentation.audio_setup_page import AudioSetupPage
    from presentation.themes import Appearance, apply_appearance
    from transport.mercury.telemetry import MercuryTelemetryClient

    binary = checked_binary()
    check_ports()
    session = ARTIFACTS / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    session.mkdir(parents=True, mode=0o700)
    ini = session / "receive-only.ini"
    ini.write_text(configuration())
    (session / "manifest.json").write_text(json.dumps({
        "created_utc": utc(), "binary": str(binary), "sha256": EXPECTED_SHA,
        "validation": "/Users/eduardo/.codex/automations/mercury-coreaudio-issue-254-first-fix/artifacts/VALIDATION.md",
        "mode": "CoreAudio left capture; PTT none; no TNC/KISS clients or automatic TX",
        "python": sys.executable, "macos": os.uname().release,
        "sw_vers": subprocess.check_output(["/usr/bin/sw_vers"], text=True),
    }, indent=2))

    class TestSupervisor(MercuryProcessSupervisor):
        def _schedule_restart(self):
            self._intended_running = False
            self.output_received.emit("Unexpected exit: automatic restart disabled for this test")

        def _read_output(self):
            data = bytes(self.process.readAllStandardOutput())
            if window.raw is not None:
                window.raw.write(data)
                window.raw.flush()
            window.pending += data
            while b"\n" in window.pending:
                line, window.pending = window.pending.split(b"\n", 1)
                self.output_received.emit(line.decode("utf-8", errors="replace").rstrip())

        def _spawn(self):
            # Refuse fallback or modified binary on every restart, not just launch.
            try:
                checked_binary()
                check_ports()
                # Regenerate from the explicit selections; ignore any later
                # edits to this test INI so CAT/PTT cannot be re-enabled.
                ini.write_text(configuration(*window.selected))
            except (OSError, ValueError) as error:
                self.output_received.emit(f"Launch refused: {error}")
                self._intended_running = False
                window.start_button.setEnabled(window.cycle < 0)
                return
            super()._spawn()

    class Window(QWidget):
        def __init__(self):
            super().__init__()
            self.raw = None
            self.pending = b""
            self.cycle = -1
            self.attempt = -1
            self.confirmed = set()
            self.stopping = False
            self.closing = False
            self.after_stop = None
            self.frames = 0
            self.last_frame = 0.0
            self.status = None
            self.phase_start = None
            self.initial_complete = False
            self.selected = ("", "")
            self.run_start = 0.0
            self.setWindowTitle("MSP — CoreAudio #254 receive-only test")
            self.resize(1000, 900)
            layout = QVBoxLayout(self)
            note = QLabel("RX ONLY · CAT/PTT disabled · No beacons, calls, replies or file traffic\n"
                          "Select current USB capture AND playback devices; capture channel is LEFT.\n"
                          f"Mercury: {binary}\nLogs: {session}")
            note.setWordWrap(True)
            layout.addWidget(note)
            self.audio = AudioSetupPage()
            # Reuse MSP's diagnostics without its normal settings or TX services.
            self.audio.input_device.setEditable(False)
            self.audio.output_device.setEditable(False)
            self.start_button = self.audio.findChild(QPushButton, "PrimaryButton")
            self.start_button.setText("Start selected devices — receive only")
            self.audio.apply_requested.connect(self.start_selected)
            self.audio.refresh_requested.connect(self.enumerate_devices)
            layout.addWidget(self.audio)
            self.progress = QLabel("1. Refresh Audio Devices. 2. Select both USB endpoints. 3. Start.")
            layout.addWidget(self.progress)
            self.begin = QPushButton("Begin 10-minute reception after permission is granted")
            self.begin.clicked.connect(self.begin_reception)
            layout.addWidget(self.begin)
            self.retest = QPushButton("Begin restart-only retest (previous reception already reviewed)")
            self.retest.clicked.connect(self.begin_retest)
            layout.addWidget(self.retest)
            self.restart = QPushButton("Controlled restart (0 / 10)")
            self.restart.setEnabled(False)
            self.restart.clicked.connect(self.restart_selected)
            layout.addWidget(self.restart)
            stop = QPushButton("Stop Mercury")
            stop.clicked.connect(self.stop_mercury)
            layout.addWidget(stop)
            self.activity = QPlainTextEdit()
            self.activity.setReadOnly(True)
            self.activity.setMaximumBlockCount(2000)
            layout.addWidget(QLabel("Activity — complete output is saved on disk"))
            layout.addWidget(self.activity)
            self.engine = TestSupervisor(MercuryProcessConfig(
                ui_port=19000, config_file=None, extra_arguments=("-C", str(ini)),
            ))
            self.engine.output_received.connect(self.log)
            self.engine.executable_resolved.connect(lambda path: self.log(f"ACTUAL Mercury executable: {path}"))
            self.engine.state_changed.connect(lambda state: self.log(f"Mercury state: {state}"))
            self.engine.process.started.connect(self.process_started)
            self.engine.process.errorOccurred.connect(lambda _: self.start_button.setEnabled(self.cycle < 0))
            self.engine.process.finished.connect(
                lambda code, state: self.log(f"Process exit: code={code} status={state.name}")
            )
            self.telemetry = MercuryTelemetryClient("ws://127.0.0.1:19000/websocket")
            self.telemetry.set_spectrum_processing_enabled(True)
            self.telemetry.spectrum_received.connect(self.on_spectrum)
            self.telemetry.status_received.connect(self.on_status)
            self.telemetry.state_changed.connect(lambda state: self.log(f"Telemetry: {state}"))
            self.telemetry.error_received.connect(self.log)
            self.enumerator = QProcess(self)
            self.enumerator.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
            self.enumerator.finished.connect(self.devices_ready)
            self.enumerator.errorOccurred.connect(lambda _: self.log("Device listing failed: " + self.enumerator.errorString()))
            self.enum_timeout = QTimer(self)
            self.enum_timeout.setSingleShot(True)
            self.enum_timeout.timeout.connect(self.enumerator.kill)
            self.timer = QTimer(self)
            self.timer.setInterval(5000)
            self.timer.timeout.connect(self.snapshot)
            self.timer.start()
            self.stop_timer = QTimer(self)
            self.stop_timer.setInterval(100)
            self.stop_timer.timeout.connect(self.poll_stop)
            self.sampler = QProcess(self)
            self.sampler.finished.connect(lambda code, _: self.log(f"Shutdown stack sample exit: {code}"))
            self.log(f"Prepared RX test. Validated binary SHA256: {EXPECTED_SHA}")

        def log(self, line):
            text = f"{utc()} | {line}"
            self.activity.appendPlainText(text)
            with (session / "activity.log").open("a", encoding="utf-8") as output:
                output.write(text + "\n")

        def enumerate_devices(self):
            if self.cycle >= 0:
                self.log("Start a new test window to refresh or change devices; preserve this run's selections")
                return
            if self.engine.process.state() != QProcess.NotRunning:
                self.log("Stop Mercury before refreshing the device list")
                return
            if self.enumerator.state() != QProcess.NotRunning:
                return
            try:
                checked_binary()
            except (OSError, ValueError) as error:
                self.log(str(error))
                return
            self.enumerator.start(str(binary), ["-C", str(ini), "-z"])
            self.enum_timeout.start(15000)

        def devices_ready(self, code, _status):
            self.enum_timeout.stop()
            output = bytes(self.enumerator.readAllStandardOutput()).decode(errors="replace")
            self.log("DEVICE ENUMERATION\n" + output)
            if code != 0:
                return
            for kind, combo in (("capture", self.audio.input_device), ("playback", self.audio.output_device)):
                combo.clear()
                combo.addItem("Select current USB " + kind, "")
                for name, identifier in parse_devices(output)[kind]:
                    combo.addItem(f"{name} [ID {identifier}]", identifier)

        def start_selected(self, capture, playback):
            if self.engine.process.state() != QProcess.NotRunning:
                self.log("Stop the current run before starting another")
                return
            if not capture or not playback:
                self.log("Select both current USB devices first; default devices are not used")
                return
            if self.cycle >= 0:
                self.log("Use Controlled restart, or open a new test session for new devices")
                return
            ini.write_text(configuration(capture, playback))
            self.selected = (capture, playback)
            self.audio.input_device.setEnabled(False)
            self.audio.output_device.setEnabled(False)
            self.start_button.setEnabled(False)
            self.start_run()

        def start_run(self):
            if self.stopping or self.engine.process.state() != QProcess.NotRunning:
                return
            self.attempt += 1
            self.frames = 0
            self.last_frame = 0.0
            self.status = None
            self.run_start = time.monotonic()
            if self.raw:
                self.raw.close()
            self.raw = (session / f"mercury-{self.attempt:02d}.log").open("ab")
            self.log(f"OPERATOR START attempt={self.attempt}; config={ini.read_text()}")
            self.audio.set_diagnostics_active(True)
            self.engine.start()
            if self.engine.process.state() != QProcess.NotRunning:
                self.telemetry.start()

        def process_started(self):
            self.cycle += 1
            self.run_start = time.monotonic()
            self.log(f"PROCESS STARTED cycle={self.cycle} attempt={self.attempt}; awaiting fresh capture")
            self.restart.setText(f"Controlled restart ({max(0, self.cycle)} / 10 launched)")

        def begin_retest(self):
            if self.cycle != 0 or self.frames == 0 or self.engine.process.state() != QProcess.Running:
                self.log("Start initial Mercury and wait for fresh spectrum before restart-only retest")
                return
            self.initial_complete = True
            self.begin.setEnabled(False)
            self.retest.setEnabled(False)
            self.log("OPERATOR selected restart-only retest; no new ten-minute pass claimed")

        def begin_reception(self):
            if self.cycle != 0 or self.engine.process.state() != QProcess.Running:
                self.log("Start the initial capture run first")
                return
            self.phase_start = time.monotonic()
            self.initial_complete = False
            self.log("OPERATOR began ten-minute reception observation")
            self.begin.setEnabled(False)

        def on_spectrum(self, frame):
            self.frames += 1
            self.last_frame = time.monotonic()
            self.audio.update_spectrum(frame)

        def on_status(self, status):
            self.status = asdict(status)
            self.audio.update_status(status)

        def snapshot(self):
            if self.cycle < 0:
                return
            self.log("SNAPSHOT " + json.dumps({"cycle": self.cycle, "spectrum_frames": self.frames,
                                               "status": self.status}, allow_nan=False))
            running = self.engine.process.state() == QProcess.Running
            observed = (running and self.frames > 0 and time.monotonic() - self.last_frame < 5
                        and time.monotonic() - self.run_start >= 30)
            if observed and not self.stopping and self.cycle not in self.confirmed:
                self.confirmed.add(self.cycle)
                self.log(f"RX CONFIRMED cycle={self.cycle}; samples observed over run; frames={self.frames}")
            self.restart.setEnabled(not self.stopping and self.initial_complete and self.cycle < 10
                                    and (observed or self.engine.process.state() == QProcess.NotRunning))
            if self.initial_complete:
                self.progress.setText(f"Restarts launched: {max(0, self.cycle)}/10; RX observed: "
                                      f"{len(self.confirmed - {0})}/10; frames this run: {self.frames}")
            if self.phase_start is not None and not self.initial_complete:
                if self.engine.process.state() != QProcess.Running:
                    self.phase_start = None
                    self.begin.setEnabled(True)
                    self.log("Observation interrupted; ten-minute completion NOT recorded")
                    return
                elapsed = int(time.monotonic() - self.phase_start)
                self.progress.setText(f"Reception observation: {min(elapsed, 600)} / 600 seconds; spectrum frames: {self.frames}")
                if elapsed >= 600:
                    self.initial_complete = True
                    self.restart.setEnabled(True)
                    self.log("Ten-minute observation completed (not an automatic pass). Begin ten operator restarts.")

        def restart_selected(self):
            if not self.initial_complete or self.cycle >= 10:
                return
            if self.stopping:
                return
            if self.engine.process.state() == QProcess.Running and (self.frames == 0 or time.monotonic() - self.run_start < 30):
                return
            self.stop_mercury(self.start_run)
            self.restart.setEnabled(False)

        def stop_mercury(self, callback=None):
            if self.stopping:
                return
            self.stopping = True
            self.after_stop = callback if callable(callback) else None
            if self.phase_start is not None and not self.initial_complete:
                self.phase_start = None
                self.log("Ten-minute observation interrupted by operator stop")
            self.telemetry.stop()
            self.audio.set_diagnostics_active(False)
            self.engine._intended_running = False
            self.engine._restart_timer.stop()
            self.engine._stable_timer.stop()
            self.stop_started = time.monotonic()
            self.terminated = False
            self.sampled = False
            self.killed = False
            self.log("OPERATOR STOP requested; event loop remains active for WebSocket close")
            self.stop_timer.start()

        def poll_stop(self):
            elapsed = time.monotonic() - self.stop_started
            process = self.engine.process
            self.progress.setText(f"Stopping owned Mercury — {int(elapsed)} seconds; please wait")
            if elapsed >= 8 and self.sampler.state() != QProcess.NotRunning:
                self.log("Stack sampler exceeded its budget; stopping diagnostic process")
                self.sampler.kill()
            if process.state() != QProcess.NotRunning:
                if elapsed >= 0.5 and not self.terminated:
                    self.terminated = True
                    self.log(f"Sending termination to owned Mercury pid={process.processId()}")
                    process.terminate()
                if elapsed >= 3.5 and not self.sampled:
                    self.sampled = True
                    target = session / f"shutdown-{self.attempt:02d}.sample.txt"
                    self.log(f"Shutdown still pending; collecting one-second stack sample: {target}")
                    self.sampler.start("/usr/bin/sample", [str(process.processId()), "1", "1", "-file", str(target)])
                if elapsed >= 10.5 and not self.killed:
                    self.killed = True
                    self.log("FORCED STOP: Mercury did not exit within 10 seconds after termination")
                    process.kill()
                return
            if self.sampler.state() != QProcess.NotRunning:
                return
            self.stop_timer.stop()
            if self.engine.process.isOpen():
                self.engine._read_output()
            if self.pending:
                self.log(self.pending.decode(errors="replace"))
                self.pending = b""
            if self.raw:
                self.raw.close()
                self.raw = None
            self.log("OPERATOR STOP complete; review process exit and raw output")
            self.stopping = False
            callback, self.after_stop = self.after_stop, None
            if self.closing:
                self.close()
            elif callback:
                callback()

        def closeEvent(self, event):
            if self.stopping or self.engine.process.state() != QProcess.NotRunning:
                self.closing = True
                self.stop_mercury()
                event.ignore()
                return
            self.timer.stop()
            self.enumerator.kill()
            self.enumerator.waitForFinished(2000)
            if self.raw:
                self.raw.close()
                self.raw = None
            self.log("Test window closed. Collect this session with --collect " + str(session))
            event.accept()

    app = QApplication.instance() or QApplication(sys.argv)
    app.setOrganizationName("MSPCoreAudio254Test")
    app.setApplicationName("MSPCoreAudio254Test")
    apply_appearance(app, Appearance.system())
    window = Window()
    if window_ready is not None:
        window_ready(window)
        return 0
    window.show()
    return app.exec()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verify binary/config only; do not start Mercury or GUI")
    parser.add_argument("--collect", type=Path, help="Collect a closed test session into a ZIP")
    args = parser.parse_args()
    if args.collect:
        print(collect(args.collect))
    elif args.check:
        print("Verified executable:", checked_binary())
        print("SHA256:", EXPECTED_SHA)
        print(configuration())
    else:
        return launch()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

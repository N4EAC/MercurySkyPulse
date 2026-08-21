"""Process discovery and crash-restart behavior tests."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QEventLoop, QProcess, QTimer
from PySide6.QtWidgets import QApplication

from platform_runtime.mercury_process import (
    MercuryProcessConfig,
    MercuryProcessSupervisor,
    discover_mercury_executable,
)


class MercurySupervisorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication(["supervisor-test"])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_discovers_configured_executable(self) -> None:
        found = discover_mercury_executable(Path(sys.executable))
        self.assertEqual(Path(sys.executable).resolve(), found)

    def test_frozen_application_discovers_side_by_side_mercury(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            application = Path(directory) / "MercurySkyPulse.exe"
            application.touch()
            mercury_name = "mercury.exe" if os.name == "nt" else "mercury"
            mercury = Path(directory) / "mercury" / mercury_name
            mercury.parent.mkdir()
            mercury.touch()
            mercury.chmod(0o755)
            with (
                patch.dict(os.environ, {}, clear=True),
                patch.object(sys, "frozen", True, create=True),
                patch.object(sys, "executable", str(application)),
            ):
                found = discover_mercury_executable()
            self.assertEqual(mercury.resolve(), found)

    def test_frozen_application_discovers_pyinstaller_bundled_mercury(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle_root = Path(directory) / "Contents" / "Frameworks"
            mercury_name = "mercury.exe" if os.name == "nt" else "mercury"
            mercury = bundle_root / "mercury" / mercury_name
            mercury.parent.mkdir(parents=True)
            mercury.touch()
            mercury.chmod(0o755)
            application = Path(directory) / "Contents" / "MacOS" / "MercurySkyPulse"
            with (
                patch.dict(os.environ, {}, clear=True),
                patch.object(sys, "frozen", True, create=True),
                patch.object(sys, "_MEIPASS", str(bundle_root), create=True),
                patch.object(sys, "executable", str(application)),
            ):
                found = discover_mercury_executable()
            self.assertEqual(mercury.resolve(), found)

    @unittest.skipIf(os.name == "nt", "fake Mercury uses Unix executable semantics")
    def test_unexpected_exit_schedules_restart(self) -> None:
        config = MercuryProcessConfig(
            executable=Path(sys.executable),
            restart_delays_ms=(500,),
        )
        supervisor = MercuryProcessSupervisor(config)
        states: list[str] = []
        supervisor.state_changed.connect(states.append)

        loop = QEventLoop()
        supervisor.restart_scheduled.connect(lambda delay: loop.quit())
        timeout = QTimer()
        timeout.setSingleShot(True)
        timeout.timeout.connect(loop.quit)
        timeout.start(3000)
        supervisor.start()
        loop.exec()
        supervisor.stop()

        self.assertIn("starting", states)
        self.assertIn("crashed", states)
        self.assertIn("restart-wait", states)

    def test_restart_backoff_is_bounded_and_stop_cancels_it(self) -> None:
        supervisor = MercuryProcessSupervisor(
            MercuryProcessConfig(restart_delays_ms=(5, 10))
        )
        delays = []
        supervisor.restart_scheduled.connect(delays.append)
        supervisor._intended_running = True
        for _ in range(4):
            supervisor._schedule_restart()
        self.assertEqual(delays, [5, 10, 10, 10])
        self.assertTrue(supervisor._restart_timer.isActive())
        supervisor.stop()
        self.assertFalse(supervisor._restart_timer.isActive())
        self.assertEqual(supervisor.state, "stopped")

    def test_expected_shutdown_suppresses_qprocess_crash_error(self) -> None:
        supervisor = MercuryProcessSupervisor()
        output = []
        supervisor.output_received.connect(output.append)
        supervisor._intended_running = False
        supervisor._set_state("stopping")

        supervisor._on_error(QProcess.ProcessError.Crashed)

        self.assertEqual(output, [])

    def test_missing_modem_reports_missing_without_retry_loop(self) -> None:
        supervisor = MercuryProcessSupervisor(
            MercuryProcessConfig(executable=Path("/definitely/missing/mercury"))
        )
        with patch("platform_runtime.mercury_process.discover_mercury_executable",
                   return_value=None):
            supervisor.start()
        self.assertEqual(supervisor.state, "missing")
        self.assertFalse(supervisor._restart_timer.isActive())
        supervisor.stop()

    def test_unmanaged_profile_never_discovers_or_launches_mercury(self) -> None:
        supervisor = MercuryProcessSupervisor(MercuryProcessConfig(managed=False))
        with patch("platform_runtime.mercury_process.discover_mercury_executable") as discover:
            supervisor.start()
        discover.assert_not_called()
        self.assertEqual(supervisor.state, "external")
        self.assertEqual(supervisor.process.state().name, "NotRunning")

    def test_radio_configuration_updates_documented_startup_options(self) -> None:
        supervisor = MercuryProcessSupervisor(MercuryProcessConfig())
        with patch.object(supervisor, "restart_now") as restart:
            supervisor.configure_radio(1035, "/dev/cu.radio", 38400)
        self.assertEqual(supervisor.config.radio_model, 1035)
        self.assertEqual(supervisor.config.radio_address, "/dev/cu.radio")
        self.assertEqual(supervisor.config.radio_serial_speed, 38400)
        restart.assert_called_once_with()

    def test_external_supervisor_refuses_radio_configuration(self) -> None:
        supervisor = MercuryProcessSupervisor(MercuryProcessConfig(managed=False))
        with self.assertRaises(RuntimeError):
            supervisor.configure_radio(1035, "/dev/cu.radio", 38400)

    def test_application_owned_config_contains_documented_cat_speed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mercury-skypulse.ini"
            supervisor = MercuryProcessSupervisor(MercuryProcessConfig(
                config_file=path, radio_serial_speed=115200,
                input_device="USB Audio \\\"RX\\\"", output_device="USB Audio TX",
            ))
            supervisor._write_application_config()
            self.assertEqual(
                path.read_text(encoding="utf-8"),
                "[main]\nradio_serial_speed = 115200\n"
                'input_device = "USB Audio \\\\\\"RX\\\\\\""\n'
                'output_device = "USB Audio TX"\n',
            )

    def test_station_configuration_updates_audio_and_restarts_once(self) -> None:
        supervisor = MercuryProcessSupervisor(MercuryProcessConfig())
        with patch.object(supervisor, "restart_now") as restart:
            supervisor.configure_station(
                1035, "COM4", 38400, "capture-id", "playback-id"
            )
        self.assertEqual(supervisor.config.input_device, "capture-id")
        self.assertEqual(supervisor.config.output_device, "playback-id")
        restart.assert_called_once_with()

    def test_fatal_radio_startup_output_has_actionable_operator_guidance(self) -> None:
        supervisor = MercuryProcessSupervisor()
        issues = []
        supervisor.startup_issue.connect(lambda *values: issues.append(values))

        supervisor._inspect_output_line("mercury_engine: radio init failed")

        self.assertEqual(issues[0][0], "Radio setup required")
        self.assertIn("Setup → Radio", issues[0][1])
        self.assertIn("disable Hamlib", issues[0][1])

    def test_fatal_audio_startup_output_has_actionable_operator_guidance(self) -> None:
        supervisor = MercuryProcessSupervisor()
        issues = []
        supervisor.startup_issue.connect(lambda *values: issues.append(values))

        supervisor._inspect_output_line("mercury_engine: audio init failed")

        self.assertEqual(issues[0][0], "Audio setup required")
        self.assertIn("Setup → Audio", issues[0][1])


if __name__ == "__main__":
    unittest.main()

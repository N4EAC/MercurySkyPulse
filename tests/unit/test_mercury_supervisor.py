"""Process discovery and crash-restart behavior tests."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from PySide6.QtCore import QEventLoop, QTimer
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


if __name__ == "__main__":
    unittest.main()

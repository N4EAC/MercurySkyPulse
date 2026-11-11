"""Software-only contracts for the isolated receive-only test launcher."""
import configparser
import os
import socket
import time
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import coreaudio_254_test as harness


class CoreAudioLauncherTests(unittest.TestCase):
    def test_configuration_has_no_cat_and_uses_selected_endpoints(self):
        config = configparser.ConfigParser()
        config.read_string(harness.configuration("702", "703"))
        self.assertEqual(config["ptt"]["method"], "none")
        self.assertEqual(config["ptt"]["hamlib_model"], "0")
        self.assertEqual(config["main"]["input_device"], '"702"')
        self.assertEqual(config["main"]["output_device"], '"703"')
        self.assertEqual(config["main"]["capture_channel"], "left")
        self.assertEqual(config["main"]["sound_system"], "coreaudio")
        for unsafe in ('1"\n[ptt]\nmethod=hamlib', "default", "USB Audio"):
            with self.assertRaises(ValueError):
                harness.configuration(unsafe, "703")

    def test_native_list_requires_real_capture_and_playback_ids(self):
        text = ("playback devices:\n"
                "device: name: 'USB Audio Device'  id: '703'  default: 0\n"
                "capture devices:\n"
                "device: name: 'USB Audio Device'  id: '702'  default: 0\n")
        self.assertEqual(harness.parse_devices(text), {
            "capture": [("USB Audio Device", "702")],
            "playback": [("USB Audio Device", "703")],
        })
        self.assertEqual(harness.parse_devices("capture devices:\n" )["capture"], [])

    def test_missing_or_changed_override_never_uses_bundled_mercury(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                harness.checked_binary()
        with tempfile.TemporaryDirectory() as folder:
            binary = Path(folder) / "mercury"
            binary.write_bytes(b"changed binary")
            binary.chmod(0o700)
            with patch.dict(os.environ, {"MERCURY_EXECUTABLE": str(binary)}):
                with self.assertRaisesRegex(ValueError, "differs"):
                    harness.checked_binary()

    def test_collection_keeps_startup_and_errors_without_launching(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            session = root / "session"
            session.mkdir()
            (session / "manifest.json").write_text("{}")
            (session / "activity.log").write_text("OPERATOR START cycle=0\n")
            (session / "mercury-00.log").write_text("startup\ncapture stalled 2005 ms\nAudioDeviceStart\n")
            with patch.object(harness, "ARTIFACTS", root):
                archive = harness.collect(session)
            self.assertTrue(archive.is_file())
            report = (session / "RECEPTION_REPORT.txt").read_text()
            self.assertIn("Start attempts: 1", report)
            self.assertIn("Engine initializations: 0", report)
            self.assertIn("capture stalled", report)
            self.assertIn("AudioDeviceStart", report)

    def test_live_listener_is_rejected_but_departed_connection_is_reusable(self):
        with socket.socket() as server:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(("127.0.0.1", 0))
            port = server.getsockname()[1]
            server.listen(1)
            with self.assertRaisesRegex(ValueError, "occupied"):
                harness.check_ports((port,))
            with socket.create_connection(("127.0.0.1", port)) as client:
                connection, _ = server.accept()
                connection.shutdown(socket.SHUT_WR)
                self.assertEqual(client.recv(1), b"")
                connection.close()
        harness.check_ports((port,))

    def test_gui_counting_and_nonblocking_stop_without_real_processes(self):
        from PySide6.QtCore import QProcess
        from platform_runtime.mercury_process import MercuryProcessSupervisor

        def exercise(window):
            try:
                with patch.object(window.engine, "start"), patch.object(window.telemetry, "start"):
                    window.start_selected("702", "703")
                    self.assertEqual(window.cycle, -1)  # attempt is not a launch
                    window.start_run()
                    self.assertEqual(window.cycle, -1)
                with patch.object(harness, "check_ports", side_effect=ValueError("occupied")):
                    window.engine._spawn()
                    self.assertEqual(window.cycle, -1)
                    self.assertTrue(window.start_button.isEnabled())
                window.process_started()
                self.assertEqual(window.cycle, 0)
                window.frames = 25
                window.run_start = time.monotonic() - 35
                window.last_frame = time.monotonic()
                with patch.object(window.engine.process, "state", return_value=QProcess.Running):
                    window.begin_retest()
                    window.snapshot()
                    self.assertEqual(window.confirmed, {0})
                    self.assertTrue(window.restart.isEnabled())
                    window.last_frame = time.monotonic() - 15
                    window.snapshot()
                    self.assertFalse(window.restart.isEnabled())
                    with patch.object(window.engine.process, "terminate") as terminate:
                        window.stop_mercury()
                        terminate.assert_not_called()  # Qt close has time to run
                        window.stop_started -= 1
                        window.poll_stop()
                        terminate.assert_called_once()
                    with patch.object(window.sampler, "start") as sample, \
                         patch.object(window.engine.process, "processId", return_value=4321), \
                         patch.object(window.engine.process, "kill") as kill:
                        window.stop_started = time.monotonic() - 4
                        window.poll_stop()
                        self.assertEqual(sample.call_args.args[0], "/usr/bin/sample")
                        self.assertEqual(sample.call_args.args[1][:3], ["4321", "1", "1"])
                        window.stop_started = time.monotonic() - 11
                        window.poll_stop()
                        kill.assert_called_once()
                        sample.assert_called_once()
                window.poll_stop()
                self.assertFalse(window.stopping)
            finally:
                window.close()

        with tempfile.TemporaryDirectory() as folder, \
             patch.object(harness, "ARTIFACTS", Path(folder)), \
             patch.object(harness, "checked_binary", return_value=Path("/test/mercury")), \
             patch.object(harness, "check_ports"), \
             patch.object(QProcess, "start", side_effect=AssertionError("No subprocess allowed")), \
             patch.object(MercuryProcessSupervisor, "start", side_effect=AssertionError("No modem allowed")):
            harness.launch(exercise)


if __name__ == "__main__":
    unittest.main()

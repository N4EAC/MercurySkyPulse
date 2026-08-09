"""Radio setup persistence, catalog parsing, and tune safety tests."""

from __future__ import annotations

import unittest
from unittest.mock import Mock

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from application.radio import HamlibRig, RadioStationService
from persistence.chat_repository import ChatRepository
from platform_runtime.hamlib_catalog import parse_hamlib_catalog


CATALOG = """Rhizomatica Mercury Version 1.9.11
 Rig #  Mfg                    Model                   Version         Status      Macro
     1  Hamlib                 Dummy                   20240709.0      Stable      RIG_MODEL_DUMMY
  1035  Yaesu                  FT-991                  20241118.18     Stable      RIG_MODEL_FT991
  2026  Elecraft               K3/KX3                  20250515.0      Stable      RIG_MODEL_K3
"""


class FakeCatalog(QObject):
    models_loaded = Signal(object)
    error_received = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.loaded = False

    def load(self) -> None:
        self.loaded = True


class FakeRadioClient(QObject):
    control_event = Signal(str)
    state_changed = Signal(str)
    session_disconnected = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.commands = []

    def start_tune(self, level): self.commands.append(("start", level))
    def set_tune_level(self, level): self.commands.append(("level", level))
    def stop_tune(self): self.commands.append(("stop",))


class FakeStationDevices(QObject):
    serial_ports_loaded = Signal(object)

    def load(self) -> None:
        pass


class RadioStationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication(["radio-service-test"])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.repository = ChatRepository(":memory:")
        self.catalog = FakeCatalog()
        self.client = FakeRadioClient()
        self.runtime = Mock()
        self.station_devices = FakeStationDevices()
        self.service = RadioStationService(
            self.client, self.repository, self.catalog, self.runtime,
            self.station_devices, True
        )
        self.rigs = parse_hamlib_catalog(CATALOG)
        self.catalog.models_loaded.emit(self.rigs)

    def tearDown(self) -> None:
        self.service.stop()
        self.repository.close()

    def test_parser_reads_mercury_compiled_hamlib_catalog(self) -> None:
        self.assertEqual([rig.model_id for rig in self.rigs], [1, 1035, 2026])
        self.assertEqual(self.rigs[1].manufacturer, "Yaesu")
        self.assertEqual(self.rigs[1].model, "FT-991")

    def test_radio_selection_is_persisted_and_applied_through_runtime(self) -> None:
        self.service.apply(
            1035, "/dev/cu.usbserial-1", 38400, "capture:radio", "playback:radio"
        )
        self.runtime.configure_station.assert_called_once_with(
            1035, "/dev/cu.usbserial-1", 38400,
            "capture:radio", "playback:radio",
        )
        restored = RadioStationService(
            self.client, self.repository, FakeCatalog(), self.runtime,
            FakeStationDevices(), True
        )
        self.assertEqual(restored.config.model_id, 1035)
        self.assertEqual(restored.config.device, "/dev/cu.usbserial-1")
        self.assertEqual(restored.config.serial_speed, 38400)
        self.assertEqual(restored.config.input_device, "capture:radio")
        self.assertEqual(restored.config.output_device, "playback:radio")
        restored.stop()

    def test_external_mercury_radio_configuration_is_rejected(self) -> None:
        external = RadioStationService(
            self.client, self.repository, FakeCatalog(), self.runtime,
            FakeStationDevices(), False
        )
        errors = []
        external.error_received.connect(errors.append)
        external.apply(1035, "radio:4532", 0)
        self.assertIn("external Mercury host", errors[0])
        self.runtime.configure_station.assert_not_called()
        external.stop()

    def test_tune_level_persists_and_timeout_sends_off(self) -> None:
        states = []
        self.service.tune_state_changed.connect(lambda active, text: states.append((active, text)))
        self.service.set_tune_level(-15)
        self.service.start_tune()
        self.assertEqual(self.service._tune_timer.interval(), 12_000)
        self.assertEqual(self.client.commands, [("start", -15)])
        self.assertTrue(self.service._tune_timer.isActive())
        self.service._tune_timeout()
        self.assertEqual(self.client.commands[-1], ("stop",))
        self.assertFalse(states[-1][0])
        self.assertEqual(self.repository.get_setting("radio.tune_dbfs"), "-15")

    def test_live_slider_change_does_not_extend_twelve_second_timer(self) -> None:
        self.service.start_tune()
        remaining = self.service._tune_timer.remainingTime()
        self.service.set_tune_level(-10)
        self.assertEqual(self.client.commands[-1], ("level", -10))
        self.assertLessEqual(self.service._tune_timer.remainingTime(), remaining)

    def test_active_link_prevents_tuning(self) -> None:
        errors = []
        self.service.error_received.connect(errors.append)
        self.client.state_changed.emit("connected")
        self.service.start_tune()
        self.assertEqual(self.client.commands, [])
        self.assertIn("Disconnect", errors[0])

    def test_control_disconnect_warns_operator_about_mercury_failsafe(self) -> None:
        errors = []
        self.service.error_received.connect(errors.append)
        self.service.start_tune()
        self.client.state_changed.emit("disconnected")
        self.assertFalse(self.service._tune_timer.isActive())
        self.assertIn("verify the transmitter unkeyed", errors[-1])


if __name__ == "__main__":
    unittest.main()

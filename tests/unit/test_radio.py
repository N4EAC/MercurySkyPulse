"""Radio setup persistence and catalog parsing tests."""

from __future__ import annotations

import unittest
from unittest.mock import Mock

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from application.modem import ModemStatus
from application.radio import HamlibRig, RadioStationService, TxLevelTestService
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



class FakeStationDevices(QObject):
    serial_ports_loaded = Signal(object)
    audio_inputs_loaded = Signal(object)
    audio_outputs_loaded = Signal(object)

    def load(self) -> None:
        pass


class FakeTelemetry(QObject):
    status_received = Signal(object)
    state_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.levels = []

    def set_tx_gain_db(self, level) -> None:
        self.levels.append(float(level))


class FakeBeaconService:
    def __init__(self, callsign="N0CALL", grid="FN30") -> None:
        self.config = type("Config", (), {"callsign": callsign, "grid": grid})()
        self.sent = 0

    def transmit_test_beacon(self) -> None:
        self.sent += 1


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

    def test_platform_audio_fallback_is_relayed_to_setup(self) -> None:
        inputs = [("Microphone", "Microphone")]
        outputs = [("Speakers", "Speakers")]
        received_inputs = []
        received_outputs = []
        self.service.audio_inputs_changed.connect(received_inputs.append)
        self.service.audio_outputs_changed.connect(received_outputs.append)
        self.station_devices.audio_inputs_loaded.emit(inputs)
        self.station_devices.audio_outputs_loaded.emit(outputs)
        self.assertEqual(received_inputs, [inputs])
        self.assertEqual(received_outputs, [outputs])

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

    def test_tx_level_test_sends_bounded_real_beacons_and_uses_modem_gain(self) -> None:
        telemetry = FakeTelemetry()
        beacon = FakeBeaconService()
        service = TxLevelTestService(beacon, telemetry, self.client)
        states = []
        service.state_changed.connect(lambda active, text: states.append((active, text)))
        service.set_level(-12)
        service.start()
        self.assertTrue(service.active)
        self.assertEqual(telemetry.levels, [-12.0, -12.0])
        self.assertEqual(beacon.sent, 1)
        self.assertEqual(service._deadline.interval(), 12_000)
        self.assertEqual(service._pulse_timer.interval(), 3_000)
        service._send_beacon()
        self.assertEqual(beacon.sent, 2)
        service._timeout()
        self.assertFalse(service.active)
        self.assertIn("12-second", states[-1][1])

    def test_tx_level_test_requires_identity_and_stops_for_active_link(self) -> None:
        telemetry = FakeTelemetry()
        service = TxLevelTestService(FakeBeaconService("", ""), telemetry, self.client)
        errors = []
        service.error_received.connect(errors.append)
        service.start()
        self.assertFalse(service.active)
        self.assertIn("callsign and GRID", errors[-1])

        service = TxLevelTestService(FakeBeaconService(), telemetry, self.client)
        service.error_received.connect(errors.append)
        self.client.state_changed.emit("connected")
        service.start()
        self.assertFalse(service.active)
        self.assertIn("Disconnect", errors[-1])

    def test_tx_level_test_reports_peak_and_does_not_overwrite_active_setting(self) -> None:
        telemetry = FakeTelemetry()
        service = TxLevelTestService(FakeBeaconService(), telemetry, self.client)
        levels, peaks = [], []
        service.level_changed.connect(levels.append)
        service.peak_changed.connect(peaks.append)
        telemetry.status_received.emit(
            ModemStatus(tx_gain_db=-7.0, tx_peak_dbfs=-3.5)
        )
        self.assertEqual(levels[-1], -7.0)
        self.assertEqual(peaks[-1], -3.5)
        service.start()
        telemetry.status_received.emit(
            ModemStatus(tx_gain_db=-2.0, tx_peak_dbfs=-1.0)
        )
        self.assertEqual(levels[-1], -7.0)
        self.assertEqual(peaks[-1], -1.0)
        service.stop()


if __name__ == "__main__":
    unittest.main()

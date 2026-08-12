"""PSK Reporter IPFIX and aggregation tests without external networking."""

from __future__ import annotations

from datetime import UTC, datetime
import struct
import unittest

from PySide6.QtCore import QObject, Signal

from application.beacon import Beacon
from application.psk_reporter import PskReception, PskReporterService
from persistence.chat_repository import ChatRepository
from platform_runtime.psk_reporter import SENDER_TEMPLATE, encode_ipfix


class FakeBeaconService(QObject):
    beacon_received = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.config = type("Config", (), {"callsign": "N4EAC", "grid": "EL98"})()


class FakeUploader(QObject):
    sent = Signal(int)
    error_received = Signal(str)
    activity_logged = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.uploads = []

    def upload(self, *values) -> None:
        self.uploads.append(values)


class FakeTelemetry(QObject):
    status_received = Signal(object)


class PskReporterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = ChatRepository(":memory:")
        self.beacons = FakeBeaconService()
        self.uploader = FakeUploader()
        self.telemetry = FakeTelemetry()
        self.service = PskReporterService(
            self.beacons, self.telemetry, self.repository, self.uploader, "0.1.0",
            random_delay=lambda: 0,
        )

    def tearDown(self) -> None:
        self.service.stop()
        self.repository.close()

    def test_cookie_cutter_packet_has_ipfix_header_templates_and_fields(self) -> None:
        self.assertEqual(len(SENDER_TEMPLATE), 0x34)
        self.assertEqual(SENDER_TEMPLATE[4:8], bytes.fromhex("99930006"))
        self.assertEqual(SENDER_TEMPLATE[8:16], bytes.fromhex("8001ffff0000768f"))
        report = PskReception("K1ABC", "FN31", 14_105_000, "OFDM", 1_700_000_000)
        packet = encode_ipfix(
            "N4EAC", "EL98", "MercurySkyPulse 0.1.0", "Dipole", (report,),
            7, 0x12345678, True, 1_700_000_100,
        )
        version, length, exported, sequence, observation = struct.unpack_from(
            ">HHIII", packet
        )
        self.assertEqual((version, length), (10, len(packet)))
        self.assertEqual((exported, sequence, observation),
                         (1_700_000_100, 7, 0x12345678))
        self.assertIn(b"N4EAC", packet)
        self.assertIn(b"K1ABC", packet)
        self.assertIn(b"OFDM", packet)
        self.assertIn(b"Dipole", packet)
        self.assertLessEqual(len(packet), 1400)

    def test_reporting_is_opt_in_persistent_deduplicated_and_rate_limited(self) -> None:
        activity = []
        self.service.activity_logged.connect(activity.append)
        self.service.configure(True, "Loop")
        self.telemetry.status_received.emit(type("Status", (), {
            "radio_frequency_hz": 14_105_000,
            "radio_frequency_age_ms": 100,
        })())
        beacon = Beacon(
            "K1ABC", "FN31", "0.1.0", ("beacon",),
            datetime.now(UTC).isoformat(),
        )
        self.beacons.beacon_received.emit(beacon)
        self.beacons.beacon_received.emit(beacon)
        self.assertEqual(len(self.service._reports), 1)
        self.assertEqual(self.service._timer.interval(), 300_000)
        self.service.flush()
        self.service._timer.stop()
        self.assertEqual(len(self.uploader.uploads), 1)
        values = self.uploader.uploads[0]
        self.assertEqual(values[:4], ("N4EAC", "EL98", "MercurySkyPulse 0.1.0", "Loop"))
        self.assertEqual(values[4][0].mode, "OFDM")
        self.assertTrue(values[5])
        self.assertTrue(any("receiver_callsign=N4EAC" in line for line in activity))
        self.assertTrue(any("sender_callsign=K1ABC" in line for line in activity))
        self.assertTrue(any("frequency_hz=14105000" in line for line in activity))
        restored = PskReporterService(
            self.beacons, self.telemetry, self.repository, FakeUploader(), "0.1.0"
        )
        self.assertTrue(restored.config.enabled)
        restored.stop()

    def test_enable_requires_saved_station_identity_and_spot_requires_frequency(self) -> None:
        errors = []
        self.service.error_received.connect(errors.append)
        self.beacons.config = type("Config", (), {"callsign": "", "grid": ""})()
        self.service.configure(True, "Dipole")
        self.assertIn("Callsign", errors[-1])
        self.beacons.config = type("Config", (), {"callsign": "N4EAC", "grid": "EL98"})()
        self.service.configure(True, "Dipole")
        states = []
        self.service.state_changed.connect(states.append)
        self.beacons.beacon_received.emit(Beacon(
            "K1ABC", "FN31", "0.1.0", ("beacon",),
            datetime.now(UTC).isoformat(),
        ))
        self.assertEqual(states[-1], "waiting-for-frequency")
        self.assertEqual(self.service._reports, [])


if __name__ == "__main__":
    unittest.main()

import unittest

from PySide6.QtCore import QObject, Signal

from application.beacon import (
    DEFAULT_BEACON_CAPABILITIES,
    BeaconService,
    normalize_grid,
)
from application_protocol.beacon import encode_beacon
from application.location import Location
from persistence.chat_repository import ChatRepository
from application.beacon import Beacon


class FakeBeaconClient(QObject):
    beacon_received = Signal(object)
    error_received = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.sent = []

    def start(self):
        pass

    def stop(self):
        pass

    def send_beacon(self, beacon):
        self.sent.append(beacon)


class BeaconTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = ChatRepository(":memory:")
        self.client = FakeBeaconClient()
        self.service = BeaconService(
            self.client,
            self.repository,
            "0.1.0",
            ("location", "chat", "file-transfer"),
            auto_timer=False,
        )

    def tearDown(self) -> None:
        self.repository.close()

    def test_grid_validation(self) -> None:
        self.assertEqual(normalize_grid("fn30as"), "FN30AS")
        self.assertEqual(normalize_grid("FN30"), "FN30")
        with self.assertRaises(ValueError):
            normalize_grid("ZZ99")

    def test_configuration_is_persisted_with_selectable_interval(self) -> None:
        self.service.configure("n0call", "fn30as", 15, True)
        restored = BeaconService(
            self.client,
            self.repository,
            "0.1.0",
            ("chat",),
            auto_timer=False,
        )
        self.assertEqual(restored.config.callsign, "N0CALL")
        self.assertEqual(restored.config.grid, "FN30AS")
        self.assertEqual(restored.config.interval_minutes, 15)
        self.assertTrue(restored.config.include_gps)
        self.assertEqual(self.service._timer.interval(), 15 * 60 * 1000)

    def test_beacon_contains_version_grid_callsign_and_capabilities(self) -> None:
        self.service.configure("N0CALL", "FN30AS", 5, False)
        self.service.send_now()
        event = self.client.sent[0]
        self.assertEqual(event.callsign, "N0CALL")
        self.assertEqual(event.grid, "FN30AS")
        self.assertEqual(event.software_version, "0.1.0")
        self.assertEqual(
            event.capabilities, ("chat", "file-transfer", "location")
        )
        self.assertIsNone(event.latitude)

    def test_default_application_capabilities_are_wire_encodable(self) -> None:
        beacon = Beacon(
            "N0CALL", "FN30", "0.1.0", DEFAULT_BEACON_CAPABILITIES,
            "2026-08-08T12:00:00+00:00",
        )
        self.assertTrue(encode_beacon(beacon).startswith(b"MSPB"))

    def test_service_rejects_non_wire_capability_during_construction(self) -> None:
        with self.assertRaisesRegex(ValueError, "radio-setup"):
            BeaconService(
                self.client, self.repository, "0.1.0", ("chat", "radio-setup"),
                auto_timer=False,
            )

    def test_gps_is_included_only_when_selected_and_available(self) -> None:
        self.service.configure("N0CALL", "FN30AS", 1, True)
        self.service.send_now()
        self.assertIsNone(self.client.sent[-1].latitude)
        self.service.update_location(
            Location(40.1, -74.2, "manual", "now")
        )
        self.service.send_now()
        self.assertIsNone(self.client.sent[-1].latitude)
        self.service.update_location(
            Location(40.1, -74.2, "gps", "2026-01-01T00:00:00+00:00", 5.0)
        )
        self.service.send_now()
        self.assertEqual(self.client.sent[-1].latitude, 40.1)
        self.assertEqual(self.client.sent[-1].longitude, -74.2)
        self.assertEqual(
            self.client.sent[-1].gps_timestamp,
            "2026-01-01T00:00:00+00:00",
        )

    def test_received_beacon_is_validated(self) -> None:
        received = []
        self.service.beacon_received.connect(received.append)
        self.client.beacon_received.emit(
            Beacon(
                "K1ABC", "FN31", "0.1.0", ("beacon", "chat"), "now",
                41.0, -73.0, "now",
            )
        )
        self.assertEqual(received[0].callsign, "K1ABC")
        self.assertEqual(received[0].capabilities, ("beacon", "chat"))

    def test_turn_off_persists_disabled_interval(self) -> None:
        self.service.configure("N0CALL", "FN30AS", 10, False)
        self.service.disable()
        self.assertEqual(self.service.config.interval_minutes, 0)


if __name__ == "__main__":
    unittest.main()

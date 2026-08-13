import unittest
from datetime import UTC, datetime, timedelta

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
from application.beacon import CqCall


class FakeBeaconClient(QObject):
    beacon_received = Signal(object)
    cq_received = Signal(object)
    error_received = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.sent = []
        self.cq_sent = []

    def start(self):
        pass

    def stop(self):
        pass

    def send_beacon(self, beacon):
        self.sent.append(beacon)

    def send_cq(self, cq):
        self.cq_sent.append(cq)


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
        self.assertEqual(self.service.milliseconds_until_next(), 15 * 60 * 1000)

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
        self.assertIsNone(self.service.milliseconds_until_next())

    def test_cq_uses_saved_identity_without_arq_session(self) -> None:
        self.service.configure("N0CALL", "FN30AS", 5, False)
        self.service.call_cq()
        self.assertEqual(self.client.cq_sent[-1].callsign, "N0CALL")
        self.assertEqual(self.client.cq_sent[-1].grid, "FN30AS")
        self.assertTrue(self.service.periodic_paused)
        self.assertEqual(self.service._cq_hold_timer.interval(), 300_000)
        self.assertIsNone(self.service.milliseconds_until_next())

    def test_new_cq_refreshes_five_minute_beacon_hold(self) -> None:
        self.service.configure("N0CALL", "FN30AS", 5, False)
        self.service.call_cq()
        self.service.call_cq()
        self.assertTrue(self.service.periodic_paused)
        self.assertEqual(self.service._cq_hold_timer.interval(), 300_000)

    def test_cq_hold_expiry_resumes_when_no_session_is_active(self) -> None:
        self.service.configure("N0CALL", "FN30AS", 5, False)
        self.service.call_cq()
        self.service._cq_hold_expired()
        self.assertFalse(self.service.periodic_paused)
        self.assertEqual(self.service.milliseconds_until_next(), 5 * 60 * 1000)

    def test_arq_session_pauses_periodic_beacon_until_disconnected(self) -> None:
        self.service.configure("N0CALL", "FN30AS", 5, False)
        self.service.set_session_connected(True)
        self.assertTrue(self.service.periodic_paused)
        self.assertIsNone(self.service.milliseconds_until_next())
        self.service.set_session_connected(False)
        self.assertFalse(self.service.periodic_paused)
        self.assertEqual(self.service.milliseconds_until_next(), 5 * 60 * 1000)

    def test_expired_cq_hold_remains_paused_during_arq_session(self) -> None:
        self.service.configure("N0CALL", "FN30AS", 5, False)
        self.service.call_cq()
        self.service.set_session_connected(True)
        self.service._cq_hold_expired()
        self.assertTrue(self.service.periodic_paused)
        self.service.set_session_connected(False)
        self.assertFalse(self.service.periodic_paused)

    def test_received_cq_is_bounded_by_age_and_ignores_self(self) -> None:
        received, errors = [], []
        self.service.cq_received.connect(received.append)
        self.service.error_received.connect(errors.append)
        now = datetime.now(UTC)
        self.client.cq_received.emit(
            CqCall("K1ABC", "FN31", "0.1.0", now.isoformat())
        )
        self.client.cq_received.emit(
            CqCall("K1OLD", "FN32", "0.1.0", (now - timedelta(minutes=6)).isoformat())
        )
        self.assertEqual([item.callsign for item in received], ["K1ABC"])
        self.assertIn("five-minute window", errors[-1])


if __name__ == "__main__":
    unittest.main()

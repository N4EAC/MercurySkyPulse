import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import QObject, Signal

from application.location import LocationService, from_aprs, to_aprs, to_maidenhead
from persistence.chat_repository import ChatRepository
from application_protocol.messaging import ChatEnvelope
from platform_runtime.location_exporter import LocationExporter


class FakeGpsReceiver(QObject):
    position_received = Signal(float, float, object)
    state_changed = Signal(str)
    error_received = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.started_with = None

    def start(self, serial_port="") -> None:
        self.started_with = serial_port

    def stop(self) -> None:
        pass


class FakeLocationClient(QObject):
    location_received = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.sent = []

    def send_file_event(self, kind, event_id, timestamp, **values) -> None:
        self.sent.append((kind, event_id, timestamp, values))


class LocationTests(unittest.TestCase):
    def test_decimal_coordinates_convert_to_maidenhead_grid(self) -> None:
        self.assertEqual(to_maidenhead(40.7128, -74.0060), "FN20XR")
        self.assertEqual(to_maidenhead(51.5074, -0.1278), "IO91WM")
        self.assertEqual(to_maidenhead(-33.8688, 151.2093), "QF56OD")

    def setUp(self) -> None:
        self.repository = ChatRepository(":memory:")
        self.receiver = FakeGpsReceiver()
        self.client = FakeLocationClient()
        self.service = LocationService(
            self.client, self.repository, self.receiver
        )

    def tearDown(self) -> None:
        self.repository.close()

    def test_aprs_round_trip(self) -> None:
        encoded = to_aprs(40.7128, -74.0060)
        self.assertEqual(encoded, "4042.77N/07400.36W")
        latitude, longitude = from_aprs(encoded)
        self.assertAlmostEqual(latitude, 40.7128, places=3)
        self.assertAlmostEqual(longitude, -74.0060, places=3)

    def test_manual_position_is_persisted(self) -> None:
        self.service.set_manual("40.7128", "-74.006")
        self.assertEqual(self.service.current.source, "manual")
        restored = LocationService(
            self.client, self.repository, FakeGpsReceiver()
        )
        self.assertAlmostEqual(restored.current.latitude, 40.7128)

    def test_blank_manual_position_has_operator_friendly_error(self) -> None:
        errors = []
        self.service.error_received.connect(errors.append)
        self.service.set_manual("", "")
        self.assertEqual(
            errors,
            ["Enter both latitude and longitude before saving a manual position"],
        )

    def test_gps_receiver_fix_becomes_current_without_auto_sharing(self) -> None:
        self.service.start_gps("/dev/example")
        self.assertEqual(self.receiver.started_with, "/dev/example")
        restored = LocationService(self.client, self.repository, FakeGpsReceiver())
        self.assertEqual(restored.saved_gps_port, "/dev/example")
        restored.start()
        self.assertEqual(restored.receiver.started_with, "/dev/example")
        self.receiver.position_received.emit(51.5, -0.12, 8.0)
        self.assertEqual(self.service.current.source, "gps")
        self.assertEqual(self.client.sent, [])
        self.assertEqual(self.repository.gps_location_count(), 0)

    def test_gps_stop_disables_automatic_restart(self) -> None:
        self.service.start_gps("/dev/example")
        self.service.stop_gps()
        restored_receiver = FakeGpsReceiver()
        restored = LocationService(self.client, self.repository, restored_receiver)
        restored.start()
        self.assertIsNone(restored_receiver.started_with)

    def test_gps_fix_keeps_position_when_accuracy_is_unavailable(self) -> None:
        errors = []
        self.service.error_received.connect(errors.append)
        for unavailable_accuracy in (float("nan"), float("inf"), -1.0, "unknown"):
            self.receiver.position_received.emit(
                28.538336, -81.379234, unavailable_accuracy
            )
            self.assertAlmostEqual(self.service.current.latitude, 28.538336)
            self.assertIsNone(self.service.current.accuracy_m)
        self.assertEqual(errors, [])

    def test_gps_retention_is_opt_in_and_persisted(self) -> None:
        self.receiver.position_received.emit(10.0, 20.0, 3.0)
        self.assertEqual(self.repository.gps_location_count(), 0)
        self.service.set_retention(True)
        self.receiver.position_received.emit(10.1, 20.1, 4.0)
        self.assertEqual(self.repository.gps_location_count(), 1)
        restored = LocationService(
            self.client, self.repository, FakeGpsReceiver()
        )
        self.assertTrue(restored.retention_enabled)

    def test_exports_retained_track(self) -> None:
        with TemporaryDirectory() as directory:
            service = LocationService(
                self.client,
                self.repository,
                self.receiver,
                exporter=LocationExporter(),
            )
            service.set_retention(True)
            self.receiver.position_received.emit(40.0, -74.0, 5.0)
            destination = Path(directory) / "track.gpx"
            service.export_history(str(destination))
            self.assertTrue(destination.exists())
            self.assertIn("<trkpt", destination.read_text())

    def test_location_sharing_is_explicit(self) -> None:
        self.service.set_manual("40.7128", "-74.006")
        self.service.share()
        self.assertEqual(self.client.sent[0][0], "location")
        self.assertEqual(
            self.client.sent[0][3]["aprs"], "4042.77N/07400.36W"
        )

    def test_receives_valid_shared_location(self) -> None:
        received = []
        self.service.shared_received.connect(received.append)
        self.client.location_received.emit(
            ChatEnvelope(
                "location", "id", "now",
                values={
                    "latitude": 40.7128,
                    "longitude": -74.006,
                    "aprs": "4042.77N/07400.36W",
                    "accuracy_m": 5,
                },
            )
        )
        self.assertEqual(received[0].source, "shared")
        self.assertEqual(received[0].accuracy_m, 5)

    def test_invalid_coordinates_are_rejected(self) -> None:
        errors = []
        self.service.error_received.connect(errors.append)
        self.service.set_manual("91", "0")
        self.assertTrue(errors)
        with self.assertRaises(ValueError):
            from_aprs("4060.00N/07400.00W")


if __name__ == "__main__":
    unittest.main()

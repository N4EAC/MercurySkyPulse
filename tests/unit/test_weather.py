import json
import unittest

from PySide6.QtCore import QObject, Signal

from application.location import Location, to_maidenhead
from application.weather import WeatherService, maidenhead_center
from persistence.chat_repository import ChatRepository


class FakeWeatherProvider(QObject):
    received = Signal(bytes)
    error_received = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.requests = []

    def fetch(self, latitude, longitude) -> None:
        self.requests.append((latitude, longitude))


class WeatherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = ChatRepository(":memory:")
        self.provider = FakeWeatherProvider()
        self.service = WeatherService(self.repository, self.provider)

    def tearDown(self) -> None:
        self.repository.close()

    def config(self, grid="FN30AS"):
        return type("Config", (), {"grid": grid})()

    def test_grid_center_round_trips_to_same_locator(self) -> None:
        for grid in ("FN30", "FN30AS", "FN30AS12"):
            latitude, longitude = maidenhead_center(grid)
            self.assertEqual(to_maidenhead(latitude, longitude, len(grid)), grid)

    def test_fetch_requires_explicit_consent(self) -> None:
        errors = []
        self.service.error_received.connect(errors.append)
        self.service.update_grid(self.config())
        self.service.fetch()
        self.assertEqual(self.provider.requests, [])
        self.assertIn("Enable internet weather", errors[-1])

    def test_fetch_prefers_current_position_and_persists_consent(self) -> None:
        self.service.configure(True)
        self.service.update_grid(self.config())
        self.service.update_location(Location(40.1, -74.2, "gps", "now"))
        self.service.fetch()
        self.assertEqual(self.provider.requests, [(40.1, -74.2)])
        self.assertEqual(self.repository.get_setting("weather.internet_enabled"), "true")

    def test_grid_center_is_used_without_coordinates(self) -> None:
        self.service.configure(True)
        self.service.update_grid(self.config())
        self.service.fetch()
        self.assertEqual(self.provider.requests[0], maidenhead_center("FN30AS"))

    def test_operator_can_force_saved_grid_instead_of_current_position(self) -> None:
        self.service.configure(True)
        self.service.update_grid(self.config())
        self.service.update_location(Location(40.1, -74.2, "gps", "now"))
        self.service.set_use_station_position(False)
        self.service.fetch()
        self.assertEqual(self.provider.requests[0], maidenhead_center("FN30AS"))
        self.assertEqual(
            self.repository.get_setting("weather.use_station_position"), "false"
        )

    def test_bounded_response_becomes_operator_reviewed_chat_text(self) -> None:
        reports = []
        self.service.report_ready.connect(reports.append)
        self.service.update_grid(self.config())
        payload = {
            "current_condition": [{
                "weatherDesc": [{"value": "Partly cloudy"}],
                "temp_C": "22", "humidity": "68", "windspeedKmph": "12",
                "winddir16Point": "SW", "pressure": "1015",
                "localObsDateTime": "2026-08-13 10:30 AM",
            }],
            "nearest_area": [{"areaName": [{"value": "Trenton"}]}],
        }
        self.provider.received.emit(json.dumps(payload).encode())
        self.assertIn("WX FN30AS Partly cloudy 22°C", reports[0].text)
        self.assertIn("RH 68% WIND SW 12 km/h PRESS 1015 hPa", reports[0].text)
        self.assertEqual(reports[0].source_location, "Trenton")

    def test_malformed_weather_is_rejected(self) -> None:
        errors = []
        self.service.error_received.connect(errors.append)
        self.provider.received.emit(b"{}")
        self.assertIn("could not be read", errors[-1])

    def test_chat_fetch_emits_draft_text_only_after_response(self) -> None:
        drafts = []
        self.service.chat_report_ready.connect(drafts.append)
        self.service.configure(True)
        self.service.update_grid(self.config())
        self.service.fetch_for_chat()
        self.assertEqual(drafts, [])
        self.provider.received.emit(json.dumps({
            "current_condition": [{
                "weatherDesc": [{"value": "Clear"}], "temp_C": "20",
                "humidity": "50", "windspeedKmph": "5",
                "winddir16Point": "N", "pressure": "1010",
            }],
            "nearest_area": [{"areaName": [{"value": "Test"}]}],
        }).encode())
        self.assertEqual(len(drafts), 1)
        self.assertTrue(drafts[0].startswith("WX FN30AS Clear"))


if __name__ == "__main__":
    unittest.main()

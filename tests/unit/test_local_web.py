from __future__ import annotations

from dataclasses import dataclass
import http.client
import json
import unittest

from application.web_dashboard import WebDashboardSnapshot
from platform_runtime.local_web import LocalWebServer


@dataclass(frozen=True)
class TransferProjection:
    id: str
    name: str
    size: int
    transferred: int
    direction: str
    status: str

    @property
    def progress(self) -> int:
        return int(self.transferred * 100 / self.size)


class LocalWebTests(unittest.TestCase):
    def setUp(self) -> None:
        self.snapshot = WebDashboardSnapshot()
        self.snapshot.update_station(engine="running", snr_db=8.5, bitrate_bps=1200)
        self.snapshot.update_transfers([
            TransferProjection("one", "map.jpg", 100, 50, "incoming", "transferring")
        ])
        self.snapshot.append_log("test event")
        self.server = LocalWebServer(self.snapshot, 0)
        self.server.start()
        self.connection = http.client.HTTPConnection("127.0.0.1", self.server._server.server_port)

    def tearDown(self) -> None:
        self.connection.close()
        self.server.stop()

    def test_dashboard_and_all_read_only_pages_are_available(self) -> None:
        for path in ("/", "/messages", "/transfers", "/station", "/logs"):
            self.connection.request("GET", path)
            response = self.connection.getresponse()
            body = response.read().decode()
            self.assertEqual(response.status, 200)
            self.assertIn("MercurySkyPulse", body)
            self.assertEqual(response.getheader("Cache-Control"), "no-store")

    def test_json_api_contains_plain_snapshot_values(self) -> None:
        self.connection.request("GET", "/api/dashboard")
        response = self.connection.getresponse()
        payload = json.loads(response.read())
        self.assertEqual(payload["station"]["snr_db"], 8.5)
        self.assertEqual(payload["transfers"][0]["progress"], 50)
        self.assertTrue(any("test event" in line for line in payload["logs"]))
        self.connection.request("GET", "/api/plugins")
        response = self.connection.getresponse()
        self.assertEqual(json.loads(response.read()), [])

    def test_mutation_methods_are_rejected(self) -> None:
        self.connection.request("POST", "/messages", body=b"message=not-allowed")
        response = self.connection.getresponse()
        response.read()
        self.assertEqual(response.status, 405)
        self.assertEqual(response.getheader("Allow"), "GET, HEAD")

    def test_unknown_routes_are_not_served(self) -> None:
        self.connection.request("GET", "/../private")
        response = self.connection.getresponse()
        response.read()
        self.assertEqual(response.status, 404)


if __name__ == "__main__":
    unittest.main()

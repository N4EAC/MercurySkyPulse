import unittest

from PySide6.QtCore import QObject, Signal

from application.ping import PingService
from application_protocol.messaging import ChatEnvelope
from application.modem import ModemStatus


class FakePingClient(QObject):
    ping_event_received = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.sent = []

    def send_file_event(self, kind, event_id, timestamp, **values):
        self.sent.append((kind, event_id, timestamp, values))


class Clock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self):
        return self.value


class PingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = FakePingClient()
        self.clock = Clock()
        self.service = PingService(
            self.client, clock=self.clock, auto_timeout=False
        )

    def test_request_returns_rtt_and_local_remote_metrics(self) -> None:
        self.service.update_status(
            ModemStatus(bitrate_bps=600, snr_db=3.5, sync=True, modem_mode="ARQ")
        )
        results = []
        self.service.result_received.connect(results.append)
        self.service.ping()
        ping_id = self.client.sent[0][1]
        self.clock.value += 0.245
        self.client.ping_event_received.emit(
            ChatEnvelope(
                "ping_response", ping_id, "now",
                values={"snr_db": 8.25, "bitrate_bps": 1200, "modem_mode": "ARQ"},
            )
        )
        result = results[0]
        self.assertAlmostEqual(result.rtt_ms, 245.0)
        self.assertEqual(result.local_snr_db, 3.5)
        self.assertEqual(result.remote_snr_db, 8.25)
        self.assertEqual(result.bitrate_bps, 1200)
        self.assertEqual(result.modem_mode, "ARQ")

    def test_incoming_request_returns_latest_modem_snapshot(self) -> None:
        self.service.update_status(
            ModemStatus(bitrate_bps=2400, snr_db=9.75, sync=True, modem_mode="DATAC3")
        )
        self.client.ping_event_received.emit(
            ChatEnvelope("ping_request", "remote-id", "now")
        )
        response = self.client.sent[0]
        self.assertEqual(response[0], "ping_response")
        self.assertEqual(response[1], "remote-id")
        self.assertEqual(response[3]["snr_db"], 9.75)
        self.assertEqual(response[3]["bitrate_bps"], 2400)
        self.assertEqual(response[3]["modem_mode"], "DATAC3")

    def test_timeout_clears_pending_request(self) -> None:
        errors = []
        self.service.error_received.connect(errors.append)
        self.service.ping()
        self.service._timeout()
        self.assertIsNone(self.service._pending_id)
        self.assertEqual(errors[-1], "Ping timed out")

    def test_invalid_response_is_rejected(self) -> None:
        errors = []
        self.service.error_received.connect(errors.append)
        self.service.ping()
        ping_id = self.client.sent[0][1]
        self.client.ping_event_received.emit(
            ChatEnvelope(
                "ping_response", ping_id, "now",
                values={"snr_db": "nan", "bitrate_bps": -1, "modem_mode": ""},
            )
        )
        self.assertTrue(errors[-1].startswith("Invalid ping response"))


if __name__ == "__main__":
    unittest.main()

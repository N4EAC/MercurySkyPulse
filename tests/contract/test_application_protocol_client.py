from __future__ import annotations

from datetime import UTC, datetime
import unittest

from PySide6.QtCore import QObject, Signal

from application_protocol.client import ApplicationMessagingClient
from application_protocol.messaging import encode_ack, encode_event, encode_message


class FakeByteTransport(QObject):
    state_changed = Signal(str)
    control_event = Signal(str)
    session_connected = Signal(str, str, int)
    session_disconnected = Signal()
    data_received = Signal(bytes)
    error_received = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.controls = []
        self.writes = []
        self.started = False

    def start(self): self.started = True
    def stop(self): self.started = False
    def send_control(self, command): self.controls.append(command)
    def write(self, payload): self.writes.append(payload)
    def write_ready(self): return True


class ApplicationProtocolClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.transport = FakeByteTransport()
        self.client = ApplicationMessagingClient(self.transport)
        self.now = datetime.now(UTC).isoformat()

    def test_station_commands_are_normalized_above_transport(self) -> None:
        states = []
        self.client.state_changed.connect(states.append)
        self.client.connect_station("n0call", "k1abc")
        self.assertEqual(self.transport.controls,
                         ["MYCALL N0CALL", "LISTEN ON", "CONNECT N0CALL K1ABC"])
        self.assertEqual(states, ["linking"])

    def test_transport_receives_only_encoded_opaque_bytes(self) -> None:
        self.client.send_message("message-1", self.now, "hello")
        self.assertIsInstance(self.transport.writes[0], bytes)
        self.assertTrue(self.transport.writes[0].startswith(b"MSP1"))

    def test_incoming_message_is_demultiplexed_and_acknowledged(self) -> None:
        received = []
        self.client.message_received.connect(received.append)
        self.transport.data_received.emit(encode_message("incoming", self.now, "hello"))
        self.assertEqual(received[0].text, "hello")
        self.assertTrue(self.transport.writes[-1].startswith(b"MSP1"))

    def test_feature_events_are_routed_above_mercury_transport(self) -> None:
        files, bbs, pings = [], [], []
        self.client.file_event_received.connect(files.append)
        self.client.bbs_event_received.connect(bbs.append)
        self.client.ping_event_received.connect(pings.append)
        frames = (
            encode_event("file_pause", "file", self.now),
            encode_event("bbs_file_request", "bbs", self.now),
            encode_event("ping_request", "ping", self.now),
        )
        self.transport.data_received.emit(b"".join(frames))
        self.assertEqual([item.kind for item in files], ["file_pause"])
        self.assertEqual([item.kind for item in bbs], ["bbs_file_request"])
        self.assertEqual([item.kind for item in pings], ["ping_request"])

    def test_ack_is_protocol_data_not_a_mercury_command(self) -> None:
        delivered = []
        self.client.message_delivered.connect(delivered.append)
        self.transport.data_received.emit(encode_ack("sent", self.now))
        self.assertEqual(delivered, ["sent"])
        self.assertEqual(self.transport.controls, [])


if __name__ == "__main__":
    unittest.main()

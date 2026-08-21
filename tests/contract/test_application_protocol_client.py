from __future__ import annotations

from datetime import UTC, datetime
import unittest

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from application_protocol.client import ApplicationMessagingClient
from application_protocol.messaging import FrameDecoder, encode_ack, encode_event, encode_message


class FakeByteTransport(QObject):
    state_changed = Signal(str)
    control_event = Signal(str)
    session_connected = Signal(str, str, int)
    session_disconnected = Signal()
    data_received = Signal(bytes)
    error_received = Signal(str)
    queued_bytes_changed = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.controls = []
        self.writes = []
        self.started = False
        self.write_error = None

    def start(self): self.started = True
    def stop(self): self.started = False
    def send_control(self, command): self.controls.append(command)
    def write(self, payload):
        if self.write_error:
            raise self.write_error
        self.writes.append(payload)
    def write_ready(self): return True


class ApplicationProtocolClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.qt_app = QApplication.instance() or QApplication([])

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

    def test_listening_publishes_explicit_state(self) -> None:
        states = []
        self.client.state_changed.connect(states.append)
        self.client.configure_and_listen("n0call")
        self.assertEqual(self.transport.controls, ["MYCALL N0CALL", "LISTEN ON"])
        self.assertEqual(states, ["listening"])

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

    def test_acknowledgement_disconnect_race_is_reported(self) -> None:
        received, errors = [], []
        self.client.message_received.connect(received.append)
        self.client.error_received.connect(errors.append)
        self.transport.write_error = RuntimeError("station link disconnected")
        self.transport.data_received.emit(encode_message("incoming", self.now, "hello"))
        self.assertEqual([item.text for item in received], ["hello"])
        self.assertEqual(
            errors,
            ["Could not acknowledge received message: station link disconnected"],
        )

    def test_feature_events_are_routed_above_mercury_transport(self) -> None:
        files, bbs, pings, presence = [], [], [], []
        self.client.file_event_received.connect(files.append)
        self.client.bbs_event_received.connect(bbs.append)
        self.client.ping_event_received.connect(pings.append)
        self.client.presence_received.connect(presence.append)
        frames = (
            encode_event("file_pause", "file", self.now),
            encode_event("bbs_file_request", "bbs", self.now),
            encode_event("ping_request", "ping", self.now),
            encode_event("presence", "presence", self.now,
                         state="typing", ttl_seconds=45),
        )
        self.transport.data_received.emit(b"".join(frames))
        self.assertEqual([item.kind for item in files], ["file_pause"])
        self.assertEqual([item.kind for item in bbs], ["bbs_file_request"])
        self.assertEqual([item.kind for item in pings], ["ping_request"])
        self.assertEqual([item.kind for item in presence], ["presence"])

    def test_presence_is_encoded_as_opaque_application_data(self) -> None:
        self.client.send_presence("presence-1", self.now, "recording_audio", 20)
        envelope = FrameDecoder().feed(self.transport.writes[-1])[0]
        self.assertEqual(envelope.kind, "presence")
        self.assertEqual(envelope.values["state"], "recording_audio")

    def test_ack_is_protocol_data_not_a_mercury_command(self) -> None:
        delivered = []
        self.client.message_delivered.connect(delivered.append)
        self.transport.data_received.emit(encode_ack("sent", self.now))
        self.assertEqual(delivered, ["sent"])
        self.assertEqual(self.transport.controls, [])

    def test_local_mercury_connection_requires_peer_application_confirmation(self) -> None:
        states, sessions = [], []
        self.client.state_changed.connect(states.append)
        self.client.session_connected.connect(lambda *values: sessions.append(values))

        self.client.connect_station("N0CALL", "K1ABC")
        self.transport.state_changed.emit("connected")
        self.transport.session_connected.emit("N0CALL", "K1ABC", 2300)

        self.assertEqual(states, ["linking", "validating"])
        self.assertEqual(sessions, [])
        probe = FrameDecoder().feed(self.transport.writes[-1])[0]
        self.assertEqual(probe.kind, "session_probe")

        self.transport.data_received.emit(encode_event(
            "session_probe_ack", "ack-1", self.now, probe_id=probe.message_id
        ))
        self.assertEqual(states[-1], "connected")
        self.assertEqual(sessions, [("N0CALL", "K1ABC", 2300)])

    def test_wrong_probe_ack_does_not_validate_session(self) -> None:
        sessions = []
        self.client.session_connected.connect(lambda *values: sessions.append(values))
        self.client.connect_station("N0CALL", "K1ABC")
        self.transport.session_connected.emit("N0CALL", "K1ABC", 2300)
        self.transport.data_received.emit(encode_event(
            "session_probe_ack", "ack-1", self.now, probe_id="wrong"
        ))
        self.assertEqual(sessions, [])

    def test_validation_timeout_disconnects_false_local_connection(self) -> None:
        errors = []
        self.client.error_received.connect(errors.append)
        self.client.connect_station("N0CALL", "K1ABC")
        self.transport.session_connected.emit("N0CALL", "K1ABC", 2300)

        self.client._validation_timed_out()

        self.assertEqual(self.transport.controls[-1], "DISCONNECT")
        self.assertIn("not confirmed", errors[-1])

    def test_unanswered_call_timeout_disconnects_and_reports_error(self) -> None:
        errors = []
        self.client.error_received.connect(errors.append)
        self.client.connect_station("N0CALL", "K1ABC")

        self.client._call_timed_out()

        self.assertEqual(self.transport.controls[-1], "DISCONNECT")
        self.assertIn("60 seconds", errors[-1])

    def test_peer_probe_is_acknowledged_with_matching_identifier(self) -> None:
        sessions = []
        self.client.session_connected.connect(lambda *values: sessions.append(values))
        self.transport.session_connected.emit("K1ABC", "N0CALL", 2300)
        self.assertEqual(self.transport.writes, [])
        self.transport.data_received.emit(encode_event(
            "session_probe", "peer-probe", self.now
        ))
        response = FrameDecoder().feed(self.transport.writes[-1])[0]
        self.assertEqual(response.kind, "session_probe_ack")
        self.assertEqual(response.values["probe_id"], "peer-probe")
        self.assertEqual(sessions, [("K1ABC", "N0CALL", 2300)])

    def test_only_calling_station_initiates_session_probe(self) -> None:
        self.transport.session_connected.emit("K1ABC", "N0CALL", 2300)
        self.assertEqual(self.transport.writes, [])
        self.assertTrue(self.client._validation_timer.isActive())
        self.assertTrue(self.client._validation_maximum_timer.isActive())

    def test_mercury_buffer_progress_extends_no_progress_window(self) -> None:
        self.client.connect_station("N0CALL", "K1ABC")
        self.transport.session_connected.emit("N0CALL", "K1ABC", 2300)
        timer_id = self.client._validation_timer.timerId()
        self.transport.queued_bytes_changed.emit(122)
        self.assertEqual(self.client._validation_queued_bytes, 122)
        self.transport.queued_bytes_changed.emit(100)
        self.assertEqual(self.client._validation_queued_bytes, 100)
        self.assertTrue(self.client._validation_timer.isActive())
        self.assertNotEqual(self.client._validation_timer.timerId(), timer_id)

    def test_hard_validation_deadline_disconnects_even_with_progress(self) -> None:
        errors = []
        self.client.error_received.connect(errors.append)
        self.client.connect_station("N0CALL", "K1ABC")
        self.transport.session_connected.emit("N0CALL", "K1ABC", 2300)
        self.transport.queued_bytes_changed.emit(122)
        self.transport.queued_bytes_changed.emit(100)

        self.client._validation_maximum_timed_out()

        self.assertEqual(self.transport.controls[-1], "DISCONNECT")
        self.assertIn("safety deadline", errors[-1])

    def test_manual_cancel_ignores_late_probe_ack(self) -> None:
        sessions = []
        self.client.session_connected.connect(lambda *values: sessions.append(values))
        self.client.connect_station("N0CALL", "K1ABC")
        self.transport.session_connected.emit("N0CALL", "K1ABC", 2300)
        probe = FrameDecoder().feed(self.transport.writes[-1])[0]

        self.client.disconnect_station()
        self.transport.data_received.emit(encode_event(
            "session_probe_ack", "late", self.now, probe_id=probe.message_id
        ))

        self.assertEqual(sessions, [])
        self.assertEqual(self.transport.controls[-1], "DISCONNECT")

    def test_new_call_can_start_after_previous_call_timeout(self) -> None:
        self.client.connect_station("N0CALL", "K1ABC")
        self.client._call_timed_out()
        self.client.connect_station("N0CALL", "K2XYZ")
        self.assertEqual(self.transport.controls[-1], "CONNECT N0CALL K2XYZ")
        self.assertTrue(self.client._call_timer.isActive())

    def test_unanswered_disconnect_restores_application_ready_state(self) -> None:
        states = []
        def observe(state: str) -> None:
            states.append(state)
            if state == "ready":
                self.client.configure_and_listen("N0CALL")
        self.client.state_changed.connect(observe)
        self.client.connect_station("N0CALL", "K1ABC")

        # Mercury can emit DISCONNECTED without a preceding CONNECTED, leaving
        # its raw transport state unchanged at ready.
        self.transport.session_disconnected.emit()

        self.assertEqual(states, ["linking", "ready", "listening"])
        self.assertEqual(self.transport.controls[-2:], ["MYCALL N0CALL", "LISTEN ON"])

    def test_successful_disconnect_does_not_publish_ready_twice(self) -> None:
        states = []
        self.client.state_changed.connect(states.append)
        self.transport.state_changed.emit("ready")
        self.transport.state_changed.emit("connected")
        self.client.connect_station("N0CALL", "K1ABC")
        self.transport.session_connected.emit("N0CALL", "K1ABC", 2300)
        self.transport.state_changed.emit("ready")
        self.transport.session_disconnected.emit()

        self.assertEqual(states.count("ready"), 2)


if __name__ == "__main__":
    unittest.main()

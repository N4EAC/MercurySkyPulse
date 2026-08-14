from __future__ import annotations

from tempfile import TemporaryDirectory
from pathlib import Path
import unittest

from PySide6.QtCore import QObject, Signal

from application.voice_message import MAX_VOICE_BYTES, VoiceMessageService


class FakeClient(QObject):
    session_connected = Signal(str, str, int)
    session_disconnected = Signal()
    voice_event_received = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.events = []

    def send_file_event(self, kind, event_id, timestamp, **values):
        self.events.append((kind, event_id, values))

    def file_write_ready(self):
        return True


class Envelope:
    def __init__(self, kind, message_id="event", **values):
        self.kind, self.message_id, self.values = kind, message_id, values


class Transfer:
    def __init__(self, status): self.status = status


class VoiceMessageTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.client = FakeClient()
        self.service = VoiceMessageService(self.client, Path(self.temp.name))

    def tearDown(self):
        self.temp.cleanup()

    def make_available(self):
        self.client.session_connected.emit("N4EAC", "K1ABC", 2500)
        self.client.voice_event_received.emit(Envelope(
            "voice_capability", protocol=1, mime_types=["audio/mp4"], ack=True,
            maximum_seconds=10, maximum_bytes=MAX_VOICE_BYTES,
        ))
        for _ in range(3): self.service.set_modem_bitrate(600)

    def test_requires_connection_capability_and_sustained_bitrate(self):
        self.assertFalse(self.service.availability()[0])
        self.client.session_connected.emit("N4EAC", "K1ABC", 2500)
        self.assertEqual(self.client.events[-1][0], "voice_capability")
        self.client.voice_event_received.emit(Envelope(
            "voice_capability", protocol=1, mime_types=["audio/mp4"], ack=True
        ))
        self.service.set_modem_bitrate(600)
        self.service.set_modem_bitrate(600)
        self.assertFalse(self.service.availability()[0])
        self.service.set_modem_bitrate(600)
        self.assertTrue(self.service.availability()[0])

    def test_capability_request_gets_one_bounded_ack_without_echo(self):
        self.client.session_connected.emit("N4EAC", "K1ABC", 2500)
        self.client.voice_event_received.emit(Envelope(
            "voice_capability", protocol=1, mime_types=["audio/mp4"], ack=False
        ))
        self.assertEqual([event[0] for event in self.client.events],
                         ["voice_capability", "voice_capability"])
        self.assertTrue(self.client.events[-1][2]["ack"])
        self.client.voice_event_received.emit(Envelope(
            "voice_capability", protocol=1, mime_types=["audio/mp4"], ack=False
        ))
        self.assertEqual(len(self.client.events), 2)

    def test_paused_file_blocks_voice(self):
        self.make_available()
        self.service.set_file_transfers([Transfer("paused")])
        self.assertFalse(self.service.availability()[0])
        self.assertIn("file transfer", self.service.availability()[1])

    def test_oversized_recording_is_rejected(self):
        self.make_available()
        path = Path(self.temp.name) / "large.m4a"
        path.write_bytes(b"x" * (MAX_VOICE_BYTES + 1))
        self.assertFalse(self.service.send_recording(str(path), "audio/mp4"))

    def test_disconnect_deletes_incomplete_session_artifact(self):
        self.make_available()
        path = Path(self.temp.name) / "draft.m4a"
        path.write_bytes(b"voice")
        self.assertTrue(self.service.send_recording(str(path), "audio/mp4"))
        self.assertTrue(self.service.transfer_busy())
        self.client.session_disconnected.emit()
        self.assertFalse(path.exists())
        self.assertFalse(self.service.availability()[0])

    def test_invalid_incoming_offer_never_creates_file(self):
        errors = []
        self.service.error_received.connect(errors.append)
        self.client.voice_event_received.emit(Envelope(
            "voice_offer", size=MAX_VOICE_BYTES + 1, sha256="0" * 64,
            mime="audio/mp4", duration_ms=10_000,
        ))
        self.assertTrue(errors)
        self.assertEqual(list(Path(self.temp.name).iterdir()), [])


if __name__ == "__main__":
    unittest.main()

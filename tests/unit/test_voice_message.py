from __future__ import annotations

import base64
import hashlib
from tempfile import TemporaryDirectory
from pathlib import Path
import unittest

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from application.voice_message import (
    MAX_VOICE_BYTES, VOICE_CHUNK_BYTES, VoiceMessageService,
)


class FakeClient(QObject):
    session_connected = Signal(str, str, int)
    session_disconnected = Signal()
    voice_event_received = Signal(object)
    queued_bytes_changed = Signal(int)

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
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.client = FakeClient()
        self.service = VoiceMessageService(self.client, Path(self.temp.name))

    def tearDown(self):
        self.temp.cleanup()

    def make_available(self):
        self.client.session_connected.emit("N4EAC", "K1ABC", 2500)
        self.client.voice_event_received.emit(Envelope(
            "voice_capability", protocol=2, mime_types=["audio/mp4"], ack=True,
            maximum_seconds=10, maximum_bytes=MAX_VOICE_BYTES, link_ready=True,
        ))
        for _ in range(3): self.service.set_modem_bitrate(600)

    def test_requires_connection_capability_and_sustained_bitrate(self):
        self.assertFalse(self.service.availability()[0])
        self.client.session_connected.emit("N4EAC", "K1ABC", 2500)
        self.assertEqual(self.client.events[-1][0], "voice_capability")
        self.client.voice_event_received.emit(Envelope(
            "voice_capability", protocol=2, mime_types=["audio/mp4"], ack=True,
            link_ready=True,
        ))
        self.service.set_modem_bitrate(600)
        self.service.set_modem_bitrate(600)
        self.assertFalse(self.service.availability()[0])
        self.service.set_modem_bitrate(600)
        self.assertTrue(self.service.availability()[0])

    def test_capability_request_gets_one_bounded_ack_without_echo(self):
        self.client.session_connected.emit("N4EAC", "K1ABC", 2500)
        self.client.voice_event_received.emit(Envelope(
            "voice_capability", protocol=2, mime_types=["audio/mp4"], ack=False
        ))
        self.assertEqual([event[0] for event in self.client.events],
                         ["voice_capability", "voice_capability"])
        self.assertTrue(self.client.events[-1][2]["ack"])
        self.client.voice_event_received.emit(Envelope(
            "voice_capability", protocol=2, mime_types=["audio/mp4"], ack=False
        ))
        self.assertEqual(len(self.client.events), 2)

    def test_voice_requires_both_stations_to_report_sustained_bitrate(self):
        self.client.session_connected.emit("N4EAC", "K1ABC", 2500)
        self.client.voice_event_received.emit(Envelope(
            "voice_capability", protocol=2, mime_types=["audio/mp4"], ack=True,
            link_ready=False,
        ))
        for _ in range(3):
            self.service.set_modem_bitrate(600)
        self.assertFalse(self.service.availability()[0])
        self.assertIn("receiving station", self.service.availability()[1])
        readiness_events = [
            event for event in self.client.events
            if event[0] == "voice_capability" and event[2].get("link_ready")
        ]
        self.assertEqual(len(readiness_events), 1)

        self.client.voice_event_received.emit(Envelope(
            "voice_capability", protocol=2, mime_types=["audio/mp4"], ack=True,
            link_ready=True, bitrate_bps=700,
        ))
        self.assertTrue(self.service.availability()[0])

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

    def test_sender_retains_a_separate_playable_copy(self):
        self.make_available()
        draft = Path(self.temp.name) / "draft.m4a"
        draft.write_bytes(b"voice")
        updates = []
        self.service.messages_changed.connect(lambda values: updates.append(values[-1]))

        self.assertTrue(self.service.send_recording(str(draft), "audio/mp4"))
        message_id = updates[-1].id
        self.client.voice_event_received.emit(Envelope(
            "voice_result", message_id, result="delivered"
        ))

        retained = Path(updates[-1].path)
        self.assertNotEqual(retained, draft)
        self.assertEqual(retained.read_bytes(), b"voice")
        draft.unlink()
        self.assertEqual(retained.read_bytes(), b"voice")

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

    def test_sender_waits_for_receiver_ack_and_mercury_low_water(self):
        self.make_available()
        self.client.queued_bytes_changed.emit(500)
        path = Path(self.temp.name) / "draft.m4a"
        path.write_bytes(b"v" * (VOICE_CHUNK_BYTES * 2))
        updates = []
        self.service.messages_changed.connect(lambda values: updates.append(values[-1]))
        self.assertTrue(self.service.send_recording(str(path), "audio/mp4"))
        message_id = updates[-1].id
        self.assertEqual(updates[-1].status, "queued")
        self.assertFalse(any(event[0] == "voice_offer" for event in self.client.events))

        self.client.queued_bytes_changed.emit(0)
        self.assertEqual(updates[-1].status, "offered")
        self.assertEqual(self.client.events[-1][0], "voice_offer")

        self.client.voice_event_received.emit(Envelope("voice_accept", message_id))
        chunks = [event for event in self.client.events if event[0] == "voice_chunk"]
        self.assertEqual(len(chunks), 1)
        self.assertEqual(updates[-1].transferred, 0)

        self.client.queued_bytes_changed.emit(2_000)
        self.client.voice_event_received.emit(Envelope(
            "voice_chunk_ack", message_id, offset=VOICE_CHUNK_BYTES
        ))
        chunks = [event for event in self.client.events if event[0] == "voice_chunk"]
        self.assertEqual(len(chunks), 1)
        self.assertEqual(updates[-1].transferred, VOICE_CHUNK_BYTES)

        self.client.queued_bytes_changed.emit(0)
        chunks = [event for event in self.client.events if event[0] == "voice_chunk"]
        self.assertEqual(len(chunks), 2)

    def test_peer_timeout_starts_only_after_mercury_queue_drains(self):
        self.make_available()
        path = Path(self.temp.name) / "draft.m4a"
        path.write_bytes(b"voice")
        self.assertTrue(self.service.send_recording(str(path), "audio/mp4"))
        self.assertTrue(self.service._response_timer.isActive())

        self.client.queued_bytes_changed.emit(400)
        self.assertFalse(self.service._response_timer.isActive())

        self.client.queued_bytes_changed.emit(0)
        self.assertTrue(self.service._response_timer.isActive())

    def test_receiver_reports_progress_with_existing_chunk_ack(self):
        payload = b"voice"
        checksum = hashlib.sha256(payload).hexdigest()
        updates = []
        self.service.messages_changed.connect(lambda values: updates.append(values[-1]))
        for _ in range(3):
            self.service.set_modem_bitrate(600)
        self.client.voice_event_received.emit(Envelope(
            "voice_offer", "voice-id", size=len(payload), sha256=checksum,
            mime="audio/mp4", duration_ms=1_000,
        ))
        self.assertEqual(updates[-1].status, "receiving")
        self.client.voice_event_received.emit(Envelope(
            "voice_chunk", "voice-id", offset=0,
            data=base64.b64encode(payload).decode("ascii"),
        ))
        self.assertEqual(updates[-1].transferred, len(payload))
        self.assertEqual(self.client.events[-1][0], "voice_chunk_ack")
        self.assertEqual(self.client.events[-1][2]["offset"], len(payload))

    def test_receiver_rejects_voice_when_its_inbound_link_is_poor(self):
        payload = b"voice"
        self.service.set_modem_bitrate(87)
        self.client.voice_event_received.emit(Envelope(
            "voice_offer", "voice-id", size=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(), mime="audio/mp4",
            duration_ms=1_000,
        ))
        self.assertEqual(self.client.events[-1][0], "voice_result")
        self.assertEqual(self.client.events[-1][2]["result"], "link-poor")
        self.assertFalse(self.service.transfer_busy())

    def test_late_result_does_not_change_terminal_failure(self):
        self.make_available()
        path = Path(self.temp.name) / "draft.m4a"
        path.write_bytes(b"voice")
        updates = []
        self.service.messages_changed.connect(lambda values: updates.append(values[-1]))
        self.assertTrue(self.service.send_recording(str(path), "audio/mp4"))
        message_id = updates[-1].id
        self.service._response_timeout()
        self.assertEqual(updates[-1].status, "failed")

        self.client.voice_event_received.emit(Envelope(
            "voice_result", message_id, result="busy"
        ))
        self.assertEqual(updates[-1].status, "failed")


if __name__ == "__main__":
    unittest.main()

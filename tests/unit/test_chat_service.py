"""Automatic incoming ARQ listening behavior."""

from __future__ import annotations

from tempfile import TemporaryDirectory
import unittest

from PySide6.QtCore import QObject, Signal

from application.chat_service import ChatService
from persistence.chat_repository import ChatRepository


class FakeMessagingClient(QObject):
    state_changed = Signal(str)
    session_connected = Signal(str, str, int)
    session_disconnected = Signal()
    message_received = Signal(object)
    message_sent = Signal(str)
    message_delivered = Signal(str)
    presence_received = Signal(object)
    error_received = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.ready = False
        self.listen_calls: list[str] = []
        self.presence_calls: list[tuple[str, int]] = []

    @staticmethod
    def normalize_callsign(value: str) -> str:
        call = value.strip().upper()
        if not call or " " in call:
            raise ValueError("invalid callsign")
        return call

    def configure_and_listen(self, callsign: str) -> None:
        if not self.ready:
            raise RuntimeError("TNC is not ready")
        self.listen_calls.append(callsign)
        self.state_changed.emit("listening")

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def send_presence(self, _event_id: str, _timestamp: str, state: str,
                      ttl_seconds: int) -> None:
        self.presence_calls.append((state, ttl_seconds))


class ChatServiceAutoListenTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.client = FakeMessagingClient()
        self.repository = ChatRepository(f"{self.temp.name}/chat.sqlite3")
        self.service = ChatService(self.client, self.repository)

    def tearDown(self) -> None:
        self.repository.close()
        self.temp.cleanup()

    def test_saved_identity_listens_when_tnc_becomes_ready(self) -> None:
        identities = []
        self.service.listening_as_changed.connect(identities.append)
        self.service.configure_auto_listen("n4eac")
        self.assertEqual(self.client.listen_calls, [])

        self.client.ready = True
        self.client.state_changed.emit("ready")

        self.assertEqual(self.client.listen_calls, ["N4EAC"])
        self.assertEqual(identities, ["N4EAC"])

    def test_listening_is_rearmed_after_session_disconnect_returns_ready(self) -> None:
        self.client.ready = True
        self.client.state_changed.emit("ready")
        self.service.configure_auto_listen("N4EAC")
        self.client.state_changed.emit("connected")
        self.client.state_changed.emit("ready")
        self.assertEqual(self.client.listen_calls, ["N4EAC", "N4EAC"])

    def test_callsign_change_is_deferred_during_active_session(self) -> None:
        self.client.ready = True
        self.client.state_changed.emit("ready")
        self.service.configure_auto_listen("N4EAC")
        self.client.state_changed.emit("connected")

        self.service.configure_auto_listen("K1NEW")
        self.assertEqual(self.client.listen_calls, ["N4EAC"])

        self.client.state_changed.emit("ready")
        self.assertEqual(self.client.listen_calls, ["N4EAC", "K1NEW"])

    def test_delete_conversation_clears_active_history(self) -> None:
        conversation = self.repository.get_or_create_conversation(
            "N4EAC", "K1ABC", "2026-08-13T12:00:00+00:00"
        )
        self.service.select_conversation(conversation.id)
        messages = []
        self.service.messages_changed.connect(messages.append)
        self.service.delete_conversation(conversation.id)
        self.assertEqual(self.repository.list_conversations(), [])
        self.assertIsNone(self.service.active)
        self.assertEqual(messages[-1], [])

    def test_presence_only_sends_during_connected_session(self) -> None:
        self.assertFalse(self.service.send_presence("typing"))
        self.client.state_changed.emit("connected")
        self.assertTrue(self.service.send_presence("typing"))
        self.assertEqual(self.client.presence_calls, [("typing", 45)])

    def test_presence_is_suppressed_during_bulk_transfer(self) -> None:
        self.client.state_changed.emit("connected")
        self.service.set_bulk_busy_check(lambda: True)
        self.assertFalse(self.service.send_presence("recording_audio"))
        self.assertEqual(self.client.presence_calls, [])

    def test_text_is_suppressed_during_bulk_transfer(self) -> None:
        errors = []
        self.service.error_received.connect(errors.append)
        conversation = self.repository.get_or_create_conversation(
            "N4EAC", "K1ABC", "2026-08-14T12:00:00+00:00"
        )
        self.service.select_conversation(conversation.id)
        self.service.set_bulk_busy_check(lambda: True)

        self.assertFalse(self.service.send_text("wait for voice"))
        self.assertIn("active voice or file transfer", errors[-1])

    def test_invalid_remote_presence_is_ignored_and_disconnect_clears_it(self) -> None:
        class Envelope:
            values = {"state": "typing", "ttl_seconds": 999}

        received = []
        self.service.peer_presence_changed.connect(
            lambda state, ttl: received.append((state, ttl))
        )
        self.client.presence_received.emit(Envelope())
        self.assertEqual(received, [])
        self.client.session_disconnected.emit()
        self.assertEqual(received, [("idle", 0)])


if __name__ == "__main__":
    unittest.main()

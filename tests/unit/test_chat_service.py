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
    error_received = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.ready = False
        self.listen_calls: list[str] = []

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


if __name__ == "__main__":
    unittest.main()

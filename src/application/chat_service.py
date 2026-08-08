"""Use-case coordinator for station-to-station text chat."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from PySide6.QtCore import QObject, Signal

from persistence.chat_repository import ChatRepository

from .messaging import ChatMessage, Conversation, MessageDirection, MessageStatus


class ChatService(QObject):
    state_changed = Signal(str)
    conversations_changed = Signal(object)
    messages_changed = Signal(object)
    active_conversation_changed = Signal(object)
    error_received = Signal(str)

    def __init__(self, client, repository: ChatRepository, parent=None) -> None:
        super().__init__(parent)
        self.client = client
        self.repository = repository
        self.local_call = ""
        self.active: Conversation | None = None
        client.state_changed.connect(self.state_changed)
        client.session_connected.connect(self._on_session_connected)
        client.session_disconnected.connect(self._on_session_disconnected)
        client.message_received.connect(self._on_message_received)
        client.message_sent.connect(
            lambda message_id: self._set_status(message_id, MessageStatus.SENT)
        )
        client.message_delivered.connect(
            lambda message_id: self._set_status(message_id, MessageStatus.DELIVERED)
        )
        client.error_received.connect(self.error_received)

    def start(self) -> None:
        self.client.start()
        self._publish_conversations()

    def close(self) -> None:
        self.client.stop()
        self.repository.close()

    def listen(self, local_call: str) -> None:
        try:
            self.local_call = self.client.normalize_callsign(local_call)
            self.client.configure_and_listen(self.local_call)
        except (ValueError, RuntimeError) as error:
            self.error_received.emit(str(error))

    def connect_station(self, local_call: str, remote_call: str) -> None:
        try:
            self.local_call = self.client.normalize_callsign(local_call)
            remote = self.client.normalize_callsign(remote_call)
            self._activate(self.local_call, remote)
            self.client.connect_station(self.local_call, remote)
        except (ValueError, RuntimeError) as error:
            self.error_received.emit(str(error))

    def disconnect_station(self) -> None:
        try:
            self.client.disconnect_station()
        except RuntimeError as error:
            self.error_received.emit(str(error))

    def select_conversation(self, conversation_id: int) -> None:
        self.active = next(
            (item for item in self.repository.list_conversations() if item.id == conversation_id),
            None,
        )
        if self.active:
            self.active_conversation_changed.emit(self.active)
            self._publish_messages()

    def send_text(self, text: str) -> bool:
        body = text.strip()
        if not body:
            return False
        if len(body) > 2048:
            self.error_received.emit("Messages are limited to 2048 characters")
            return False
        if not self.active:
            self.error_received.emit("Select or connect to a station first")
            return False
        message = ChatMessage(
            id=str(uuid4()),
            conversation_id=self.active.id,
            direction=MessageDirection.OUTGOING,
            body=body,
            sent_at=self._now(),
            status=MessageStatus.QUEUED,
        )
        self.repository.save_message(message)
        self._publish_all()
        try:
            self.client.send_message(message.id, message.sent_at, body)
        except RuntimeError as error:
            self._set_status(message.id, MessageStatus.FAILED)
            self.error_received.emit(str(error))
            return False
        return True

    def _on_session_connected(self, source: str, destination: str, _bandwidth: int) -> None:
        source = source.upper()
        destination = destination.upper()
        if self.local_call == source:
            remote = destination
        elif self.local_call == destination:
            remote = source
        else:
            self.local_call = destination
            remote = source
        self._activate(self.local_call, remote)

    def _on_session_disconnected(self) -> None:
        if self.active:
            self.repository.fail_unsettled(self.active.id)
            self._publish_messages()

    def _on_message_received(self, envelope) -> None:
        if not self.active:
            self.error_received.emit("Received text without an identified station session")
            return
        self.repository.save_message(
            ChatMessage(
                id=envelope.message_id,
                conversation_id=self.active.id,
                direction=MessageDirection.INCOMING,
                body=envelope.text,
                sent_at=envelope.timestamp,
                status=MessageStatus.RECEIVED,
            )
        )
        self._publish_all()

    def _activate(self, local_call: str, remote_call: str) -> None:
        self.active = self.repository.get_or_create_conversation(
            local_call, remote_call, self._now()
        )
        self.active_conversation_changed.emit(self.active)
        self._publish_all()

    def _set_status(self, message_id: str, status: MessageStatus) -> None:
        self.repository.update_status(message_id, status)
        self._publish_messages()

    def _publish_all(self) -> None:
        self._publish_conversations()
        self._publish_messages()

    def _publish_conversations(self) -> None:
        self.conversations_changed.emit(self.repository.list_conversations())

    def _publish_messages(self) -> None:
        if self.active:
            self.messages_changed.emit(self.repository.list_messages(self.active.id))

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

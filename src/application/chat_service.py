"""Use-case coordinator for station-to-station text chat."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
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
    listening_as_changed = Signal(str)
    peer_presence_changed = Signal(str, int)

    def __init__(self, client, repository: ChatRepository, parent=None) -> None:
        super().__init__(parent)
        self.client = client
        self.repository = repository
        self.local_call = ""
        self._auto_listen_call = ""
        self._client_state = "disconnected"
        self.active: Conversation | None = None
        client.state_changed.connect(self._on_client_state)
        client.session_connected.connect(self._on_session_connected)
        client.session_disconnected.connect(self._on_session_disconnected)
        client.message_received.connect(self._on_message_received)
        client.message_sent.connect(
            lambda message_id: self._set_status(message_id, MessageStatus.SENT)
        )
        client.message_delivered.connect(
            lambda message_id: self._set_status(message_id, MessageStatus.DELIVERED)
        )
        client.presence_received.connect(self._on_presence_received)
        client.error_received.connect(self.error_received)

    def start(self) -> None:
        self.client.start()
        self.repository.delete_empty_conversations_before(
            (datetime.now(UTC) - timedelta(days=30)).isoformat()
        )
        self._publish_conversations()

    def close(self) -> None:
        self.client.stop()
        self.repository.close()

    def listen(self, local_call: str) -> None:
        try:
            self.local_call = self.client.normalize_callsign(local_call)
            self._auto_listen_call = self.local_call
            self._arm_listening(report_error=True)
        except (ValueError, RuntimeError) as error:
            self.error_received.emit(str(error))

    def configure_auto_listen(self, local_call: str) -> None:
        """Remember a validated identity and listen whenever the TNC is ready."""
        try:
            self._auto_listen_call = self.client.normalize_callsign(local_call)
            self.local_call = self._auto_listen_call
        except ValueError as error:
            self.error_received.emit(str(error))
            return
        self._arm_listening(report_error=False)

    def connect_station(self, local_call: str, remote_call: str) -> None:
        try:
            self.local_call = self.client.normalize_callsign(local_call)
            self._auto_listen_call = self.local_call
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

    def delete_conversation(self, conversation_id: int) -> None:
        conversation = next(
            (item for item in self.repository.list_conversations()
             if item.id == int(conversation_id)),
            None,
        )
        if conversation is None:
            return
        if self.active and self.active.id == conversation.id and self._client_state == "connected":
            self.error_received.emit("Disconnect before deleting the active conversation")
            return
        self.repository.delete_conversation(conversation.id)
        if self.active and self.active.id == conversation.id:
            self.active = None
            self.messages_changed.emit([])
        self._publish_conversations()

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

    def send_presence(self, state: str) -> bool:
        """Send one bounded, disposable presence transition over an active ARQ session."""
        ttl_by_state = {"typing": 45, "recording_audio": 20, "idle": 0}
        if state not in ttl_by_state or self._client_state != "connected":
            return False
        try:
            self.client.send_presence(
                str(uuid4()), self._now(), state, ttl_by_state[state]
            )
        except RuntimeError:
            # Presence is deliberately best-effort: never distract the operator or
            # retry stale activity over a constrained RF link.
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
        self.peer_presence_changed.emit("idle", 0)
        if self.active:
            self.repository.fail_unsettled(self.active.id)
            self._publish_messages()

    def _on_presence_received(self, envelope) -> None:
        values = envelope.values or {}
        state = values.get("state")
        ttl = values.get("ttl_seconds")
        limits = {"typing": 45, "recording_audio": 20, "idle": 0}
        if state not in limits or isinstance(ttl, bool) or not isinstance(ttl, int):
            return
        if ttl < 0 or ttl > limits[state]:
            return
        self.peer_presence_changed.emit(state, ttl)

    def _on_client_state(self, state: str) -> None:
        self._client_state = state
        self.state_changed.emit(state)
        if state == "ready":
            self._arm_listening(report_error=False)

    def _arm_listening(self, report_error: bool) -> bool:
        if not self._auto_listen_call:
            return False
        if self._client_state not in {"ready", "listening"}:
            if report_error:
                self.error_received.emit(
                    "TNC is not ready to listen; wait for Mercury or disconnect the active station"
                )
            return False
        try:
            self.client.configure_and_listen(self._auto_listen_call)
        except RuntimeError as error:
            if report_error:
                self.error_received.emit(str(error))
            return False
        self.listening_as_changed.emit(self._auto_listen_call)
        return True

    def _on_message_received(self, envelope) -> None:
        self.peer_presence_changed.emit("idle", 0)
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

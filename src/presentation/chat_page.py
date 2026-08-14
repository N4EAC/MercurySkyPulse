"""Station-to-station text chat page."""

from __future__ import annotations

from datetime import UTC, datetime

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFormLayout,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QProgressBar,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from application.messaging import (
    ChatMessage, Conversation, MessageDirection, MessageStatus,
)
from .time_format import format_utc_timestamp


class ChatPage(QWidget):
    listen_requested = Signal(str)
    connect_requested = Signal(str, str)
    disconnect_requested = Signal()
    send_requested = Signal(str)
    file_requested = Signal(str)
    transfer_pause_requested = Signal(str)
    transfer_resume_requested = Signal(str)
    transfer_folder_requested = Signal(str)
    conversation_selected = Signal(int)
    cq_requested = Signal()
    answer_cq_requested = Signal(str)
    weather_requested = Signal()
    conversation_delete_requested = Signal(int)
    presence_requested = Signal(str)
    voice_record_requested = Signal()
    voice_stop_requested = Signal()
    voice_send_requested = Signal()
    voice_play_requested = Signal(str)
    voice_discard_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._conversation_ids: list[int] = []
        root = QVBoxLayout(self)
        title = QLabel("Station Chat")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        controls = QFrame()
        controls.setObjectName("Card")
        control_row = QHBoxLayout(controls)
        form = QFormLayout()
        self.local_call = QLineEdit()
        self.local_call.setPlaceholderText("N0CALL")
        self.local_call.setMaxLength(15)
        self.remote_call = QLineEdit()
        self.remote_call.setPlaceholderText("REMOTE")
        self.remote_call.setMaxLength(15)
        form.addRow("My callsign", self.local_call)
        form.addRow("Station", self.remote_call)
        control_row.addLayout(form, 1)
        self.listen_button = QPushButton("Listen")
        self.connect_button = QPushButton("Connect")
        self.connect_button.setObjectName("PrimaryButton")
        self.disconnect_button = QPushButton("Disconnect")
        control_row.addWidget(self.listen_button)
        control_row.addWidget(self.connect_button)
        control_row.addWidget(self.disconnect_button)
        self.link_state = QLabel("TNC: disconnected")
        self.link_state.setObjectName("StatusPill")
        control_row.addWidget(self.link_state)
        self.listening_identity = QLabel("Listening as: not configured")
        self.listening_identity.setObjectName("Muted")
        self.listening_identity.setToolTip(
            "Station identity used to accept incoming ARQ connections"
        )
        root.addWidget(controls)
        identity_row = QHBoxLayout()
        identity_row.addWidget(self.listening_identity)
        identity_row.addStretch(1)
        self.peer_presence = QLabel()
        self.peer_presence.setObjectName("Muted")
        self.peer_presence.setVisible(False)
        identity_row.addWidget(self.peer_presence)
        root.addLayout(identity_row)

        cq_row = QHBoxLayout()
        self.call_cq_button = QPushButton("Call CQ")
        self.call_cq_button.setToolTip(
            "Broadcast one CQ invitation on the current radio frequency"
        )
        self.cq_callers = QComboBox()
        self.cq_callers.setPlaceholderText("No CQ callers heard")
        self.answer_cq_button = QPushButton("Answer CQ")
        self.answer_cq_button.setEnabled(False)
        cq_row.addWidget(self.call_cq_button)
        cq_row.addWidget(QLabel("CQ callers"))
        cq_row.addWidget(self.cq_callers, 1)
        cq_row.addWidget(self.answer_cq_button)
        root.addLayout(cq_row)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("ChatSplitter")
        splitter.setHandleWidth(1)
        self.chat_splitter = splitter
        conversation_panel = QWidget()
        conversation_layout = QVBoxLayout(conversation_panel)
        conversation_layout.setContentsMargins(0, 0, 0, 0)
        conversation_title = QLabel("Conversations")
        conversation_title.setObjectName("SectionTitle")
        conversation_layout.addWidget(conversation_title)
        self.conversations = QListWidget()
        self.conversations.setMinimumWidth(180)
        conversation_layout.addWidget(self.conversations, 1)
        self.delete_conversation_button = QPushButton("Delete Conversation")
        self.delete_conversation_button.setEnabled(False)
        conversation_layout.addWidget(self.delete_conversation_button)
        splitter.addWidget(conversation_panel)

        chat = QWidget()
        chat_layout = QVBoxLayout(chat)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        self.heading = QLabel("Connect to a station or select a conversation")
        self.heading.setObjectName("SectionTitle")
        chat_layout.addWidget(self.heading)
        self.messages = QListWidget()
        self.messages.setWordWrap(True)
        self.messages.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        chat_layout.addWidget(self.messages, 1)
        compose_row = QHBoxLayout()
        self.composer = QPlainTextEdit()
        self.composer.setPlaceholderText("Type a text message…")
        self.composer.setMaximumHeight(90)
        self.send_button = QPushButton("Send")
        self.send_button.setObjectName("PrimaryButton")
        self.weather_button = QPushButton("WX")
        self._weather_enabled = False
        self._weather_fetching = False
        self._session_connected = False
        self.weather_button.setEnabled(False)
        self.weather_button.setToolTip(
            "Fetch internet weather and insert it into this message draft"
        )
        compose_row.addWidget(self.composer, 1)
        compose_row.addWidget(self.weather_button)
        compose_row.addWidget(self.send_button)
        chat_layout.addLayout(compose_row)

        voice_row = QHBoxLayout()
        self.voice_record_button = QPushButton("Record Voice")
        self.voice_stop_button = QPushButton("Stop")
        self.voice_send_button = QPushButton("Send Voice")
        self.voice_play_button = QPushButton("Play")
        self.voice_discard_button = QPushButton("Discard")
        self.voice_status = QLabel("Ready to record locally")
        self.voice_stop_button.setEnabled(False)
        self.voice_send_button.setEnabled(False)
        self.voice_play_button.setEnabled(False)
        self.voice_discard_button.setEnabled(False)
        voice_row.addWidget(self.voice_record_button)
        voice_row.addWidget(self.voice_stop_button)
        voice_row.addWidget(self.voice_send_button)
        voice_row.addWidget(self.voice_play_button)
        voice_row.addWidget(self.voice_discard_button)
        voice_row.addWidget(self.voice_status, 1)
        chat_layout.addLayout(voice_row)

        transfer_row = QHBoxLayout()
        self.send_file_button = QPushButton("Send File…")
        self.pause_file_button = QPushButton("Pause")
        self.resume_file_button = QPushButton("Resume")
        self.open_transfer_button = QPushButton("Open Folder")
        self.open_transfer_button.setEnabled(False)
        self.transfer_status = QLabel("No file transfer")
        self.transfer_thumbnail = QLabel()
        self.transfer_thumbnail.setFixedSize(72, 72)
        self.transfer_thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.transfer_thumbnail.setObjectName("Muted")
        self.transfer_progress = QProgressBar()
        self.transfer_progress.setRange(0, 100)
        self.transfer_progress.setValue(0)
        transfer_row.addWidget(self.send_file_button)
        transfer_row.addWidget(self.transfer_thumbnail)
        transfer_row.addWidget(self.pause_file_button)
        transfer_row.addWidget(self.resume_file_button)
        transfer_row.addWidget(self.open_transfer_button)
        transfer_row.addWidget(self.transfer_status, 1)
        transfer_row.addWidget(self.transfer_progress)
        chat_layout.addLayout(transfer_row)
        splitter.addWidget(chat)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, 1)

        self.listen_button.clicked.connect(
            lambda: self.listen_requested.emit(self.local_call.text())
        )
        self.connect_button.clicked.connect(
            lambda: self.connect_requested.emit(
                self.local_call.text(), self.remote_call.text()
            )
        )
        self.disconnect_button.clicked.connect(self.disconnect_requested)
        self.call_cq_button.clicked.connect(self.cq_requested)
        self.answer_cq_button.clicked.connect(self._answer_cq)
        self.cq_callers.currentIndexChanged.connect(
            lambda index: self.answer_cq_button.setEnabled(index >= 0)
        )
        self.send_button.clicked.connect(self._send)
        self.weather_button.clicked.connect(self.weather_requested)
        self.voice_record_button.clicked.connect(self.voice_record_requested)
        self.voice_stop_button.clicked.connect(self.voice_stop_requested)
        self.voice_send_button.clicked.connect(self.voice_send_requested)
        self.voice_play_button.clicked.connect(
            lambda: self.voice_play_requested.emit(self._voice_play_path)
        )
        self.voice_discard_button.clicked.connect(self.voice_discard_requested)
        self.send_file_button.clicked.connect(self._choose_file)
        self.pause_file_button.clicked.connect(self._pause_transfer)
        self.resume_file_button.clicked.connect(self._resume_transfer)
        self.open_transfer_button.clicked.connect(self._open_transfer_folder)
        self.conversations.currentRowChanged.connect(self._select_row)
        self.conversations.currentRowChanged.connect(
            lambda row: self.delete_conversation_button.setEnabled(row >= 0)
        )
        self.delete_conversation_button.clicked.connect(self._delete_conversation)
        self._transfer_id = ""
        self._transfer_path = ""
        self._voice_play_path = ""
        self._voice_available = False
        self._voice_draft_ready = False
        self._voice_send_reason = "Connect to a station before sending voice"
        self._voice_transfer_active = False
        self._cq_expiry_timer = QTimer(self)
        self._cq_expiry_timer.setInterval(30_000)
        self._cq_expiry_timer.timeout.connect(self._expire_cq_calls)
        self._cq_expiry_timer.start()
        self._typing_announced = False
        self._typing_timer = QTimer(self)
        self._typing_timer.setSingleShot(True)
        self._typing_timer.setInterval(10_000)
        self._typing_timer.timeout.connect(self._announce_typing)
        self.composer.textChanged.connect(self._composer_changed)
        self._presence_expiry_timer = QTimer(self)
        self._presence_expiry_timer.setSingleShot(True)
        self._presence_expiry_timer.timeout.connect(self._clear_peer_presence)

    def set_state(self, state: str) -> None:
        self.link_state.setText(f"TNC: {state}")

    def set_listening_identity(self, callsign: str) -> None:
        self.listening_identity.setText(f"Listening as: {callsign}")

    def add_cq_caller(self, cq) -> None:
        received_at = datetime.fromisoformat(cq.timestamp).timestamp()
        existing = next(
            (index for index in range(self.cq_callers.count())
             if self.cq_callers.itemData(index, Qt.ItemDataRole.UserRole) == cq.callsign),
            -1,
        )
        label = f"{cq.callsign} · {cq.grid}"
        if existing >= 0:
            self.cq_callers.setItemText(existing, label)
            self.cq_callers.setItemData(
                existing, received_at, Qt.ItemDataRole.UserRole + 1
            )
            self.cq_callers.setCurrentIndex(existing)
        else:
            self.cq_callers.addItem(label, cq.callsign)
            index = self.cq_callers.count() - 1
            self.cq_callers.setItemData(
                index, received_at, Qt.ItemDataRole.UserRole + 1
            )
            self.cq_callers.setCurrentIndex(index)
        while self.cq_callers.count() > 16:
            self.cq_callers.removeItem(0)
        self.answer_cq_button.setEnabled(self.cq_callers.count() > 0)

    def _answer_cq(self) -> None:
        self._expire_cq_calls()
        callsign = self.cq_callers.currentData(Qt.ItemDataRole.UserRole)
        if callsign:
            self.remote_call.setText(str(callsign))
            self.answer_cq_requested.emit(str(callsign))

    def _expire_cq_calls(self) -> None:
        cutoff = datetime.now(UTC).timestamp() - 300
        for index in range(self.cq_callers.count() - 1, -1, -1):
            timestamp = self.cq_callers.itemData(index, Qt.ItemDataRole.UserRole + 1)
            if timestamp is None or float(timestamp) < cutoff:
                self.cq_callers.removeItem(index)
        self.answer_cq_button.setEnabled(self.cq_callers.count() > 0)

    def set_connected_peer(self, source: str, destination: str, bandwidth: int) -> None:
        local = self.local_call.text().strip().upper()
        peer = destination if source == local else source
        self.remote_call.setText(peer)
        self.link_state.setText(f"Connected: {peer} · {bandwidth} Hz")
        self.link_state.setToolTip(f"ARQ session {source} ↔ {destination}")
        self._session_connected = True
        self._update_weather_button()

    def set_disconnected(self) -> None:
        self.link_state.setText("TNC: ready · no station connected")
        self._session_connected = False
        self._typing_timer.stop()
        self._typing_announced = False
        self._clear_peer_presence()
        self._update_weather_button()

    def set_peer_presence(self, state: str, ttl_seconds: int) -> None:
        peer = self.remote_call.text().strip().upper() or "Remote station"
        descriptions = {
            "typing": f"{peer} is typing…",
            "recording_audio": f"{peer} is recording audio…",
        }
        if state not in descriptions or ttl_seconds <= 0:
            self._clear_peer_presence()
            return
        self.peer_presence.setText(descriptions[state])
        self.peer_presence.setVisible(True)
        self._presence_expiry_timer.start(min(ttl_seconds, 45) * 1000)

    def set_voice_availability(self, available: bool, reason: str) -> None:
        self._voice_available = available
        self._voice_send_reason = reason
        self.voice_send_button.setEnabled(self._voice_draft_ready and available)
        if not self._voice_transfer_active:
            self._show_voice_readiness()

    def set_voice_recording(self, recording: bool, duration_ms: int) -> None:
        self.voice_record_button.setEnabled(not recording)
        self.voice_stop_button.setEnabled(recording)
        self.voice_discard_button.setEnabled(
            not recording and self._voice_draft_ready
        )
        self.voice_status.setText(
            f"Recording… {min(10.0, duration_ms / 1000):.1f} / 10.0 seconds"
            if recording else self.voice_status.text()
        )

    def set_voice_draft(self, ready: bool, path: str = "") -> None:
        self._voice_draft_ready = ready
        self._voice_play_path = path if ready else ""
        self.voice_record_button.setEnabled(True)
        self.voice_send_button.setEnabled(ready and self._voice_available)
        self.voice_play_button.setEnabled(ready and bool(self._voice_play_path))
        self.voice_discard_button.setEnabled(ready)
        if ready:
            self._show_voice_readiness()
        else:
            self._show_voice_readiness()

    def set_voice_messages(self, messages) -> None:
        if not messages:
            self._voice_transfer_active = False
            self._show_voice_readiness()
            return
        message = messages[-1]
        active = message.status in {
            "queued", "offered", "transmitting", "receiving", "verifying",
        }
        self._voice_transfer_active = active
        labels = {
            "queued": "Voice queued locally — waiting for Mercury BUFFER 0",
            "offered": "Voice offer sent — waiting for receiving station",
            "transmitting": f"Voice transmitting — {message.progress}% confirmed by receiver",
            "receiving": f"Incoming voice message — {message.progress}% received",
            "verifying": "Voice sent — waiting for receiver verification",
            "delivered": "Voice delivered — verified by receiving station",
            "received": "Incoming voice message ready to play",
            "failed": "Voice message failed — recording retained for review",
            "busy": "Receiving station was busy — recording retained",
            "link-poor": "Receiving station reports link too weak for voice",
        }
        self.voice_status.setText(
            labels.get(message.status, f"Voice {message.direction} · {message.status}")
        )
        self.voice_record_button.setEnabled(not active)
        self.voice_send_button.setEnabled(
            not active and self._voice_draft_ready and self._voice_available
        )
        self.voice_discard_button.setEnabled(
            not active and self._voice_draft_ready
        )
        if message.status in {"received", "delivered"}:
            self._voice_play_path = message.path
            self.voice_play_button.setEnabled(bool(message.path))
        else:
            self.voice_play_button.setEnabled(
                not active and self._voice_draft_ready and bool(self._voice_play_path)
            )

    def _show_voice_readiness(self) -> None:
        if self._voice_transfer_active:
            return
        if self._voice_available:
            detail = "Peer voice compatible — ready to send"
        else:
            detail = f"Send unavailable: {self._voice_send_reason}"
        prefix = "Voice recording ready" if self._voice_draft_ready else "Ready to record locally"
        self.voice_status.setText(f"{prefix} · {detail}")

    def set_station_callsign_once(self, callsign: str) -> None:
        """Use station identity as the initial chat identity without overriding edits."""
        if not self.local_call.text().strip():
            self.local_call.setText(callsign)

    def show_error(self, message: str) -> None:
        self.link_state.setText(message)
        self.link_state.setToolTip(message)

    def insert_composer_text(self, text: str) -> None:
        """Insert operator-reviewed helper text without transmitting it."""
        clean = text.strip()
        if not clean:
            return
        existing = self.composer.toPlainText().rstrip()
        self.composer.setPlainText(f"{existing}\n{clean}" if existing else clean)
        self.composer.setFocus()

    def set_weather_enabled(self, enabled: bool) -> None:
        self._weather_enabled = bool(enabled)
        self._update_weather_button()

    def set_weather_state(self, state: str) -> None:
        self._weather_fetching = state.startswith("Fetching")
        self.weather_button.setText("WX…" if self._weather_fetching else "WX")
        self._update_weather_button()

    def _update_weather_button(self) -> None:
        self.weather_button.setEnabled(
            self._weather_enabled
            and self._session_connected
            and not self._weather_fetching
        )
        if not self._weather_enabled:
            tooltip = "Enable internet weather access in Setup → Weather"
        elif not self._session_connected:
            tooltip = "Connect to a station before inserting a weather report"
        elif self._weather_fetching:
            tooltip = "Fetching internet weather"
        else:
            tooltip = "Fetch internet weather and insert it into this message draft"
        self.weather_button.setToolTip(tooltip)

    def set_active_conversation(self, conversation: Conversation) -> None:
        self.heading.setText(
            f"{conversation.local_call} ↔ {conversation.remote_call}"
        )
        self.local_call.setText(conversation.local_call)
        self.remote_call.setText(conversation.remote_call)

    def set_conversations(self, conversations: list[Conversation]) -> None:
        selected = self._conversation_ids[self.conversations.currentRow()] if (
            0 <= self.conversations.currentRow() < len(self._conversation_ids)
        ) else None
        self.conversations.blockSignals(True)
        self.conversations.clear()
        self._conversation_ids = [item.id for item in conversations]
        for conversation in conversations:
            updated = format_utc_timestamp(
                conversation.updated_at, "%Y-%m-%d %H:%M UTC"
            )
            item = QListWidgetItem(f"{conversation.remote_call}\n{updated}")
            item.setToolTip(
                f"Conversation from {conversation.local_call} · last contact {updated}"
            )
            self.conversations.addItem(item)
        if selected in self._conversation_ids:
            self.conversations.setCurrentRow(self._conversation_ids.index(selected))
        self.conversations.blockSignals(False)
        self.delete_conversation_button.setEnabled(
            self.conversations.currentRow() >= 0
        )

    def set_messages(self, messages: list[ChatMessage]) -> None:
        self.messages.clear()
        for message in messages:
            direction = (
                "You" if message.direction is MessageDirection.OUTGOING
                else (self.remote_call.text().strip().upper() or "Remote station")
            )
            timestamp = self._display_time(message.sent_at)
            display_status = {
                MessageStatus.QUEUED: "queued locally",
                MessageStatus.SENT: "submitted to Mercury",
                MessageStatus.DELIVERED: "delivered",
                MessageStatus.FAILED: "failed",
            }.get(message.status, message.status.value)
            status = f" · {display_status}" if direction == "You" else ""
            item = QListWidgetItem(
                f"{direction}  {timestamp}{status}\n{message.body}"
            )
            if message.direction is MessageDirection.OUTGOING:
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight)
            self.messages.addItem(item)
        self.messages.scrollToBottom()

    def set_transfers(self, transfers: list[object]) -> None:
        if not transfers:
            return
        transfer = transfers[-1]
        self._transfer_id = transfer.id
        self._transfer_path = transfer.path
        status = {
            "offered": "awaiting acceptance" if transfer.direction == "incoming" else "offer queued",
            "transferring": "receiving" if transfer.direction == "incoming" else "queued to Mercury",
            "verifying": "awaiting peer checksum result",
            "duplicate": "already received and checksum verified",
            "received": "checksum verified",
        }.get(transfer.status, transfer.status)
        self.transfer_status.setText(
            f"{transfer.name} · {transfer.direction} · {status} · "
            f"SHA-256 {transfer.checksum[:12]}…"
        )
        self.transfer_status.setToolTip(
            f"{transfer.path}\nSHA-256: {transfer.checksum}"
        )
        indeterminate = transfer.direction == "outgoing" and transfer.status in {
            "offered", "transferring", "verifying"
        }
        self.transfer_progress.setRange(0, 0 if indeterminate else 100)
        if not indeterminate:
            self.transfer_progress.setValue(transfer.progress)
        if transfer.thumbnail:
            pixmap = QPixmap()
            if pixmap.loadFromData(transfer.thumbnail):
                self.transfer_thumbnail.setPixmap(
                    pixmap.scaled(
                        self.transfer_thumbnail.size(),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
        else:
            self.transfer_thumbnail.clear()
        self.pause_file_button.setEnabled(transfer.status in {"offered", "transferring"})
        self.resume_file_button.setEnabled(transfer.status == "paused")
        self.open_transfer_button.setEnabled(
            bool(transfer.path) and transfer.status in {"received", "duplicate"}
        )

    def _send(self) -> None:
        text = self.composer.toPlainText()
        if text.strip():
            self.send_requested.emit(text)
            self.composer.clear()

    def _composer_changed(self) -> None:
        if not self._session_connected or not self.composer.toPlainText().strip():
            self._typing_timer.stop()
            self._typing_announced = False
            return
        if not self._typing_announced and not self._typing_timer.isActive():
            self._typing_timer.start()

    def _announce_typing(self) -> None:
        if (self._session_connected and self.composer.toPlainText().strip()
                and not self._typing_announced):
            self.presence_requested.emit("typing")
            self._typing_announced = True

    def _clear_peer_presence(self) -> None:
        self._presence_expiry_timer.stop()
        self.peer_presence.clear()
        self.peer_presence.setVisible(False)

    def _choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Send file")
        if path:
            self.file_requested.emit(path)

    def _pause_transfer(self) -> None:
        if self._transfer_id:
            self.transfer_pause_requested.emit(self._transfer_id)

    def _resume_transfer(self) -> None:
        if self._transfer_id:
            self.transfer_resume_requested.emit(self._transfer_id)

    def _open_transfer_folder(self) -> None:
        if self._transfer_path:
            self.transfer_folder_requested.emit(self._transfer_path)

    def _select_row(self, row: int) -> None:
        if 0 <= row < len(self._conversation_ids):
            self.conversation_selected.emit(self._conversation_ids[row])

    def _delete_conversation(self) -> None:
        row = self.conversations.currentRow()
        if not 0 <= row < len(self._conversation_ids):
            return
        station = self.conversations.currentItem().text().splitlines()[0]
        answer = QMessageBox.question(
            self,
            "Delete Conversation",
            f"Delete the conversation and all locally saved messages with {station}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.conversation_delete_requested.emit(self._conversation_ids[row])

    @staticmethod
    def _display_time(value: str) -> str:
        return format_utc_timestamp(value, "%b %d, %H:%M:%S UTC")

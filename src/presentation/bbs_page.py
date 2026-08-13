"""Mailbox, access-control, bulletin board, and file library UI."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .time_format import format_utc_timestamp


class BbsPage(QWidget):
    folder_requested = Signal(str)
    private_requested = Signal(str, str, str, str)
    bulletin_requested = Signal(str, str, str)
    upload_requested = Signal(str, str)
    download_requested = Signal(str)
    authenticate_requested = Signal(str, str)
    enable_protection_requested = Signal(str, str)
    unlock_commander_requested = Signal(str)
    disable_protection_requested = Signal()
    role_requested = Signal(str, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._file_ids: list[str] = []
        root = QVBoxLayout(self)
        title = QLabel("BBS Mailbox")
        title.setObjectName("PageTitle")
        root.addWidget(title)
        self.security_banner = QLabel("Protection status loading…")
        self.security_banner.setObjectName("StatusPill")
        root.addWidget(self.security_banner)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._mailbox_tab(), "Mailbox")
        self.tabs.addTab(self._compose_tab(), "Compose")
        self.tabs.addTab(self._files_tab(), "Files")
        self.tabs.addTab(self._security_tab(), "Access")
        root.addWidget(self.tabs, 1)
        self.status = QLabel("BBS ready")
        self.status.setObjectName("Muted")
        root.addWidget(self.status)

    def _mailbox_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        splitter = QSplitter()
        self.folders = QListWidget()
        self.messages = QListWidget()
        self.message_body = QPlainTextEdit()
        self.message_body.setReadOnly(True)
        splitter.addWidget(self.folders)
        splitter.addWidget(self.messages)
        splitter.addWidget(self.message_body)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 2)
        layout.addWidget(splitter)
        self.folders.currentTextChanged.connect(self.folder_requested)
        self.messages.currentRowChanged.connect(self._show_message)
        self._messages = []
        return widget

    def _security_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(14)

        sign_in = QFrame()
        sign_in.setObjectName("Card")
        self.sign_in_card = sign_in
        sign_form = QFormLayout(sign_in)
        self._configure_access_form(sign_form)
        self.auth_call = QLineEdit()
        self.auth_call.setPlaceholderText("Your callsign")
        self.auth_password = QLineEdit()
        self.auth_password.setEchoMode(QLineEdit.EchoMode.Password)
        authenticate = QPushButton("Authenticate to Connected BBS")
        authenticate.setObjectName("PrimaryButton")
        self.auth_state = QLabel("Not authenticated")
        sign_form.addRow("Callsign", self.auth_call)
        sign_form.addRow("Password", self.auth_password)
        sign_form.addRow(authenticate)
        sign_form.addRow("Session", self.auth_state)
        authenticate.clicked.connect(self._authenticate)
        layout.addWidget(sign_in)

        commander = QFrame()
        commander.setObjectName("Card")
        self.commander_card = commander
        commander_form = QFormLayout(commander)
        self.commander_form = commander_form
        self._configure_access_form(commander_form)
        self.commander_call = QLineEdit()
        self.commander_call.setPlaceholderText("Station commander callsign")
        self.commander_password = QLineEdit()
        self.commander_password.setEchoMode(QLineEdit.EchoMode.Password)
        actions = QHBoxLayout()
        enable = QPushButton("Enable Protection")
        unlock = QPushButton("Unlock Controls")
        disable = QPushButton("Disable Protection")
        actions.addWidget(enable)
        actions.addWidget(unlock)
        actions.addWidget(disable)
        self.commander_state = QLabel("Commander locked")
        self.commander_help = QLabel(
            "The commander is this local BBS administrator. The commander can "
            "unlock local security controls and assign station roles; this is "
            "not the callsign used to sign in to a remote BBS."
        )
        self.commander_help.setWordWrap(True)
        self.commander_help.setObjectName("Muted")
        self.commander_help.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding
        )
        commander_form.addRow("Commander", self.commander_call)
        commander_form.addRow("Password", self.commander_password)
        commander_form.addRow(self.commander_help)
        commander_form.addRow(actions)
        commander_form.addRow("Local controls", self.commander_state)
        enable.clicked.connect(self._enable_protection)
        unlock.clicked.connect(self._unlock_commander)
        disable.clicked.connect(self.disable_protection_requested)
        layout.addWidget(commander)

        roles = QFrame()
        roles.setObjectName("Card")
        self.roles_card = roles
        roles_form = QFormLayout(roles)
        self._configure_access_form(roles_form)
        self.role_call = QLineEdit()
        self.role_call.setPlaceholderText("Callsign")
        self.role = QComboBox()
        self.role.addItems(["user", "operator", "commander"])
        apply_role = QPushButton("Apply Role")
        self.role_list = QListWidget()
        self.role_list.setMinimumHeight(90)
        roles_form.addRow("Callsign", self.role_call)
        roles_form.addRow("Role", self.role)
        roles_form.addRow(apply_role)
        roles_form.addRow("Assignments", self.role_list)
        apply_role.clicked.connect(
            lambda: self.role_requested.emit(self.role_call.text(), self.role.currentText())
        )
        layout.addWidget(roles)
        layout.addStretch()
        scroll.setWidget(widget)
        return scroll

    @staticmethod
    def _configure_access_form(form: QFormLayout) -> None:
        form.setContentsMargins(18, 18, 18, 18)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)

    def set_security(self, enabled: bool, commander_state: str) -> None:
        self.security_banner.setText(
            "Password protection enabled · authentication and roles enforced"
            if enabled else "Password protection disabled · connected stations have open BBS access"
        )
        self.commander_state.setText(commander_state)

    def set_roles(self, roles: list[tuple[str, str]]) -> None:
        self.role_list.clear()
        self.role_list.addItems([f"{callsign} · {role}" for callsign, role in roles])

    def set_auth(self, state: str) -> None:
        self.auth_state.setText(state)

    def set_station_callsign_once(self, callsign: str) -> None:
        """Use station identity as the initial remote-BBS login without overwrites."""
        if not self.auth_call.text().strip():
            self.auth_call.setText(callsign)

    def _authenticate(self) -> None:
        self.authenticate_requested.emit(self.auth_call.text(), self.auth_password.text())
        self.auth_password.clear()

    def _enable_protection(self) -> None:
        self.enable_protection_requested.emit(
            self.commander_call.text(), self.commander_password.text()
        )
        self.commander_password.clear()

    def _unlock_commander(self) -> None:
        self.unlock_commander_requested.emit(self.commander_password.text())
        self.commander_password.clear()

    def _compose_tab(self) -> QWidget:
        card = QFrame()
        card.setObjectName("Card")
        form = QFormLayout(card)
        self.sender = QLineEdit()
        self.sender.setPlaceholderText("N0CALL")
        self.recipient = QLineEdit()
        self.recipient.setPlaceholderText("K1ABC")
        self.message_type = QComboBox()
        self.message_type.addItems(["Private message", "Bulletin"])
        self.subject = QLineEdit()
        self.subject.setMaxLength(120)
        self.body = QPlainTextEdit()
        send = QPushButton("Post to BBS")
        send.setObjectName("PrimaryButton")
        form.addRow("From", self.sender)
        form.addRow("Type", self.message_type)
        form.addRow("To", self.recipient)
        form.addRow("Subject", self.subject)
        form.addRow("Body", self.body)
        form.addRow(send)
        self.message_type.currentIndexChanged.connect(
            lambda index: self.recipient.setEnabled(index == 0)
        )
        send.clicked.connect(self._send_message)
        return card

    def _files_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        owner_row = QHBoxLayout()
        self.file_owner = QLineEdit()
        self.file_owner.setPlaceholderText("Owner callsign")
        upload = QPushButton("Upload…")
        download = QPushButton("Download Selected")
        owner_row.addWidget(self.file_owner)
        owner_row.addWidget(upload)
        owner_row.addWidget(download)
        layout.addLayout(owner_row)
        self.files = QListWidget()
        layout.addWidget(self.files)
        upload.clicked.connect(self._choose_upload)
        download.clicked.connect(self._download)
        return widget

    def set_folders(self, folders: list[tuple[int, str]]) -> None:
        current = self.folders.currentItem().text() if self.folders.currentItem() else "Inbox"
        self.folders.clear()
        self.folders.addItems([name for _, name in folders])
        matches = self.folders.findItems(current, Qt.MatchFlag.MatchExactly)
        self.folders.setCurrentItem(matches[0] if matches else self.folders.item(0))

    def set_messages(self, messages: list[object]) -> None:
        self._messages = messages
        self.messages.clear()
        for message in messages:
            target = f" → {message.recipient}" if message.recipient else ""
            self.messages.addItem(
                f"{message.subject}\n{message.sender}{target} · "
                f"{format_utc_timestamp(message.created_at)}"
            )
        self.message_body.clear()

    def set_files(self, files: list[object]) -> None:
        self.files.clear()
        self._file_ids = [item.id for item in files]
        for item in files:
            self.files.addItem(
                f"{item.name} · {item.size:,} bytes · {item.owner} · "
                f"{item.availability} · SHA-256 {item.checksum[:12]}…"
            )

    def set_status(self, message: str) -> None:
        self.status.setText(message)

    def show_error(self, message: str) -> None:
        self.status.setText(message)
        self.status.setToolTip(message)

    def _show_message(self, row: int) -> None:
        if 0 <= row < len(self._messages):
            message = self._messages[row]
            self.message_body.setPlainText(
                f"Subject: {message.subject}\nFrom: {message.sender}\n"
                f"To: {message.recipient or 'All stations'}\n"
                f"Status: {message.status}\n"
                f"Date: {format_utc_timestamp(message.created_at)}\n\n"
                f"{message.body}"
            )

    def _send_message(self) -> None:
        if self.message_type.currentIndex() == 0:
            self.private_requested.emit(
                self.sender.text(), self.recipient.text(),
                self.subject.text(), self.body.toPlainText(),
            )
        else:
            self.bulletin_requested.emit(
                self.sender.text(), self.subject.text(), self.body.toPlainText()
            )

    def _choose_upload(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Upload file to BBS")
        if path:
            self.upload_requested.emit(self.file_owner.text(), path)

    def _download(self) -> None:
        row = self.files.currentRow()
        if 0 <= row < len(self._file_ids):
            self.download_requested.emit(self._file_ids[row])

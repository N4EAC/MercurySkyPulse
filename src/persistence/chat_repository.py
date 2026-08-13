"""SQLite-backed MercurySkyPulse application data."""

from __future__ import annotations

from pathlib import Path
import sqlite3

from application.messaging import ChatMessage, Conversation, MessageDirection, MessageStatus


class ChatRepository:
    def __init__(self, path: Path | str) -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path)
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._migrate()

    def _migrate(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS stations (
                    id INTEGER PRIMARY KEY,
                    callsign TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    display_name TEXT,
                    grid_square TEXT,
                    notes TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS contacts (
                    id INTEGER PRIMARY KEY,
                    callsign TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    display_name TEXT,
                    grid_square TEXT,
                    notes TEXT,
                    last_contact_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY,
                    local_call TEXT NOT NULL,
                    remote_call TEXT NOT NULL,
                    station_id INTEGER REFERENCES stations(id) ON DELETE SET NULL,
                    contact_id INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(local_call, remote_call)
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    direction TEXT NOT NULL,
                    body TEXT NOT NULL CHECK(length(body) <= 2048),
                    sent_at TEXT NOT NULL,
                    status TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY,
                    occurred_at TEXT NOT NULL,
                    level TEXT NOT NULL,
                    category TEXT NOT NULL,
                    message TEXT NOT NULL,
                    context_json TEXT
                );
                CREATE TABLE IF NOT EXISTS location_history (
                    id INTEGER PRIMARY KEY,
                    latitude REAL NOT NULL CHECK(latitude BETWEEN -90 AND 90),
                    longitude REAL NOT NULL CHECK(longitude BETWEEN -180 AND 180),
                    accuracy_m REAL CHECK(accuracy_m IS NULL OR accuracy_m >= 0),
                    recorded_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS bbs_folders (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    system INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS bbs_messages (
                    id TEXT PRIMARY KEY,
                    folder_id INTEGER NOT NULL REFERENCES bbs_folders(id),
                    kind TEXT NOT NULL CHECK(kind IN ('private', 'bulletin')),
                    sender TEXT NOT NULL,
                    recipient TEXT,
                    subject TEXT NOT NULL CHECK(length(subject) <= 120),
                    body TEXT NOT NULL CHECK(length(body) <= 4096),
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS bbs_files (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    size INTEGER NOT NULL CHECK(size >= 0),
                    checksum TEXT NOT NULL,
                    owner TEXT NOT NULL,
                    local_path TEXT,
                    availability TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS bbs_security (
                    id INTEGER PRIMARY KEY CHECK(id = 1),
                    enabled INTEGER NOT NULL CHECK(enabled IN (0, 1)),
                    salt BLOB,
                    verifier BLOB,
                    commander_call TEXT,
                    updated_at TEXT NOT NULL,
                    CHECK(enabled = 0 OR (salt IS NOT NULL AND verifier IS NOT NULL
                          AND commander_call IS NOT NULL))
                );
                CREATE TABLE IF NOT EXISTS bbs_roles (
                    callsign TEXT PRIMARY KEY COLLATE NOCASE,
                    role TEXT NOT NULL CHECK(role IN ('user', 'operator', 'commander')),
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS messages_conversation_time
                    ON messages(conversation_id, sent_at, id);
                CREATE INDEX IF NOT EXISTS contacts_last_contact
                    ON contacts(last_contact_at DESC);
                CREATE INDEX IF NOT EXISTS logs_time
                    ON logs(occurred_at DESC);
                CREATE INDEX IF NOT EXISTS location_history_time
                    ON location_history(recorded_at, id);
                CREATE INDEX IF NOT EXISTS bbs_messages_folder_time
                    ON bbs_messages(folder_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS bbs_files_time
                    ON bbs_files(created_at DESC);
                """
            )
            self._connection.executemany(
                "INSERT OR IGNORE INTO bbs_folders(name, system) VALUES (?, 1)",
                (("Inbox",), ("Outbox",), ("Bulletins",), ("Files",)),
            )
            self._connection.execute(
                """INSERT OR IGNORE INTO bbs_security(
                       id, enabled, salt, verifier, commander_call, updated_at
                   ) VALUES (1, 0, NULL, NULL, NULL, 'migration')"""
            )
            self._upgrade_legacy_conversations()
            self._connection.execute("PRAGMA user_version = 5")

    def _upgrade_legacy_conversations(self) -> None:
        """Add relational columns to databases created by the chat-only schema."""
        columns = {
            row[1]
            for row in self._connection.execute("PRAGMA table_info(conversations)")
        }
        additions = {
            "station_id": "INTEGER REFERENCES stations(id) ON DELETE SET NULL",
            "contact_id": "INTEGER REFERENCES contacts(id) ON DELETE SET NULL",
            "created_at": "TEXT",
        }
        for name, declaration in additions.items():
            if name not in columns:
                self._connection.execute(
                    f"ALTER TABLE conversations ADD COLUMN {name} {declaration}"
                )
        self._connection.execute(
            "UPDATE conversations SET created_at=updated_at WHERE created_at IS NULL"
        )

    def close(self) -> None:
        self._connection.close()

    def get_or_create_conversation(
        self, local_call: str, remote_call: str, updated_at: str
    ) -> Conversation:
        with self._connection:
            station_id = self._upsert_station(local_call, updated_at)
            contact_id = self._upsert_contact(remote_call, updated_at)
            self._connection.execute(
                """INSERT INTO conversations(
                       local_call, remote_call, station_id, contact_id,
                       created_at, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(local_call, remote_call)
                   DO UPDATE SET
                       station_id=excluded.station_id,
                       contact_id=excluded.contact_id,
                       updated_at=excluded.updated_at""",
                (
                    local_call,
                    remote_call,
                    station_id,
                    contact_id,
                    updated_at,
                    updated_at,
                ),
            )
        row = self._connection.execute(
            "SELECT id, local_call, remote_call, updated_at FROM conversations WHERE local_call=? AND remote_call=?",
            (local_call, remote_call),
        ).fetchone()
        return Conversation(*row)

    def _upsert_station(self, callsign: str, timestamp: str) -> int:
        self._connection.execute(
            """INSERT INTO stations(callsign, created_at, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(callsign) DO UPDATE SET updated_at=excluded.updated_at""",
            (callsign, timestamp, timestamp),
        )
        row = self._connection.execute(
            "SELECT id FROM stations WHERE callsign=? COLLATE NOCASE", (callsign,)
        ).fetchone()
        return int(row[0])

    def _upsert_contact(self, callsign: str, timestamp: str) -> int:
        self._connection.execute(
            """INSERT INTO contacts(
                   callsign, last_contact_at, created_at, updated_at
               ) VALUES (?, ?, ?, ?)
               ON CONFLICT(callsign) DO UPDATE SET
                   last_contact_at=excluded.last_contact_at,
                   updated_at=excluded.updated_at""",
            (callsign, timestamp, timestamp, timestamp),
        )
        row = self._connection.execute(
            "SELECT id FROM contacts WHERE callsign=? COLLATE NOCASE", (callsign,)
        ).fetchone()
        return int(row[0])

    def set_setting(self, key: str, value: str, updated_at: str) -> None:
        with self._connection:
            self._connection.execute(
                """INSERT INTO settings(key, value, updated_at) VALUES (?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET
                       value=excluded.value,
                       updated_at=excluded.updated_at""",
                (key, value, updated_at),
            )

    def get_setting(self, key: str) -> str | None:
        row = self._connection.execute(
            "SELECT value FROM settings WHERE key=?", (key,)
        ).fetchone()
        return None if row is None else str(row[0])

    def add_log(
        self,
        occurred_at: str,
        level: str,
        category: str,
        message: str,
        context_json: str | None = None,
    ) -> int:
        with self._connection:
            cursor = self._connection.execute(
                """INSERT INTO logs(
                       occurred_at, level, category, message, context_json
                   ) VALUES (?, ?, ?, ?, ?)""",
                (occurred_at, level, category, message, context_json),
            )
        return int(cursor.lastrowid)

    def save_gps_location(
        self,
        latitude: float,
        longitude: float,
        accuracy_m: float | None,
        recorded_at: str,
    ) -> int:
        with self._connection:
            cursor = self._connection.execute(
                """INSERT INTO location_history(
                       latitude, longitude, accuracy_m, recorded_at
                   ) VALUES (?, ?, ?, ?)""",
                (latitude, longitude, accuracy_m, recorded_at),
            )
        return int(cursor.lastrowid)

    def list_gps_locations(self) -> list[tuple[float, float, float | None, str]]:
        rows = self._connection.execute(
            """SELECT latitude, longitude, accuracy_m, recorded_at
               FROM location_history ORDER BY recorded_at, id"""
        ).fetchall()
        return [
            (float(row[0]), float(row[1]), None if row[2] is None else float(row[2]), str(row[3]))
            for row in rows
        ]

    def gps_location_count(self) -> int:
        return int(
            self._connection.execute(
                "SELECT COUNT(*) FROM location_history"
            ).fetchone()[0]
        )

    def list_bbs_folders(self) -> list[tuple[int, str]]:
        return [
            (int(row[0]), str(row[1]))
            for row in self._connection.execute(
                "SELECT id, name FROM bbs_folders ORDER BY id"
            )
        ]

    def save_bbs_message(
        self, message_id: str, folder: str, kind: str, sender: str,
        recipient: str | None, subject: str, body: str, created_at: str,
        status: str,
    ) -> None:
        folder_row = self._connection.execute(
            "SELECT id FROM bbs_folders WHERE name=?", (folder,)
        ).fetchone()
        if folder_row is None:
            raise ValueError("Unknown BBS folder")
        with self._connection:
            self._connection.execute(
                """INSERT OR IGNORE INTO bbs_messages(
                       id, folder_id, kind, sender, recipient, subject, body,
                       created_at, status
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (message_id, folder_row[0], kind, sender, recipient, subject,
                 body, created_at, status),
            )

    def list_bbs_messages(self, folder: str) -> list[tuple]:
        return self._connection.execute(
            """SELECT m.id, m.kind, m.sender, m.recipient, m.subject, m.body,
                      m.created_at, m.status
               FROM bbs_messages m JOIN bbs_folders f ON f.id=m.folder_id
               WHERE f.name=? ORDER BY m.created_at DESC, m.id""",
            (folder,),
        ).fetchall()

    def save_bbs_file(
        self, file_id: str, name: str, size: int, checksum: str, owner: str,
        local_path: str | None, availability: str, created_at: str,
    ) -> None:
        with self._connection:
            self._connection.execute(
                """INSERT OR REPLACE INTO bbs_files(
                       id, name, size, checksum, owner, local_path,
                       availability, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (file_id, name, size, checksum, owner, local_path,
                 availability, created_at),
            )

    def list_bbs_files(self) -> list[tuple]:
        return self._connection.execute(
            """SELECT id, name, size, checksum, owner, local_path,
                      availability, created_at
               FROM bbs_files ORDER BY created_at DESC, id"""
        ).fetchall()

    def get_bbs_file(self, file_id: str) -> tuple | None:
        return self._connection.execute(
            """SELECT id, name, size, checksum, owner, local_path,
                      availability, created_at FROM bbs_files WHERE id=?""",
            (file_id,),
        ).fetchone()

    def get_bbs_security(self) -> tuple[bool, bytes | None, bytes | None, str | None]:
        row = self._connection.execute(
            "SELECT enabled, salt, verifier, commander_call FROM bbs_security WHERE id=1"
        ).fetchone()
        return bool(row[0]), row[1], row[2], row[3]

    def set_bbs_security(
        self, enabled: bool, salt: bytes | None, verifier: bytes | None,
        commander_call: str | None, updated_at: str,
    ) -> None:
        with self._connection:
            self._connection.execute(
                """UPDATE bbs_security SET enabled=?, salt=?, verifier=?,
                       commander_call=?, updated_at=? WHERE id=1""",
                (int(enabled), salt, verifier, commander_call, updated_at),
            )

    def get_bbs_role(self, callsign: str) -> str:
        row = self._connection.execute(
            "SELECT role FROM bbs_roles WHERE callsign=? COLLATE NOCASE", (callsign,)
        ).fetchone()
        return "user" if row is None else str(row[0])

    def set_bbs_role(self, callsign: str, role: str, updated_at: str) -> None:
        if role not in {"user", "operator", "commander"}:
            raise ValueError("Invalid BBS role")
        with self._connection:
            self._connection.execute(
                """INSERT INTO bbs_roles(callsign, role, updated_at) VALUES (?, ?, ?)
                   ON CONFLICT(callsign) DO UPDATE SET role=excluded.role,
                       updated_at=excluded.updated_at""",
                (callsign, role, updated_at),
            )

    def list_bbs_roles(self) -> list[tuple[str, str]]:
        return [
            (str(row[0]), str(row[1]))
            for row in self._connection.execute(
                "SELECT callsign, role FROM bbs_roles ORDER BY callsign COLLATE NOCASE"
            )
        ]

    def list_conversations(self) -> list[Conversation]:
        rows = self._connection.execute(
            "SELECT id, local_call, remote_call, updated_at FROM conversations ORDER BY updated_at DESC"
        ).fetchall()
        return [Conversation(*row) for row in rows]

    def delete_conversation(self, conversation_id: int) -> bool:
        with self._connection:
            cursor = self._connection.execute(
                "DELETE FROM conversations WHERE id=?", (int(conversation_id),)
            )
        return cursor.rowcount > 0

    def delete_empty_conversations_before(self, cutoff: str) -> int:
        """Remove stale connection attempts while preserving every message history."""
        with self._connection:
            cursor = self._connection.execute(
                """DELETE FROM conversations
                   WHERE updated_at < ?
                     AND NOT EXISTS (
                         SELECT 1 FROM messages
                         WHERE messages.conversation_id=conversations.id
                     )""",
                (cutoff,),
            )
        return max(0, cursor.rowcount)

    def save_message(self, message: ChatMessage) -> None:
        with self._connection:
            self._connection.execute(
                """INSERT OR REPLACE INTO messages
                   (id, conversation_id, direction, body, sent_at, status)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    message.id,
                    message.conversation_id,
                    message.direction.value,
                    message.body,
                    message.sent_at,
                    message.status.value,
                ),
            )
            self._connection.execute(
                "UPDATE conversations SET updated_at=? WHERE id=?",
                (message.sent_at, message.conversation_id),
            )

    def update_status(self, message_id: str, status: MessageStatus) -> None:
        with self._connection:
            self._connection.execute(
                "UPDATE messages SET status=? WHERE id=?",
                (status.value, message_id),
            )

    def fail_unsettled(self, conversation_id: int) -> None:
        with self._connection:
            self._connection.execute(
                """UPDATE messages SET status=?
                   WHERE conversation_id=? AND status IN (?, ?)""",
                (
                    MessageStatus.FAILED.value,
                    conversation_id,
                    MessageStatus.QUEUED.value,
                    MessageStatus.SENT.value,
                ),
            )

    def list_messages(self, conversation_id: int) -> list[ChatMessage]:
        rows = self._connection.execute(
            """SELECT id, conversation_id, direction, body, sent_at, status
               FROM messages WHERE conversation_id=? ORDER BY sent_at, id""",
            (conversation_id,),
        ).fetchall()
        return [
            ChatMessage(
                id=row[0],
                conversation_id=row[1],
                direction=MessageDirection(row[2]),
                body=row[3],
                sent_at=row[4],
                status=MessageStatus(row[5]),
            )
            for row in rows
        ]

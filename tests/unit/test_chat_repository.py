from pathlib import Path
from datetime import UTC, datetime, timedelta
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from application.messaging import ChatMessage, MessageDirection, MessageStatus
from persistence.chat_repository import ChatRepository


class ChatRepositoryTests(unittest.TestCase):
    def test_creates_complete_application_schema(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "application.sqlite3"
            repository = ChatRepository(path)
            repository.close()
            connection = sqlite3.connect(path)
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            self.assertTrue(
                {
                    "stations", "contacts", "conversations", "messages",
                    "settings", "logs", "location_history", "bbs_folders",
                    "bbs_messages", "bbs_files",
                    "bbs_security", "bbs_roles",
                }
                <= tables
            )
            self.assertEqual(
                connection.execute("PRAGMA user_version").fetchone()[0], 5
            )
            connection.close()

    def test_conversation_populates_station_and_contact(self) -> None:
        repository = ChatRepository(":memory:")
        repository.get_or_create_conversation("N0CALL", "K1ABC", "now")
        station = repository._connection.execute(
            "SELECT callsign FROM stations"
        ).fetchone()
        contact = repository._connection.execute(
            "SELECT callsign FROM contacts"
        ).fetchone()
        self.assertEqual(station[0], "N0CALL")
        self.assertEqual(contact[0], "K1ABC")
        repository.close()

    def test_settings_and_logs_are_writable(self) -> None:
        repository = ChatRepository(":memory:")
        repository.set_setting("appearance.theme", "dark", "now")
        log_id = repository.add_log("now", "info", "test", "ready")
        self.assertEqual(repository.get_setting("appearance.theme"), "dark")
        self.assertGreater(log_id, 0)
        repository.close()

    def test_gps_history_is_ordered_and_counted(self) -> None:
        repository = ChatRepository(":memory:")
        repository.save_gps_location(40.1, -73.9, 4.0, "later")
        repository.save_gps_location(40.0, -74.0, None, "earlier")
        self.assertEqual(repository.gps_location_count(), 2)
        history = repository.list_gps_locations()
        self.assertEqual(history[0], (40.0, -74.0, None, "earlier"))
        repository.close()

    def test_bbs_schema_has_default_folders(self) -> None:
        repository = ChatRepository(":memory:")
        self.assertEqual(
            [name for _, name in repository.list_bbs_folders()],
            ["Inbox", "Outbox", "Bulletins", "Files"],
        )
        repository.close()

    def test_bbs_security_defaults_open_and_persists_roles(self) -> None:
        repository = ChatRepository(":memory:")
        self.assertEqual(repository.get_bbs_security(), (False, None, None, None))
        repository.set_bbs_role("N0CALL", "commander", "now")
        self.assertEqual(repository.get_bbs_role("n0call"), "commander")
        self.assertEqual(repository.list_bbs_roles(), [("N0CALL", "commander")])
        repository.close()

    def test_upgrades_legacy_chat_schema_without_data_loss(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.sqlite3"
            connection = sqlite3.connect(path)
            connection.executescript(
                """
                CREATE TABLE conversations (
                    id INTEGER PRIMARY KEY,
                    local_call TEXT NOT NULL,
                    remote_call TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(local_call, remote_call)
                );
                CREATE TABLE messages (
                    id TEXT PRIMARY KEY,
                    conversation_id INTEGER NOT NULL REFERENCES conversations(id),
                    direction TEXT NOT NULL,
                    body TEXT NOT NULL,
                    sent_at TEXT NOT NULL,
                    status TEXT NOT NULL
                );
                INSERT INTO conversations(local_call, remote_call, updated_at)
                VALUES ('N0CALL', 'K1ABC', 'before');
                INSERT INTO messages VALUES
                ('old', 1, 'incoming', 'preserved', 'before', 'received');
                """
            )
            connection.close()
            repository = ChatRepository(path)
            self.assertEqual(repository.list_messages(1)[0].body, "preserved")
            created_at = repository._connection.execute(
                "SELECT created_at FROM conversations WHERE id=1"
            ).fetchone()[0]
            self.assertEqual(created_at, "before")
            repository.close()

    def test_history_survives_repository_reopen(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "history.sqlite3"
            repository = ChatRepository(path)
            conversation = repository.get_or_create_conversation(
                "N0CALL", "K1ABC", "2026-01-01T00:00:00+00:00"
            )
            repository.save_message(
                ChatMessage(
                    "id-1", conversation.id, MessageDirection.OUTGOING, "Hello",
                    "2026-01-01T00:00:01+00:00", MessageStatus.SENT,
                )
            )
            repository.close()
            reopened = ChatRepository(path)
            messages = reopened.list_messages(conversation.id)
            self.assertEqual(messages[0].body, "Hello")
            self.assertEqual(messages[0].status, MessageStatus.SENT)
            reopened.close()

    def test_unsettled_messages_fail_on_disconnect(self) -> None:
        repository = ChatRepository(":memory:")
        conversation = repository.get_or_create_conversation("N0CALL", "K1ABC", "now")
        repository.save_message(
            ChatMessage(
                "id-1", conversation.id, MessageDirection.OUTGOING, "Hello",
                "later", MessageStatus.SENT,
            )
        )
        repository.fail_unsettled(conversation.id)
        self.assertEqual(
            repository.list_messages(conversation.id)[0].status,
            MessageStatus.FAILED,
        )
        repository.close()

    def test_delete_conversation_cascades_messages(self) -> None:
        repository = ChatRepository(":memory:")
        conversation = repository.get_or_create_conversation(
            "N0CALL", "K1ABC", "2026-01-01T00:00:00+00:00"
        )
        repository.save_message(ChatMessage(
            "id-1", conversation.id, MessageDirection.INCOMING, "Hello",
            "2026-01-01T00:01:00+00:00", MessageStatus.RECEIVED,
        ))
        self.assertTrue(repository.delete_conversation(conversation.id))
        self.assertEqual(repository.list_conversations(), [])
        self.assertEqual(repository.list_messages(conversation.id), [])
        repository.close()

    def test_cleanup_removes_only_old_empty_connection_attempts(self) -> None:
        repository = ChatRepository(":memory:")
        old = (datetime.now(UTC) - timedelta(days=31)).isoformat()
        recent = datetime.now(UTC).isoformat()
        empty = repository.get_or_create_conversation("N0CALL", "K1OLD", old)
        kept = repository.get_or_create_conversation("N0CALL", "K1KEPT", old)
        repository.save_message(ChatMessage(
            "kept", kept.id, MessageDirection.INCOMING, "History", old,
            MessageStatus.RECEIVED,
        ))
        repository.get_or_create_conversation("N0CALL", "K1NEW", recent)
        removed = repository.delete_empty_conversations_before(
            (datetime.now(UTC) - timedelta(days=30)).isoformat()
        )
        self.assertEqual(removed, 1)
        calls = [item.remote_call for item in repository.list_conversations()]
        self.assertNotIn(empty.remote_call, calls)
        self.assertEqual(set(calls), {"K1KEPT", "K1NEW"})
        repository.close()


if __name__ == "__main__":
    unittest.main()

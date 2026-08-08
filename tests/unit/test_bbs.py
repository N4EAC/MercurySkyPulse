from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PySide6.QtCore import QObject, Signal

from application.bbs import BbsService
from persistence.chat_repository import ChatRepository
from application_protocol.messaging import ChatEnvelope


class FakeBbsClient(QObject):
    bbs_event_received = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.sent = []

    @staticmethod
    def normalize_callsign(value):
        value = value.strip().upper()
        if not value or len(value) > 15:
            raise ValueError("invalid callsign")
        return value

    def send_file_event(self, kind, event_id, timestamp, **values):
        self.sent.append((kind, event_id, timestamp, values))


class FakeFileTransfer:
    def __init__(self) -> None:
        self.paths = []

    def send_raw_file(self, path):
        self.paths.append(path)


class BbsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.repository = ChatRepository(":memory:")
        self.client = FakeBbsClient()
        self.transfers = FakeFileTransfer()
        self.service = BbsService(
            self.client,
            self.repository,
            self.transfers,
            Path(self.temporary.name) / "bbs",
        )

    def tearDown(self) -> None:
        self.repository.close()
        self.temporary.cleanup()

    def test_system_folders_exist(self) -> None:
        names = [name for _, name in self.repository.list_bbs_folders()]
        self.assertEqual(names, ["Inbox", "Outbox", "Bulletins", "Files"])

    def test_private_message_is_sent_and_saved_to_outbox(self) -> None:
        self.service.send_private("n0call", "k1abc", "Hello", "Private body")
        self.assertEqual(self.client.sent[0][0], "bbs_private")
        message = self.repository.list_bbs_messages("Outbox")[0]
        self.assertEqual(message[2], "N0CALL")
        self.assertEqual(message[3], "K1ABC")
        self.assertEqual(message[5], "Private body")

    def test_received_private_message_and_bulletin_use_separate_folders(self) -> None:
        self.client.bbs_event_received.emit(
            ChatEnvelope(
                "bbs_private", "private", "now",
                values={"sender": "K1ABC", "recipient": "N0CALL", "subject": "P", "body": "private"},
            )
        )
        self.client.bbs_event_received.emit(
            ChatEnvelope(
                "bbs_bulletin", "bulletin", "now",
                values={"sender": "K1ABC", "subject": "B", "body": "public"},
            )
        )
        self.assertEqual(len(self.repository.list_bbs_messages("Inbox")), 1)
        self.assertEqual(len(self.repository.list_bbs_messages("Bulletins")), 1)

    def test_upload_advertise_request_and_raw_download(self) -> None:
        source = Path(self.temporary.name) / "manual.pdf"
        source.write_bytes(b"BBS file")
        self.service.upload("N0CALL", str(source))
        event = self.client.sent[0]
        self.assertEqual(event[0], "bbs_file_announce")
        file_id = event[1]
        stored = self.repository.get_bbs_file(file_id)
        self.assertTrue(Path(stored[5]).is_file())
        self.client.bbs_event_received.emit(
            ChatEnvelope("bbs_file_request", file_id, "now")
        )
        self.assertEqual(self.transfers.paths, [stored[5]])

    def test_remote_file_can_be_requested_for_download(self) -> None:
        self.client.bbs_event_received.emit(
            ChatEnvelope(
                "bbs_file_announce", "remote-file", "now",
                values={
                    "name": "map.dat", "size": 12, "sha256": "a" * 64,
                    "owner": "K1ABC",
                },
            )
        )
        self.service.download("remote-file")
        self.assertEqual(self.client.sent[-1][0], "bbs_file_request")

    def test_commander_can_enable_unlock_assign_roles_and_disable(self) -> None:
        self.service.enable_protection("N0CALL", "correct horse battery")
        enabled, salt, verifier, commander = self.repository.get_bbs_security()
        self.assertTrue(enabled)
        self.assertEqual(commander, "N0CALL")
        self.assertNotEqual(verifier, b"correct horse battery")
        self.assertEqual(len(salt), 16)
        self.service.set_role("K1ABC", "operator")
        self.assertEqual(self.repository.get_bbs_role("K1ABC"), "operator")
        self.service.disable_protection()
        self.assertFalse(self.repository.get_bbs_security()[0])

    def test_protected_bbs_rejects_unauthenticated_content(self) -> None:
        self.service.enable_protection("N0CALL", "correct horse battery")
        self.client.sent.clear()
        self.client.bbs_event_received.emit(
            ChatEnvelope("bbs_private", "private", "now", values={
                "sender": "K1ABC", "recipient": "N0CALL",
                "subject": "P", "body": "private",
            })
        )
        self.assertEqual(self.repository.list_bbs_messages("Inbox"), [])
        self.assertEqual(self.client.sent[-1][0], "bbs_access_denied")

    def test_wrong_commander_password_does_not_unlock_controls(self) -> None:
        self.service.enable_protection("N0CALL", "correct horse battery")
        self.service._commander_unlocked = False
        self.service.unlock_commander("incorrect password")
        self.service.set_role("K1ABC", "operator")
        self.assertEqual(self.repository.get_bbs_role("K1ABC"), "user")

    def test_locked_station_cannot_replace_existing_password(self) -> None:
        self.service.enable_protection("N0CALL", "correct horse battery")
        original = self.repository.get_bbs_security()[2]
        self.service._commander_unlocked = False
        self.service.enable_protection("K1ABC", "replacement password")
        self.assertEqual(self.repository.get_bbs_security()[2], original)

    def test_challenge_response_authenticates_assigned_role(self) -> None:
        remote_repository = ChatRepository(":memory:")
        remote_client = FakeBbsClient()
        remote_service = BbsService(
            remote_client, remote_repository, FakeFileTransfer(),
            Path(self.temporary.name) / "remote",
        )
        self.service.enable_protection("N0CALL", "correct horse battery")
        self.service.set_role("K1ABC", "operator")

        remote_service.authenticate("K1ABC", "correct horse battery")
        kind, event_id, timestamp, values = remote_client.sent.pop()
        self.service._on_event(ChatEnvelope(kind, event_id, timestamp, values=values))
        kind, event_id, timestamp, values = self.client.sent.pop()
        remote_service._on_event(ChatEnvelope(kind, event_id, timestamp, values=values))
        kind, event_id, timestamp, values = remote_client.sent.pop()
        self.service._on_event(ChatEnvelope(kind, event_id, timestamp, values=values))

        self.assertEqual(self.service._remote_call, "K1ABC")
        self.assertEqual(self.service._remote_role, "operator")
        self.assertEqual(self.client.sent[-1][0], "bbs_auth_result")
        remote_repository.close()


if __name__ == "__main__":
    unittest.main()

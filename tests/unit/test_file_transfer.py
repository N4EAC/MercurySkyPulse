from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PySide6.QtCore import QObject, Signal

from application.file_transfer import FileTransferService, PreparedFile
from persistence.chat_repository import ChatRepository
from application_protocol.messaging import ChatEnvelope


class FakeClient(QObject):
    file_event_received = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.peer = None
        self.write_ready = True

    def send_file_event(self, kind, transfer_id, timestamp, **values) -> None:
        self.peer.file_event_received.emit(
            ChatEnvelope(kind, transfer_id, timestamp, values=values)
        )

    def file_write_ready(self) -> bool:
        return self.write_ready


class FileTransferTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        root = Path(self.temporary.name)
        self.source_directory = root / "source"
        self.receive_directory = root / "received"
        self.source_directory.mkdir()
        sender_client = FakeClient()
        receiver_client = FakeClient()
        sender_client.peer = receiver_client
        receiver_client.peer = sender_client
        self.sender = FileTransferService(
            sender_client, ChatRepository(":memory:"), root / "sender-received",
            auto_pump=False,
        )
        self.receiver = FileTransferService(
            receiver_client, ChatRepository(":memory:"), self.receive_directory,
            auto_pump=False,
        )
        self.sender_client = sender_client
        self.receiver_client = receiver_client

    def tearDown(self) -> None:
        self.sender.repository.close()
        self.receiver.repository.close()
        self.temporary.cleanup()

    def _finish(self) -> None:
        for _ in range(100):
            transfer = next(iter(self.sender._transfers.values()))
            if transfer.status in {"received", "duplicate", "failed"}:
                return
            self.sender._pump()
        self.fail("transfer did not finish")

    def test_send_receive_progress_and_checksum(self) -> None:
        source = self.source_directory / "report.bin"
        source.write_bytes(b"MercurySkyPulse" * 1000)
        self.sender.send_file(str(source))
        transfer_id = next(iter(self.sender._transfers))
        self.assertEqual(self.sender._transfers[transfer_id].status, "transferring")
        self.sender.pause(transfer_id)
        self.assertEqual(self.sender._transfers[transfer_id].status, "paused")
        self.assertEqual(self.receiver._transfers[transfer_id].status, "paused")
        self.sender.resume(transfer_id)
        self.sender._pump()
        self.assertGreater(self.sender._transfers[transfer_id].progress, 0)
        self.assertLess(self.sender._transfers[transfer_id].progress, 100)
        self._finish()
        received = self.receive_directory / "report.bin"
        self.assertEqual(received.read_bytes(), source.read_bytes())
        self.assertEqual(self.sender._transfers[transfer_id].status, "received")
        self.assertEqual(self.sender._transfers[transfer_id].progress, 100)

    def test_duplicate_checksum_is_not_written_twice(self) -> None:
        source = self.source_directory / "same.bin"
        source.write_bytes(b"same content")
        self.sender.send_file(str(source))
        self._finish()
        first_id = next(iter(self.sender._transfers))
        self.sender.send_file(str(source))
        second_id = next(reversed(self.sender._transfers))
        self.assertNotEqual(first_id, second_id)
        self.assertEqual(self.sender._transfers[second_id].status, "duplicate")
        self.assertEqual(len(list(self.receive_directory.glob("same*"))), 1)

    def test_received_name_cannot_escape_download_directory(self) -> None:
        self.receiver._receive_offer(
            "unsafe",
            {"name": "../../escape.txt", "size": 1, "sha256": "0" * 64},
        )
        transfer = self.receiver._transfers["unsafe"]
        self.assertEqual(transfer.name, "escape.txt")
        self.assertEqual(Path(transfer.path).parent, self.receive_directory)

    def test_checksum_mismatch_does_not_publish_file(self) -> None:
        self.receiver._receive_offer(
            "corrupt",
            {"name": "bad.bin", "size": 3, "sha256": "0" * 64},
        )
        self.receiver._receive_chunk(
            "corrupt", {"offset": 0, "data": "YWJj"}
        )
        self.receiver._receive_complete("corrupt", {})
        self.assertEqual(
            self.receiver._transfers["corrupt"].status, "checksum-failed"
        )
        self.assertFalse((self.receive_directory / "bad.bin").exists())

    def test_image_thumbnail_metadata_reaches_receiver(self) -> None:
        source = self.source_directory / "photo.jpg"
        source.write_bytes(b"prepared image")

        class Processor:
            def prepare(self, path):
                return PreparedFile(path, path.name, b"thumbnail", True)

            def close(self):
                pass

        self.sender.image_processor = Processor()
        self.sender.send_file(str(source))
        transfer_id = next(iter(self.sender._transfers))
        incoming = self.receiver._transfers[transfer_id]
        self.assertEqual(incoming.thumbnail, b"thumbnail")
        self.assertTrue(incoming.optimized)

    def test_backpressure_does_not_advance_or_read_a_chunk(self) -> None:
        source = self.source_directory / "blocked.bin"
        source.write_bytes(b"x" * 9000)
        self.sender.send_file(str(source))
        transfer_id = next(iter(self.sender._transfers))
        self.sender_client.write_ready = False
        self.sender._pump()
        self.assertEqual(self.sender._transfers[transfer_id].transferred, 0)
        self.sender_client.write_ready = True
        self.sender._pump()
        self.assertEqual(self.sender._transfers[transfer_id].transferred, 4096)

    def test_out_of_order_chunk_is_rejected_without_writing(self) -> None:
        errors = []
        self.receiver.error_received.connect(errors.append)
        self.receiver_client.file_event_received.emit(ChatEnvelope(
            "file_offer", "ordered", "now",
            values={"name": "ordered.bin", "size": 3, "sha256": "a" * 64},
        ))
        partial = Path(self.receiver._transfers["ordered"].path)
        self.receiver_client.file_event_received.emit(ChatEnvelope(
            "file_chunk", "ordered", "now", values={"offset": 2, "data": "YQ=="},
        ))
        self.assertEqual(partial.read_bytes(), b"")
        self.assertTrue(any("offset" in error for error in errors))

    def test_empty_file_completes_with_verified_checksum(self) -> None:
        source = self.source_directory / "empty.bin"
        source.write_bytes(b"")
        self.sender.send_file(str(source))
        self._finish()
        transfer = next(iter(self.sender._transfers.values()))
        self.assertEqual(transfer.status, "received")
        self.assertEqual(transfer.progress, 100)
        self.assertEqual((self.receive_directory / "empty.bin").read_bytes(), b"")


if __name__ == "__main__":
    unittest.main()

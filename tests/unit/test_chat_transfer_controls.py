import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from application.messaging import ChatMessage, MessageDirection, MessageStatus
from presentation.chat_page import ChatPage


class ChatTransferControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.page = ChatPage()

    def tearDown(self):
        self.page.deleteLater()

    def test_interrupted_file_clears_controls_and_allows_next_send(self):
        transfer = SimpleNamespace(
            id="file", direction="outgoing", status="interrupted", progress=0,
            path="/tmp/report.txt", name="report.txt", checksum="a" * 64,
            thumbnail=b"",
        )
        self.page.set_transfers([transfer])
        self.assertEqual(self.page.transfer_status.text(), "No file transfer")
        self.assertFalse(self.page.cancel_file_button.isEnabled())
        self.assertIn("interrupted", self.page.messages.item(0).text())

    def test_completed_outgoing_file_clears_controls_but_remains_in_chat(self):
        transfer = SimpleNamespace(
            id="file", direction="outgoing", status="received", progress=100,
            path="/tmp/report.txt", name="report.txt", checksum="a" * 64,
            thumbnail=b"",
        )
        self.page.set_transfers([transfer])
        self.assertEqual(self.page.transfer_status.text(), "No file transfer")
        self.assertEqual(self.page.transfer_progress.value(), 0)
        self.assertIn("File report.txt: delivered", self.page.messages.item(0).text())

    def test_text_status_distinguishes_local_queue_from_mercury_submission(self):
        base = dict(
            id="message", conversation_id=1,
            direction=MessageDirection.OUTGOING, body="hello",
            sent_at="2026-08-14T12:00:00+00:00",
        )
        self.page.set_messages([ChatMessage(status=MessageStatus.QUEUED, **base)])
        self.assertIn("queued locally", self.page.messages.item(0).text())
        self.page.set_messages([ChatMessage(status=MessageStatus.SENT, **base)])
        self.assertIn("submitted to Mercury", self.page.messages.item(0).text())


if __name__ == "__main__":
    unittest.main()

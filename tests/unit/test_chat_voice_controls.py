import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from presentation.chat_page import ChatPage
from application.messaging import ChatMessage, MessageDirection, MessageStatus


class ChatVoiceControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.page = ChatPage()

    def tearDown(self):
        self.page.deleteLater()

    def test_recording_and_local_review_do_not_require_connection(self):
        self.page.set_voice_availability(
            False, "Connect to a station before sending voice"
        )
        self.assertTrue(self.page.voice_record_button.isEnabled())

        self.page.set_voice_draft(True, "/tmp/local-voice.m4a")

        self.assertTrue(self.page.voice_record_button.isEnabled())
        self.assertTrue(self.page.voice_play_button.isEnabled())
        self.assertTrue(self.page.voice_discard_button.isEnabled())
        self.assertFalse(self.page.voice_send_button.isEnabled())

    def test_new_draft_path_is_used_for_playback(self):
        paths = []
        self.page.voice_play_requested.connect(paths.append)
        self.page.set_voice_draft(True, "/tmp/recorded-voice.m4a")

        self.page.voice_play_button.click()

        self.assertEqual(paths, ["/tmp/recorded-voice.m4a"])

    def test_discard_clears_local_review(self):
        self.page.set_voice_draft(True, "/tmp/recorded-voice.m4a")
        self.page.set_voice_draft(False)

        self.assertTrue(self.page.voice_record_button.isEnabled())
        self.assertFalse(self.page.voice_play_button.isEnabled())
        self.assertFalse(self.page.voice_discard_button.isEnabled())

    def test_incoming_transfer_shows_local_progress_snapshot(self):
        message = SimpleNamespace(
            id="voice", direction="incoming", status="receiving",
            progress=42, path="", size=1000,
        )
        self.page.set_voice_messages([message])
        self.assertIn("Incoming voice message", self.page.voice_status.text())
        self.assertIn("42%", self.page.voice_status.text())
        self.assertFalse(self.page.voice_record_button.isEnabled())

    def test_sender_distinguishes_sent_from_delivered(self):
        sent = SimpleNamespace(
            id="voice", direction="outgoing", status="verifying",
            progress=100, path="/tmp/voice.m4a", size=1000,
        )
        delivered = SimpleNamespace(
            id="voice", direction="outgoing", status="delivered",
            progress=100, path="/tmp/voice.m4a", size=1000,
        )
        self.page.set_voice_messages([sent])
        self.assertIn("Voice sent", self.page.voice_status.text())
        self.page.set_voice_messages([delivered])
        self.assertIn("Voice delivered", self.page.voice_status.text())

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

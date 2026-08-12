"""Persistent diagnostic logging contract tests."""

from pathlib import Path
import tempfile
import unittest

from platform_runtime.diagnostic_log import DiagnosticLog


class DiagnosticLogTests(unittest.TestCase):
    def test_persists_session_activity_and_redacts_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "diagnostics" / "mercuryskypulse.log"
            log = DiagnosticLog(path)
            log.start_session("test-version")
            log.write_activity("connected password=hunter2 proof=abcdef token:topsecret")
            log.close()
            content = path.read_text(encoding="utf-8")
            self.assertIn("event=session_start", content)
            self.assertIn("connected", content)
            self.assertIn("password=[REDACTED]", content)
            self.assertNotIn("hunter2", content)
            self.assertNotIn("abcdef", content)
            self.assertNotIn("topsecret", content)

    def test_rotates_and_bounds_long_lines(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mercuryskypulse.log"
            log = DiagnosticLog(path, max_bytes=180, backup_count=2,
                                maximum_message_chars=80)
            for index in range(20):
                log.write_activity(f"line-{index}-" + "x" * 200)
            log.close()
            files = list(Path(directory).glob("mercuryskypulse.log*"))
            self.assertLessEqual(len(files), 3)
            self.assertTrue(any("[truncated]" in item.read_text(encoding="utf-8")
                                for item in files))

    def test_control_characters_cannot_inject_log_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mercuryskypulse.log"
            log = DiagnosticLog(path)
            log.write_activity("first\nforged\x00record")
            log.close()
            content = path.read_text(encoding="utf-8")
            self.assertIn(r"first\nforged?record", content)


if __name__ == "__main__":
    unittest.main()

"""Contract tests for the packaged eSpeak NG operator speech adapter."""

from __future__ import annotations

from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from platform_runtime.builtin_speech import (
    EspeakSynthesizer,
    MAX_SPEECH_CHARACTERS,
    callsign_for_speech,
)


class EspeakSpeechTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.executable = self.root / "espeak-ng"
        self.executable.write_bytes(b"test")
        self.data_parent = self.root / "runtime"
        (self.data_parent / "espeak-ng-data").mkdir(parents=True)
        self.synthesizer = EspeakSynthesizer(self.executable, self.data_parent)

    @patch("platform_runtime.builtin_speech.subprocess.run")
    def test_bounded_phrase_uses_explicit_runtime_without_shell(self, run) -> None:
        destination = self.root / "speech.wav"

        def render(command, **_values):
            Path(command[command.index("-w") + 1]).write_bytes(b"RIFFtest")
            return subprocess.CompletedProcess(command, 0, "", "")

        run.side_effect = render
        self.synthesizer.synthesize_to("Mercury   Sky Pulse", destination)

        command = run.call_args.args[0]
        self.assertEqual(command[0], str(self.executable))
        self.assertIn(f"--path={self.data_parent}", command)
        self.assertEqual(command[-1], "Mercury Sky Pulse")
        self.assertNotIn("shell", run.call_args.kwargs)
        self.assertEqual(destination.read_bytes(), b"RIFFtest")

    def test_empty_phrase_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.synthesizer.synthesize_to("  ", self.root / "speech.wav")

    @patch("platform_runtime.builtin_speech.subprocess.run")
    def test_female_voice_uses_packaged_espeak_variant(self, run) -> None:
        destination = self.root / "female.wav"

        def render(command, **_values):
            destination.write_bytes(b"RIFFtest")
            return subprocess.CompletedProcess(command, 0, "", "")

        run.side_effect = render
        self.synthesizer.synthesize_to("CQ call", destination, "female")
        command = run.call_args.args[0]
        self.assertEqual(command[command.index("-v") + 1], "en-us+f3")

    def test_unknown_voice_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "male or female"):
            self.synthesizer.synthesize_to(
                "CQ call", self.root / "invalid.wav", "robot"
            )

    def test_oversized_phrase_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.synthesizer.synthesize_to(
                "A" * (MAX_SPEECH_CHARACTERS + 1), self.root / "speech.wav"
            )

    @patch("platform_runtime.builtin_speech.subprocess.run")
    def test_nonzero_exit_is_actionable(self, run) -> None:
        run.return_value = subprocess.CompletedProcess([], 2, "", "bad voice")
        with self.assertRaisesRegex(RuntimeError, "bad voice"):
            self.synthesizer.synthesize_to(
                "Mercury Sky Pulse", self.root / "speech.wav"
            )

    def test_callsign_is_spelled_for_clear_announcement(self) -> None:
        self.assertEqual(
            callsign_for_speech("n4eac-2/p"),
            "November four Echo Alpha Charlie dash two stroke Papa",
        )


if __name__ == "__main__":
    unittest.main()

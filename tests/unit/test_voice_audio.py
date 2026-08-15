import struct
from tempfile import TemporaryDirectory
from pathlib import Path
import unittest
from unittest.mock import patch

from PySide6.QtMultimedia import QAudioFormat

from platform_runtime.voice_audio import VoiceAudioEngine


class VoiceAudioLevelTests(unittest.TestCase):
    def test_int16_peak_is_normalized(self):
        data = struct.pack("<hhh", 0, 16384, -32768)
        self.assertEqual(
            VoiceAudioEngine._normalized_peak(
                data, QAudioFormat.SampleFormat.Int16
            ),
            1.0,
        )

    def test_empty_and_unknown_audio_are_silent(self):
        self.assertEqual(
            VoiceAudioEngine._normalized_peak(
                b"", QAudioFormat.SampleFormat.Float
            ),
            0.0,
        )

    def test_finalizer_uses_backend_actual_location(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "actual.m4a"
            path.write_bytes(b"encoded-audio")
            engine = VoiceAudioEngine()
            engine._path = str(path)
            ready = []
            engine.recording_ready.connect(lambda *values: ready.append(values))
            compressed = str(Path(directory) / "actual.voice.ogg")
            with patch(
                "platform_runtime.voice_audio.compress_voice_recording",
                return_value=(compressed, "audio/ogg"),
            ) as compressor:
                engine._finalize_recording(0)
            compressor.assert_called_once_with(str(path))
            self.assertEqual(ready, [(compressed, "audio/ogg")])
            self.assertEqual(engine._requested_path, "")
        self.assertEqual(
            VoiceAudioEngine._normalized_peak(
                b"1234", QAudioFormat.SampleFormat.Unknown
            ),
            0.0,
        )

    def test_discard_removes_actual_and_requested_files(self):
        with TemporaryDirectory() as directory:
            actual = Path(directory) / "actual.m4a"
            requested = Path(directory) / "requested.m4a"
            actual.write_bytes(b"actual")
            requested.write_bytes(b"requested")
            engine = VoiceAudioEngine()
            engine._path = str(actual)
            engine._requested_path = str(requested)

            engine.discard_recording()

            self.assertFalse(actual.exists())
            self.assertFalse(requested.exists())
            self.assertEqual(engine._path, "")
            self.assertEqual(engine._requested_path, "")

    def test_input_gain_is_bounded(self):
        engine = VoiceAudioEngine()
        engine.set_input_gain(35)
        self.assertAlmostEqual(engine._input.volume(), 0.35, places=2)
        engine.set_input_gain(150)
        self.assertAlmostEqual(engine._input.volume(), 1.0, places=2)

    def test_windows_file_lock_does_not_break_discard(self):
        engine = VoiceAudioEngine()
        engine._path = "locked-voice.m4a"
        engine._requested_path = "locked-voice.m4a"
        with patch.object(engine, "_delete_file") as delete_file:
            engine.discard_recording()
        delete_file.assert_called_once_with("locked-voice.m4a")
        self.assertEqual(engine._path, "")
        self.assertEqual(engine._requested_path, "")

    def test_exhausted_windows_file_lock_is_reported_not_raised(self):
        engine = VoiceAudioEngine()
        errors = []
        engine.error_received.connect(errors.append)
        with patch("platform_runtime.voice_audio.Path.unlink", side_effect=PermissionError):
            engine._delete_file("locked-voice.m4a", attempt=20)
        self.assertIn("Windows did not release", errors[-1])


if __name__ == "__main__":
    unittest.main()

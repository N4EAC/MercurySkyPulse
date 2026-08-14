import struct
from tempfile import TemporaryDirectory
from pathlib import Path
import unittest

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
            engine._finalize_recording(0)
            self.assertEqual(ready, [(str(path), "audio/mp4")])
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


if __name__ == "__main__":
    unittest.main()

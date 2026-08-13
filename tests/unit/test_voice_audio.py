import struct
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
        self.assertEqual(
            VoiceAudioEngine._normalized_peak(
                b"1234", QAudioFormat.SampleFormat.Unknown
            ),
            0.0,
        )


if __name__ == "__main__":
    unittest.main()

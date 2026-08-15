from __future__ import annotations

from pathlib import Path
import random
import struct
from tempfile import TemporaryDirectory
import unittest
import wave

import av

from platform_runtime.voice_compression import (
    MAX_VOICE_BYTES,
    compress_voice_recording,
)


class VoiceCompressionTests(unittest.TestCase):
    def test_full_ten_second_worst_case_capture_is_valid_and_bounded(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "capture.wav"
            random_source = random.Random(42)
            with wave.open(str(source), "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(48_000)
                for _ in range(10 * 48_000):
                    output.writeframesraw(struct.pack("<h", random_source.randint(-20_000, 20_000)))

            compressed, mime_type = compress_voice_recording(str(source))

            result = Path(compressed)
            self.assertEqual(mime_type, "audio/ogg")
            self.assertFalse(source.exists())
            self.assertGreater(result.stat().st_size, 0)
            self.assertLessEqual(result.stat().st_size, MAX_VOICE_BYTES)
            with av.open(str(result)) as container:
                stream = container.streams.audio[0]
                duration_seconds = sum(
                    frame.samples / frame.sample_rate
                    for frame in container.decode(stream)
                )
                self.assertGreaterEqual(duration_seconds, 9.875)
                self.assertLessEqual(duration_seconds, 10.0)

    def test_empty_capture_is_rejected_without_output(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "empty.m4a"
            source.write_bytes(b"")
            with self.assertRaisesRegex(ValueError, "empty"):
                compress_voice_recording(str(source))
            self.assertFalse(source.with_suffix(".voice.ogg").exists())


if __name__ == "__main__":
    unittest.main()

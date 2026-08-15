from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.validate_voice_package import validate


class VoicePackageValidatorTests(unittest.TestCase):
    def test_accepts_binding_and_native_backend(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "QtMultimedia.abi3.so").touch()
            (root / "libffmpegmediaplugin.dylib").touch()
            (root / "libavcodec.62.dylib").touch()
            (root / "PYAV_LICENSE.txt").touch()
            (root / "THIRD_PARTY_NOTICES.md").touch()
            self.assertEqual(validate(root), [])

    def test_reports_each_missing_component(self):
        with TemporaryDirectory() as directory:
            errors = validate(Path(directory))
            self.assertEqual(len(errors), 5)
            self.assertIn("QtMultimedia", errors[0])
            self.assertIn("backend", errors[1])
            self.assertIn("PyAV", errors[2])
            self.assertIn("license", errors[3])
            self.assertIn("notices", errors[4])


if __name__ == "__main__":
    unittest.main()

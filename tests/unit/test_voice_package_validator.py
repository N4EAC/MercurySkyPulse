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
            self.assertEqual(validate(root), [])

    def test_reports_each_missing_component(self):
        with TemporaryDirectory() as directory:
            errors = validate(Path(directory))
            self.assertEqual(len(errors), 2)
            self.assertIn("QtMultimedia", errors[0])
            self.assertIn("backend", errors[1])


if __name__ == "__main__":
    unittest.main()

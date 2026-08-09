import subprocess
import sys
import unittest


class PresentationLauncherTests(unittest.TestCase):
    def test_package_import_does_not_import_qt_application(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import sys; import presentation; "
                    "print('presentation.app' in sys.modules); "
                    "print(any(name.startswith('PySide6') for name in sys.modules))"
                ),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.stdout.splitlines(), ["False", "False"])


if __name__ == "__main__":
    unittest.main()

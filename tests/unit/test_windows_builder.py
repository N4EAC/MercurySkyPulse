from pathlib import Path
import unittest


class WindowsBuilderContractTests(unittest.TestCase):
    def test_builder_locates_and_packages_mercury(self) -> None:
        root = Path(__file__).resolve().parents[2]
        script = (root / "build.exe.bat").read_text(encoding="utf-8").casefold()
        self.assertIn("call :find_mercury", script)
        self.assertIn("if defined mercury_executable", script)
        self.assertIn("where mercury.exe", script)
        self.assertIn(
            'copy /y "%msp_mercury%" "dist\\mercuryskypulse\\mercury.exe"',
            script,
        )
        self.assertIn("goto failed", script)


if __name__ == "__main__":
    unittest.main()

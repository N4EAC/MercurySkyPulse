from pathlib import Path
import unittest


class WindowsBuilderContractTests(unittest.TestCase):
    def test_builder_downloads_verifies_and_packages_pinned_mercury(self) -> None:
        root = Path(__file__).resolve().parents[2]
        script = (root / "build.exe.bat").read_text(encoding="utf-8").casefold()
        self.assertIn("msp_mercury_version=1.9.11-msp-9803d0fc", script)
        self.assertIn("msp_mercury_commit=9803d0fcd690de76309dbe62d9186a0d34dba507", script)
        self.assertIn("e7a2563242dd2d3a57b1380a780d9b702a3c4f2050ff6f7e3c87bd31d4c80b25", script)
        self.assertIn("github.com/n4eac/mercury/releases/download", script)
        self.assertIn("github.com/n4eac/mercury/tree/%msp_mercury_commit%", script)
        self.assertIn("call :prepare_mercury", script)
        self.assertIn("invoke-webrequest", script)
        self.assertIn("get-filehash", script)
        self.assertIn("expand-archive", script)
        self.assertIn(
            'xcopy /e /i /y "%msp_mercury_runtime%\\*" '
            '"dist\\mercuryskypulse\\mercury"',
            script,
        )
        self.assertIn("mercury\\source.txt", script)
        self.assertIn('if not exist "%msp_mercury_runtime%\\license"', script)
        self.assertIn("--icon assets\\icons\\mercuryskypulse.ico", script)
        self.assertIn("mercuryskypulse.png;assets\\icons", script)
        self.assertIn("tools\\validate_voice_package.py", script)
        self.assertIn("goto failed", script)


if __name__ == "__main__":
    unittest.main()

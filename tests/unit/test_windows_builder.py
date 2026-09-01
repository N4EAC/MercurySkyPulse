from pathlib import Path
import unittest


class WindowsBuilderContractTests(unittest.TestCase):
    def test_builder_downloads_verifies_and_packages_pinned_mercury(self) -> None:
        root = Path(__file__).resolve().parents[2]
        script = (root / "build.exe.bat").read_text(encoding="utf-8").casefold()
        self.assertIn("msp_mercury_version=1.9.13-msp-7febb890", script)
        self.assertIn("msp_mercury_commit=7febb89062e1380487592b42011092d84c60cd5c", script)
        self.assertIn("b62ab557e213bc35d58abdfc21c9c82666fad411326e55c8313a52ee474ab52a", script)
        self.assertIn("msp-1.9.13-upstream-frequency-1", script)
        self.assertIn("github.com/n4eac/mercury/releases/download", script)
        self.assertIn("github.com/rhizomatica/mercury/tree/%msp_mercury_commit%", script)
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
        self.assertIn("radio_frequency_hz", script)
        self.assertIn("arq_tx_mode", script)
        self.assertIn("arq_rx_mode", script)
        self.assertIn("--icon assets\\icons\\mercuryskypulse.ico", script)
        self.assertIn("mercuryskypulse.png;assets\\icons", script)
        self.assertNotIn("validate_voice_package", script)
        self.assertNotIn("pyav_license", script)
        self.assertIn("goto failed", script)


if __name__ == "__main__":
    unittest.main()

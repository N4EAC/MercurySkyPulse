from pathlib import Path
import unittest


class WindowsBuilderContractTests(unittest.TestCase):
    def test_builder_downloads_verifies_and_packages_pinned_mercury(self) -> None:
        root = Path(__file__).resolve().parents[2]
        script = (root / "build.exe.bat").read_text(encoding="utf-8").casefold()
        self.assertIn("msp_mercury_version=1.9.23", script)
        self.assertIn("msp_mercury_commit=09f258f84a0b69cb4d8556530a25822617ea17dd", script)
        self.assertIn("46959d9878f15cc41e4f2282e55511413e1a89cde33f77085e3f2ed2df96daf1", script)
        self.assertIn("releases/download/v1.9.23", script)
        self.assertIn("github.com/rhizomatica/mercury/releases/download", script)
        self.assertIn("raw.githubusercontent.com/rhizomatica/mercury", script)
        self.assertIn("msp_mercury_license_sha256", script)
        self.assertIn("msp_mercury_freedv_license_sha256", script)
        self.assertIn("msp_mercury_hamlib_license_sha256", script)
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
        self.assertIn("copying.lib.txt", script)
        self.assertIn("mercury license download or sha-256 verification failed", script)
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

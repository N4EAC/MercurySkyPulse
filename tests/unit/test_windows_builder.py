from pathlib import Path
import unittest


class WindowsBuilderContractTests(unittest.TestCase):
    def test_builder_downloads_verifies_and_packages_pinned_mercury(self) -> None:
        root = Path(__file__).resolve().parents[2]
        script = (root / "build.exe.bat").read_text(encoding="utf-8").casefold()
        self.assertIn("msp_mercury_version=1.9.11", script)
        self.assertIn("a88c7739428e7afe864791a964d5f8eaa0fc73d6d0a60c016a6df0a5e30a9e78", script)
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
        self.assertIn("--icon assets\\icons\\mercuryskypulse.ico", script)
        self.assertIn("mercuryskypulse.png;assets\\icons", script)
        self.assertIn("goto failed", script)


if __name__ == "__main__":
    unittest.main()

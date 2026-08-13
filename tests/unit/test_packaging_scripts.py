"""Static safeguards for native packaging entry points."""

from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class PackagingScriptTests(unittest.TestCase):
    def test_windows_installer_wraps_complete_portable_runtime(self) -> None:
        installer = (ROOT / "packaging/windows/MercurySkyPulse.iss").read_text(
            encoding="utf-8"
        )
        builder = (ROOT / "build.exe.bat").read_text(encoding="utf-8")
        self.assertIn("SetupIconFile=", installer)
        self.assertIn('Source: "..\\..\\dist\\MercurySkyPulse\\*"', installer)
        self.assertIn("recursesubdirs createallsubdirs", installer)
        self.assertIn("call :build_installer", builder)
        self.assertIn("Inno Setup 6", builder)

    def test_linux_builder_requires_and_bundles_mercury(self) -> None:
        builder = (ROOT / "build.linux.sh").read_text(encoding="utf-8")
        self.assertIn('MERCURY_SOURCE="${MERCURY_EXECUTABLE:-', builder)
        self.assertIn('install -m 0755 "$MERCURY_SOURCE"', builder)
        self.assertIn("dpkg-deb --build", builder)
        self.assertIn("rpmbuild", builder)
        self.assertIn("mercuryskypulse-256.png", builder)

    def test_linux_desktop_entry_uses_installed_application(self) -> None:
        desktop = (ROOT / "packaging/linux/mercuryskypulse.desktop").read_text(
            encoding="utf-8"
        )
        self.assertIn("Exec=/opt/mercuryskypulse/MercurySkyPulse", desktop)
        self.assertIn("Icon=mercuryskypulse", desktop)


if __name__ == "__main__":
    unittest.main()

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
        self.assertIn('candidate="${MERCURY_EXECUTABLE:-}"', builder)
        self.assertIn("MERCURY_ARCHIVE_SHA256=", builder)
        self.assertIn('curl -L --fail --show-error "$MERCURY_ARCHIVE_URL"', builder)
        self.assertIn('make -C "$MERCURY_ROOT"', builder)
        self.assertIn('grep -a -q "radio_frequency_hz" "$MERCURY_SOURCE"', builder)
        self.assertIn('install -m 0755 "$MERCURY_SOURCE"', builder)
        self.assertIn("dpkg-deb --build", builder)
        self.assertIn("rpmbuild", builder)
        self.assertIn("mercuryskypulse-256.png", builder)
        rpm_spec = (ROOT / "packaging/linux/mercury-skypulse.spec.in").read_text(
            encoding="utf-8"
        )
        self.assertIn("%global debug_package %{nil}", rpm_spec)
        self.assertIn("%global __requires_exclude ^libtiff[.]so[.]5.*$", rpm_spec)
        self.assertIn(
            "ln -s ../../opt/mercuryskypulse/MercurySkyPulse", rpm_spec
        )
        self.assertIn("rpm -qpR", builder)
        self.assertIn("plugins/multimedia/.*mediaplugin", builder)
        self.assertIn("tools/validate_voice_package.py", builder)
        self.assertIn("pipewire-libs", rpm_spec)
        deb_control = (ROOT / "packaging/linux/debian-control.in").read_text(
            encoding="utf-8"
        )
        self.assertIn("libpipewire-0.3-0", deb_control)

    def test_linux_desktop_entry_uses_installed_application(self) -> None:
        desktop = (ROOT / "packaging/linux/mercuryskypulse.desktop").read_text(
            encoding="utf-8"
        )
        self.assertIn("Exec=/opt/mercuryskypulse/MercurySkyPulse", desktop)
        self.assertIn("Icon=mercuryskypulse", desktop)


if __name__ == "__main__":
    unittest.main()

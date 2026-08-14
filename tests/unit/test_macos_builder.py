from pathlib import Path
import unittest


class MacosBuilderContractTests(unittest.TestCase):
    def test_builder_creates_named_application_bundle(self) -> None:
        root = Path(__file__).resolve().parents[2]
        script = (root / "build.app.sh").read_text(encoding="utf-8")
        self.assertIn("--windowed", script)
        self.assertIn("--name MercurySkyPulse", script)
        self.assertIn("--icon \"$PROJECT_ROOT/assets/icons/mercuryskypulse.icns\"", script)
        self.assertIn("mercuryskypulse.png:assets/icons", script)
        self.assertIn('MERCURY_SOURCE="${MERCURY_EXECUTABLE:-', script)
        self.assertIn('--add-binary "$MERCURY_RUNTIME/mercury:mercury"', script)
        self.assertIn('--add-data "$MERCURY_RUNTIME/LICENSE:mercury"', script)
        self.assertIn("MERCURY_REVISION", script)
        self.assertIn("--osx-bundle-identifier org.mercuryskypulse.desktop", script)
        self.assertIn("NSMicrophoneUsageDescription", script)
        self.assertIn("tools/validate_voice_package.py", script)
        self.assertIn("codesign --force --deep --sign -", script)
        self.assertIn("dist/MercurySkyPulse.app", script)

    def test_dmg_builder_creates_drag_install_layout(self) -> None:
        root = Path(__file__).resolve().parents[2]
        script = (root / "build.dmg.sh").read_text(encoding="utf-8")
        self.assertIn('APP="$PROJECT_ROOT/dist/MercurySkyPulse.app"', script)
        self.assertIn('ln -s /Applications "$STAGING/Applications"', script)
        self.assertIn('ditto "$APP" "$STAGING/MercurySkyPulse.app"', script)
        self.assertIn("hdiutil create", script)
        self.assertIn("-format UDZO", script)
        self.assertIn('hdiutil verify "$OUTPUT"', script)
        self.assertIn("MercurySkyPulse-$VERSION-macos-arm64.dmg", script)


if __name__ == "__main__":
    unittest.main()

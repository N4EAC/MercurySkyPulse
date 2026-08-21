#!/bin/zsh
set -euo pipefail

PROJECT_ROOT="${0:A:h}"
VERSION="${MSP_VERSION:-0.1.2}"
APP="$PROJECT_ROOT/dist/MercurySkyPulse.app"
OUTPUT_DIR="$PROJECT_ROOT/dist/installer"
OUTPUT="$OUTPUT_DIR/MercurySkyPulse-$VERSION-macos-arm64.dmg"
ARCHIVE="$OUTPUT.zip"
STAGING="$(mktemp -d "${TMPDIR:-/tmp}/msp-dmg.XXXXXX")"

cleanup() {
    rm -rf "$STAGING"
}
trap cleanup EXIT

cd "$PROJECT_ROOT"

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
    print -u2 "ERROR: The current DMG builder requires an Apple Silicon Mac."
    exit 1
fi
if ! command -v hdiutil >/dev/null 2>&1; then
    print -u2 "ERROR: macOS hdiutil is required."
    exit 1
fi

if [[ "${MSP_SKIP_APP_BUILD:-0}" != "1" ]]; then
    ./build.app.sh
fi
if [[ ! -d "$APP" ]]; then
    print -u2 "ERROR: Application bundle not found at $APP"
    exit 1
fi

codesign --verify --deep --strict "$APP"
[[ "$(plutil -extract CFBundleName raw "$APP/Contents/Info.plist")" == "Mercury SkyPulse" ]]
test -x "$APP/Contents/Frameworks/mercury/mercury"
print "Verifying bounded Opus compression, bilateral bitrate gating, and voice protocol 2 in the DMG payload..."
"$PROJECT_ROOT/.venv-build-macos/bin/python" \
    tools/validate_voice_package.py "$APP"

ditto "$APP" "$STAGING/MercurySkyPulse.app"
ln -s /Applications "$STAGING/Applications"
cp LICENSE "$STAGING/LICENSE.txt"
cp THIRD_PARTY_NOTICES.md "$STAGING/THIRD_PARTY_NOTICES.md"

mkdir -p "$OUTPUT_DIR"
rm -f "$OUTPUT"
rm -f "$ARCHIVE"
hdiutil create \
    -volname "Mercury SkyPulse $VERSION" \
    -srcfolder "$STAGING" \
    -format UDZO \
    -imagekey zlib-level=9 \
    -ov "$OUTPUT"

hdiutil verify "$OUTPUT" >/dev/null
print
print "DMG complete: $OUTPUT"
print "Open it with: open '$OUTPUT'"

GIT_ARTIFACT_LIMIT=$((50 * 1024 * 1024))
if (( $(stat -f%z "$OUTPUT") > GIT_ARTIFACT_LIMIT )); then
    ditto -c -k --sequesterRsrc "$OUTPUT" "$ARCHIVE"
    print "Repository artifact (DMG exceeds 50 MiB): $ARCHIVE"
fi

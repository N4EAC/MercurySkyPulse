#!/bin/zsh
set -euo pipefail

PROJECT_ROOT="${0:A:h}"
BUILD_VENV="$PROJECT_ROOT/.venv-build-macos"
PYTHON_BIN="${PYTHON_BIN:-python3}"
MERCURY_SOURCE="${MERCURY_EXECUTABLE:-$PROJECT_ROOT/../mercury/mercury}"
MERCURY_ROOT="${MERCURY_SOURCE:h}"
MERCURY_RUNTIME="$PROJECT_ROOT/build/mercury-macos-runtime"

cd "$PROJECT_ROOT"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    print -u2 "ERROR: Python 3.11 or newer is required."
    exit 1
fi

if [[ ! -x "$MERCURY_SOURCE" ]]; then
    print -u2 "ERROR: A runnable macOS Mercury executable was not found at:"
    print -u2 "       $MERCURY_SOURCE"
    print -u2 "Build the sibling Mercury checkout first or set MERCURY_EXECUTABLE."
    exit 1
fi
if [[ ! -f "$MERCURY_ROOT/LICENSE" || ! -f "$MERCURY_ROOT/LICENSE-freedv" ]]; then
    print -u2 "ERROR: Mercury license files are missing beside $MERCURY_SOURCE"
    exit 1
fi

mkdir -p "$MERCURY_RUNTIME"
cp "$MERCURY_SOURCE" "$MERCURY_RUNTIME/mercury"
chmod 755 "$MERCURY_RUNTIME/mercury"
cp "$MERCURY_ROOT/LICENSE" "$MERCURY_RUNTIME/LICENSE"
cp "$MERCURY_ROOT/LICENSE-freedv" "$MERCURY_RUNTIME/LICENSE-freedv"
MERCURY_REVISION="$(git -C "$MERCURY_ROOT" rev-parse HEAD 2>/dev/null || print unknown)"
MERCURY_REMOTE="$(git -C "$MERCURY_ROOT" remote get-url origin 2>/dev/null || print unknown)"
{
    print "Mercury macOS engineering runtime"
    print "Source: $MERCURY_REMOTE"
    print "Revision: $MERCURY_REVISION"
    print "License: GNU GPL-3.0-or-later; see LICENSE."
} > "$MERCURY_RUNTIME/SOURCE.txt"

"$PYTHON_BIN" -m venv "$BUILD_VENV"
"$BUILD_VENV/bin/python" -m pip install --upgrade pip
"$BUILD_VENV/bin/python" -m pip install -e . pyinstaller
if [[ "${MSP_SKIP_TESTS:-0}" != "1" ]]; then
    PYTHONDONTWRITEBYTECODE=1 "$BUILD_VENV/bin/python" tools/run_tests.py all -q
fi

"$BUILD_VENV/bin/pyinstaller" \
    --noconfirm \
    --clean \
    --windowed \
    --onedir \
    --name MercurySkyPulse \
    --icon "$PROJECT_ROOT/assets/icons/mercuryskypulse.icns" \
    --add-data "$PROJECT_ROOT/assets/icons/mercuryskypulse.png:assets/icons" \
    --add-binary "$MERCURY_RUNTIME/mercury:mercury" \
    --add-data "$MERCURY_RUNTIME/LICENSE:mercury" \
    --add-data "$MERCURY_RUNTIME/LICENSE-freedv:mercury" \
    --add-data "$MERCURY_RUNTIME/SOURCE.txt:mercury" \
    --osx-bundle-identifier org.mercuryskypulse.desktop \
    --distpath "$PROJECT_ROOT/dist" \
    --workpath "$PROJECT_ROOT/build/pyinstaller-macos" \
    --specpath "$PROJECT_ROOT/build/pyinstaller-macos" \
    "$PROJECT_ROOT/apps/desktop/main.py"

APP="$PROJECT_ROOT/dist/MercurySkyPulse.app"
PLIST="$APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Delete :NSMicrophoneUsageDescription" "$PLIST" >/dev/null 2>&1 || true
/usr/libexec/PlistBuddy -c \
    "Add :NSMicrophoneUsageDescription string MercurySkyPulse records short voice messages when the operator presses Record Voice." \
    "$PLIST"
"$BUILD_VENV/bin/python" tools/validate_voice_package.py "$APP"
# Editing Info.plist invalidates PyInstaller's ad-hoc signature.
codesign --force --deep --sign - "$APP"

print
print "Build complete: $APP"
print "Launch with: open '$APP'"

#!/bin/zsh
set -euo pipefail

PROJECT_ROOT="${0:A:h:h}"
LOCAL_PYTHON="${MSP_LOCAL_PYTHON:-$PROJECT_ROOT/.venv/bin/python}"

cd "$PROJECT_ROOT"

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
    print -u2 "ERROR: The canonical local gate requires an Apple Silicon Mac."
    exit 1
fi
if [[ ! -x "$LOCAL_PYTHON" ]]; then
    print -u2 "ERROR: Local Python environment not found at $LOCAL_PYTHON"
    exit 1
fi

print "[1/7] Checking patch hygiene"
git diff --check

print "[2/7] Validating installed dependencies"
"$LOCAL_PYTHON" -m pip check

print "[3/7] Compiling Python sources"
"$LOCAL_PYTHON" -m compileall -q src tests tools

print "[4/7] Running unit, contract, protocol, transfer, and GUI tests"
QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 \
    "$LOCAL_PYTHON" tools/run_tests.py all -q

print "[5/7] Building the macOS application bundle"
MSP_SKIP_TESTS=1 ./build.app.sh

APP="$PROJECT_ROOT/dist/MercurySkyPulse.app"
MERCURY="$APP/Contents/Frameworks/mercury/mercury"
ESPEAK="$APP/Contents/Frameworks/espeak/espeak-ng"
print "[6/7] Validating bundle identity, signature, icon, and packaged runtimes"
test -x "$APP/Contents/MacOS/MercurySkyPulse"
test -x "$MERCURY"
test -f "$APP/Contents/Resources/mercuryskypulse.icns"
test -f "$APP/Contents/Resources/mercury/LICENSE"
test -f "$APP/Contents/Resources/mercury/LICENSE-freedv"
test -f "$APP/Contents/Resources/mercury/SOURCE.txt"
test -x "$ESPEAK"
test -f "$APP/Contents/Resources/espeak/espeak-ng-data/en_dict"
test -f "$APP/Contents/Resources/espeak/LICENSE"
test -f "$APP/Contents/Resources/espeak/SOURCE.txt"
codesign --verify --deep --strict "$APP"
[[ "$(plutil -extract CFBundleName raw "$APP/Contents/Info.plist")" == "Mercury SkyPulse" ]]
[[ "$(plutil -extract CFBundleDisplayName raw "$APP/Contents/Info.plist")" == "Mercury SkyPulse" ]]
[[ "$(plutil -extract CFBundleShortVersionString raw "$APP/Contents/Info.plist")" == "0.1.7" ]]
[[ "$(plutil -extract CFBundleVersion raw "$APP/Contents/Info.plist")" == "0.1.7" ]]
[[ "$(file -b "$MERCURY")" == *"Mach-O 64-bit executable arm64"* ]]
[[ "$(file -b "$ESPEAK")" == *"Mach-O 64-bit executable arm64"* ]]
SPEECH_TEST="$(mktemp -d)/msp-speech.wav"
"$ESPEAK" --path="$APP/Contents/Resources/espeak" -w "$SPEECH_TEST" \
    "Mercury Sky Pulse"
test -s "$SPEECH_TEST"

print "[7/7] Local quality gate passed"
print "Packaged GUI launch remains a manual RF-safe operator check."

#!/bin/zsh
set -euo pipefail

PROJECT_ROOT="${0:A:h}"
BUILD_VENV="$PROJECT_ROOT/.venv-build-macos"
PYTHON_BIN="${PYTHON_BIN:-python3}"

cd "$PROJECT_ROOT"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    print -u2 "ERROR: Python 3.11 or newer is required."
    exit 1
fi

"$PYTHON_BIN" -m venv "$BUILD_VENV"
"$BUILD_VENV/bin/python" -m pip install --upgrade pip
"$BUILD_VENV/bin/python" -m pip install -e . pyinstaller
PYTHONDONTWRITEBYTECODE=1 "$BUILD_VENV/bin/python" tools/run_tests.py all -q

"$BUILD_VENV/bin/pyinstaller" \
    --noconfirm \
    --clean \
    --windowed \
    --onedir \
    --name MercurySkyPulse \
    --osx-bundle-identifier org.mercuryskypulse.desktop \
    --distpath "$PROJECT_ROOT/dist" \
    --workpath "$PROJECT_ROOT/build/pyinstaller-macos" \
    --specpath "$PROJECT_ROOT/build/pyinstaller-macos" \
    "$PROJECT_ROOT/apps/desktop/main.py"

print
print "Build complete: $PROJECT_ROOT/dist/MercurySkyPulse.app"
print "Launch with: open '$PROJECT_ROOT/dist/MercurySkyPulse.app'"

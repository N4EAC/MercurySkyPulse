#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
BUILD_VENV="$PROJECT_ROOT/.venv-build-linux"
MERCURY_SOURCE="${MERCURY_EXECUTABLE:-$PROJECT_ROOT/../mercury/mercury}"
MERCURY_ROOT="$(dirname "$MERCURY_SOURCE")"
VERSION="${MSP_VERSION:-0.1.0}"
ARCH="$(uname -m)"

cd "$PROJECT_ROOT"

if [[ "$(uname -s)" != "Linux" ]]; then
    echo "ERROR: Linux packages must be built and validated on Linux." >&2
    exit 1
fi
if [[ "$ARCH" != "x86_64" ]]; then
    echo "ERROR: The initial Linux packages support x86_64 only (found $ARCH)." >&2
    exit 1
fi
if [[ ! -x "$MERCURY_SOURCE" ]]; then
    echo "ERROR: A compatible Linux Mercury executable was not found at:" >&2
    echo "       $MERCURY_SOURCE" >&2
    echo "Build the sibling Mercury checkout or set MERCURY_EXECUTABLE." >&2
    exit 1
fi
if [[ ! -f "$MERCURY_ROOT/LICENSE" || ! -f "$MERCURY_ROOT/LICENSE-freedv" ]]; then
    echo "ERROR: Mercury LICENSE and LICENSE-freedv must accompany the runtime." >&2
    exit 1
fi

if command -v dpkg-deb >/dev/null 2>&1; then
    PACKAGE_KIND=deb
elif command -v rpmbuild >/dev/null 2>&1; then
    PACKAGE_KIND=rpm
else
    echo "ERROR: Install dpkg-deb on Ubuntu or rpm-build on Fedora." >&2
    exit 1
fi

"$PYTHON_BIN" -m venv "$BUILD_VENV"
"$BUILD_VENV/bin/python" -m pip install --upgrade pip
"$BUILD_VENV/bin/python" -m pip install -e . pyinstaller
if [[ "${MSP_SKIP_TESTS:-0}" != "1" ]]; then
    QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 \
        "$BUILD_VENV/bin/python" tools/run_tests.py all -q
fi

rm -rf build/pyinstaller-linux dist/MercurySkyPulse
"$BUILD_VENV/bin/pyinstaller" \
    --noconfirm --clean --windowed --onedir \
    --name MercurySkyPulse \
    --icon "$PROJECT_ROOT/assets/icons/linux/mercuryskypulse-256.png" \
    --add-data "$PROJECT_ROOT/assets/icons/mercuryskypulse.png:assets/icons" \
    --distpath "$PROJECT_ROOT/dist" \
    --workpath "$PROJECT_ROOT/build/pyinstaller-linux" \
    --specpath "$PROJECT_ROOT/build/pyinstaller-linux" \
    "$PROJECT_ROOT/apps/desktop/main.py"

mkdir -p dist/MercurySkyPulse/mercury
install -m 0755 "$MERCURY_SOURCE" dist/MercurySkyPulse/mercury/mercury
install -m 0644 "$MERCURY_ROOT/LICENSE" dist/MercurySkyPulse/mercury/LICENSE
install -m 0644 "$MERCURY_ROOT/LICENSE-freedv" dist/MercurySkyPulse/mercury/LICENSE-freedv
MERCURY_REVISION="$(git -C "$MERCURY_ROOT" rev-parse HEAD 2>/dev/null || echo unknown)"
MERCURY_REMOTE="$(git -C "$MERCURY_ROOT" remote get-url origin 2>/dev/null || echo unknown)"
printf 'Mercury Linux engineering runtime\nSource: %s\nRevision: %s\nLicense: GNU GPL-3.0-or-later; see LICENSE.\n' \
    "$MERCURY_REMOTE" "$MERCURY_REVISION" > dist/MercurySkyPulse/mercury/SOURCE.txt
install -m 0644 LICENSE dist/MercurySkyPulse/LICENSE

mkdir -p dist/packages
if [[ "$PACKAGE_KIND" == deb ]]; then
    STAGE="build/package-linux/deb"
    rm -rf "$STAGE"
    mkdir -p "$STAGE/DEBIAN" "$STAGE/opt/mercuryskypulse" \
        "$STAGE/usr/bin" "$STAGE/usr/share/applications" \
        "$STAGE/usr/share/icons/hicolor/256x256/apps"
    cp -a dist/MercurySkyPulse/. "$STAGE/opt/mercuryskypulse/"
    ln -s /opt/mercuryskypulse/MercurySkyPulse "$STAGE/usr/bin/mercury-skypulse"
    sed "s/@VERSION@/$VERSION/g" packaging/linux/debian-control.in > "$STAGE/DEBIAN/control"
    install -m 0644 packaging/linux/mercuryskypulse.desktop "$STAGE/usr/share/applications/"
    install -m 0644 assets/icons/linux/mercuryskypulse-256.png "$STAGE/usr/share/icons/hicolor/256x256/apps/mercuryskypulse.png"
    dpkg-deb --build --root-owner-group "$STAGE" "dist/packages/mercury-skypulse_${VERSION}_amd64.deb"
    dpkg-deb --info "dist/packages/mercury-skypulse_${VERSION}_amd64.deb" >/dev/null
    echo "Package complete: dist/packages/mercury-skypulse_${VERSION}_amd64.deb"
else
    RPM_TOP="$PROJECT_ROOT/build/package-linux/rpm"
    SOURCE_DIR="$RPM_TOP/source/mercury-skypulse-$VERSION"
    rm -rf "$RPM_TOP"
    mkdir -p "$RPM_TOP"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS} "$SOURCE_DIR/app"
    cp -a dist/MercurySkyPulse/. "$SOURCE_DIR/app/"
    cp packaging/linux/mercuryskypulse.desktop "$SOURCE_DIR/"
    cp assets/icons/linux/mercuryskypulse-256.png "$SOURCE_DIR/mercuryskypulse.png"
    tar -C "$RPM_TOP/source" -czf "$RPM_TOP/SOURCES/mercury-skypulse-$VERSION.tar.gz" "mercury-skypulse-$VERSION"
    RPM_VERSION="${VERSION//-/.}"
    sed -e "s/@VERSION@/$VERSION/g" -e "s/@RPM_VERSION@/$RPM_VERSION/g" \
        packaging/linux/mercury-skypulse.spec.in > "$RPM_TOP/SPECS/mercury-skypulse.spec"
    rpmbuild --define "_topdir $RPM_TOP" -bb "$RPM_TOP/SPECS/mercury-skypulse.spec"
    find "$RPM_TOP/RPMS" -name '*.rpm' -exec cp {} dist/packages/ \;
    rpm -qpi dist/packages/mercury-skypulse-*.rpm >/dev/null
    echo "Package complete: dist/packages/mercury-skypulse-${RPM_VERSION}-1.*.x86_64.rpm"
fi

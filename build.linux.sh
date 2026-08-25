#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
BUILD_VENV="$PROJECT_ROOT/.venv-build-linux"
MERCURY_COMMIT="84d35fbcb0377e536d9123cb0650735a5b41ae01"
MERCURY_ARCHIVE_SHA256="11109ff84924ae5654881065aa2c30c3f0b6a2227801974dff056ec49119d4a0"
MERCURY_ARCHIVE_URL="https://github.com/N4EAC/mercury/archive/$MERCURY_COMMIT.tar.gz"
MERCURY_CACHE="$PROJECT_ROOT/build/mercury-linux-runtime"
MERCURY_ROOT=""
MERCURY_SOURCE=""
MERCURY_REVISION=""
MERCURY_REMOTE=""
MERCURY_HAMLIB_CFLAGS=""
ESPEAK_BIN="${ESPEAK_EXECUTABLE:-$(command -v espeak-ng || true)}"
ESPEAK_DATA_DIR="${ESPEAK_DATA_DIR:-}"
ESPEAK_VERSION=""
ESPEAK_RUNTIME="$PROJECT_ROOT/build/espeak-linux-runtime"
VERSION="${MSP_VERSION:-0.1.7}"
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
if [[ ! -x "$ESPEAK_BIN" ]]; then
    echo "ERROR: eSpeak NG is required for offline announcements." >&2
    echo "Fedora: sudo dnf install espeak-ng" >&2
    echo "Ubuntu: sudo apt install espeak-ng" >&2
    exit 1
fi

discover_espeak_data() {
    local candidate=""
    if [[ -n "$ESPEAK_DATA_DIR" ]]; then
        return
    fi
    for candidate in \
        /usr/share/espeak-ng-data \
        "/usr/lib/$ARCH-linux-gnu/espeak-ng-data" \
        /usr/lib64/espeak-ng-data \
        /usr/local/share/espeak-ng-data; do
        if [[ -d "$candidate" ]]; then
            ESPEAK_DATA_DIR="$candidate"
            return
        fi
    done
    if command -v dpkg-query >/dev/null 2>&1; then
        candidate="$(dpkg-query -L espeak-ng-data 2>/dev/null \
            | awk '/\/espeak-ng-data$/ { print; exit }')"
        if [[ -d "$candidate" ]]; then
            ESPEAK_DATA_DIR="$candidate"
            return
        fi
    fi
    if command -v rpm >/dev/null 2>&1; then
        candidate="$(rpm -ql espeak-ng 2>/dev/null \
            | awk '/\/espeak-ng-data$/ { print; exit }')"
        if [[ -d "$candidate" ]]; then
            ESPEAK_DATA_DIR="$candidate"
        fi
    fi
}

discover_espeak_data
if [[ ! -d "$ESPEAK_DATA_DIR" ]]; then
    echo "ERROR: eSpeak NG voice data could not be located." >&2
    echo "Detected executable: $ESPEAK_BIN" >&2
    echo "Ubuntu: sudo apt install espeak-ng espeak-ng-data" >&2
    echo "Fedora: sudo dnf install espeak-ng" >&2
    echo "Or set ESPEAK_DATA_DIR to the directory named espeak-ng-data." >&2
    exit 1
fi
ESPEAK_VERSION="$("$ESPEAK_BIN" --version 2>&1 \
    | awk 'match($0, /[0-9]+\.[0-9]+(\.[0-9]+)?/) { print substr($0, RSTART, RLENGTH); exit }')"
ESPEAK_VERSION="${ESPEAK_VERSION:-distribution-version}"
ESPEAK_TEST_DIR="$PROJECT_ROOT/build/espeak-linux-smoke"
rm -rf "$ESPEAK_TEST_DIR"
mkdir -p "$ESPEAK_TEST_DIR"
if ! "$ESPEAK_BIN" -v en-us+m3 -w "$ESPEAK_TEST_DIR/male.wav" \
        "Mercury Sky Pulse" >/dev/null 2>&1 \
    || ! "$ESPEAK_BIN" -v en-us+f3 -w "$ESPEAK_TEST_DIR/female.wav" \
        "CQ call" >/dev/null 2>&1 \
    || [[ ! -s "$ESPEAK_TEST_DIR/male.wav" \
        || ! -s "$ESPEAK_TEST_DIR/female.wav" ]]; then
    echo "ERROR: The installed eSpeak NG cannot render MSP's male/female voices." >&2
    echo "Executable: $ESPEAK_BIN" >&2
    echo "Voice data: $ESPEAK_DATA_DIR" >&2
    exit 1
fi
echo "Using eSpeak NG $ESPEAK_VERSION: $ESPEAK_BIN"
echo "Using eSpeak NG voice data: $ESPEAK_DATA_DIR"
if command -v dpkg-deb >/dev/null 2>&1; then
    PACKAGE_KIND=deb
elif command -v rpmbuild >/dev/null 2>&1; then
    PACKAGE_KIND=rpm
else
    echo "ERROR: Install dpkg-deb on Ubuntu or rpm-build on Fedora." >&2
    exit 1
fi

prepare_mercury() {
    local candidate="${MERCURY_EXECUTABLE:-}"
    if [[ -n "$candidate" ]]; then
        if [[ ! -x "$candidate" ]]; then
            echo "ERROR: MERCURY_EXECUTABLE is not runnable: $candidate" >&2
            exit 1
        fi
        MERCURY_SOURCE="$(cd "$(dirname "$candidate")" && pwd)/$(basename "$candidate")"
        MERCURY_ROOT="$(dirname "$MERCURY_SOURCE")"
        MERCURY_REVISION="external-runtime"
        MERCURY_REMOTE="operator-supplied MERCURY_EXECUTABLE"
        return
    fi

    candidate="$PROJECT_ROOT/../mercury/mercury"
    if [[ -x "$candidate" ]]; then
        MERCURY_SOURCE="$(cd "$(dirname "$candidate")" && pwd)/mercury"
        MERCURY_ROOT="$(dirname "$MERCURY_SOURCE")"
        MERCURY_REVISION="$(git -C "$MERCURY_ROOT" rev-parse HEAD 2>/dev/null || echo sibling-checkout)"
        MERCURY_REMOTE="$(git -C "$MERCURY_ROOT" remote get-url origin 2>/dev/null || echo sibling-checkout)"
        return
    fi

    for command in curl tar make pkg-config sha256sum; do
        if ! command -v "$command" >/dev/null 2>&1; then
            echo "ERROR: '$command' is required to build the bundled Mercury runtime." >&2
            echo "Fedora: sudo dnf install gcc make pkgconf-pkg-config curl tar gzip" >&2
            echo "Ubuntu: sudo apt install build-essential pkg-config curl tar gzip" >&2
            exit 1
        fi
    done
    if ! pkg-config --exists alsa libpulse hamlib; then
        echo "ERROR: Mercury development libraries are missing." >&2
        echo "Fedora: sudo dnf install gcc make pkgconf-pkg-config alsa-lib-devel pulseaudio-libs-devel hamlib-devel curl tar gzip" >&2
        echo "Ubuntu: sudo apt install build-essential pkg-config libasound2-dev libpulse-dev libhamlib-dev curl" >&2
        exit 1
    fi

    local hamlib_probe="$MERCURY_CACHE/hamlib-rigerror2-probe"
    mkdir -p "$MERCURY_CACHE"
    if printf '%s\n' '#include <hamlib/rig.h>' \
            'int main(void) { return rigerror2(RIG_OK) == 0; }' \
        | "${CC:-cc}" -Werror=implicit-function-declaration -x c - \
            $(pkg-config --cflags --libs hamlib) -o "$hamlib_probe" \
            >/dev/null 2>&1; then
        echo "Hamlib $(pkg-config --modversion hamlib) provides rigerror2."
    else
        MERCURY_HAMLIB_CFLAGS="$(pkg-config --cflags hamlib) -DHAVE_HAMLIB -Drigerror2=rigerror"
        echo "Hamlib $(pkg-config --modversion hamlib) uses the rigerror compatibility path."
    fi

    local archive="$MERCURY_CACHE/mercury-$MERCURY_COMMIT.tar.gz"
    MERCURY_ROOT="$MERCURY_CACHE/mercury-$MERCURY_COMMIT"
    MERCURY_SOURCE="$MERCURY_ROOT/mercury"
    MERCURY_REVISION="$MERCURY_COMMIT"
    MERCURY_REMOTE="https://github.com/N4EAC/mercury"
    mkdir -p "$MERCURY_CACHE"
    if [[ ! -f "$archive" ]]; then
        echo "Downloading pinned Mercury source $MERCURY_COMMIT..."
        curl -L --fail --show-error "$MERCURY_ARCHIVE_URL" -o "$archive"
    fi
    if [[ "$(sha256sum "$archive" | cut -d ' ' -f 1)" != "$MERCURY_ARCHIVE_SHA256" ]]; then
        echo "ERROR: Mercury source archive SHA-256 verification failed." >&2
        echo "Delete $archive and retry." >&2
        exit 1
    fi
    if [[ ! -f "$MERCURY_ROOT/Makefile" ]]; then
        tar -xzf "$archive" -C "$MERCURY_CACHE"
    fi
    echo "Building or validating pinned Mercury runtime locally..."
    make -C "$MERCURY_ROOT" clean
    if [[ -n "$MERCURY_HAMLIB_CFLAGS" ]]; then
        make -C "$MERCURY_ROOT" GIT_HASH="${MERCURY_COMMIT:0:8}" \
            HAMLIB_CFLAGS="$MERCURY_HAMLIB_CFLAGS" \
            -j"$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 2)"
    else
        make -C "$MERCURY_ROOT" GIT_HASH="${MERCURY_COMMIT:0:8}" \
            -j"$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 2)"
    fi
}

prepare_mercury
if [[ ! -f "$MERCURY_ROOT/LICENSE" || ! -f "$MERCURY_ROOT/LICENSE-freedv" ]]; then
    echo "ERROR: Mercury LICENSE and LICENSE-freedv must accompany the runtime." >&2
    exit 1
fi
if ! grep -a -q "radio_frequency_hz" "$MERCURY_SOURCE"; then
    echo "ERROR: Mercury does not contain MSP's read-only CAT frequency telemetry." >&2
    echo "Use the pinned automatic build or a compatible MERCURY_EXECUTABLE." >&2
    exit 1
fi
if ! grep -a -q "arq_tx_mode" "$MERCURY_SOURCE" || ! grep -a -q "arq_rx_mode" "$MERCURY_SOURCE"; then
    echo "ERROR: Mercury does not contain MSP's read-only ARQ payload-mode telemetry." >&2
    echo "Use the pinned automatic build or a compatible MERCURY_EXECUTABLE." >&2
    exit 1
fi
if ldd "$MERCURY_SOURCE" | grep -q "not found"; then
    echo "ERROR: The Mercury runtime has unresolved shared-library dependencies:" >&2
    ldd "$MERCURY_SOURCE" >&2
    exit 1
fi
"$MERCURY_SOURCE" -h >/dev/null

rm -rf "$ESPEAK_RUNTIME"
mkdir -p "$ESPEAK_RUNTIME"
install -m 0644 LICENSE "$ESPEAK_RUNTIME/LICENSE"
printf 'eSpeak NG %s offline speech runtime\nSource: Linux distribution package\nLicense: GNU GPL-3.0-or-later; see LICENSE.\n' \
    "$ESPEAK_VERSION" > "$ESPEAK_RUNTIME/SOURCE.txt"

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
    --add-data "$PROJECT_ROOT/THIRD_PARTY_NOTICES.md:." \
    --add-binary "$ESPEAK_BIN:espeak" \
    --add-data "$ESPEAK_DATA_DIR:espeak/espeak-ng-data" \
    --add-data "$ESPEAK_RUNTIME/LICENSE:espeak" \
    --add-data "$ESPEAK_RUNTIME/SOURCE.txt:espeak" \
    --distpath "$PROJECT_ROOT/dist" \
    --workpath "$PROJECT_ROOT/build/pyinstaller-linux" \
    --specpath "$PROJECT_ROOT/build/pyinstaller-linux" \
    "$PROJECT_ROOT/apps/desktop/main.py"

mkdir -p dist/MercurySkyPulse/mercury
install -m 0755 "$MERCURY_SOURCE" dist/MercurySkyPulse/mercury/mercury
install -m 0644 "$MERCURY_ROOT/LICENSE" dist/MercurySkyPulse/mercury/LICENSE
install -m 0644 "$MERCURY_ROOT/LICENSE-freedv" dist/MercurySkyPulse/mercury/LICENSE-freedv
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
    ln -s ../../opt/mercuryskypulse/MercurySkyPulse "$STAGE/usr/bin/mercury-skypulse"
    sed "s/@VERSION@/$VERSION/g" packaging/linux/debian-control.in > "$STAGE/DEBIAN/control"
    install -m 0644 packaging/linux/mercuryskypulse.desktop "$STAGE/usr/share/applications/"
    install -m 0644 assets/icons/linux/mercuryskypulse-256.png "$STAGE/usr/share/icons/hicolor/256x256/apps/mercuryskypulse.png"
    dpkg-deb --build --root-owner-group "$STAGE" "dist/packages/mercury-skypulse_${VERSION}_amd64.deb"
    dpkg-deb --info "dist/packages/mercury-skypulse_${VERSION}_amd64.deb" >/dev/null
    DEB_CONTENTS="$(dpkg-deb --contents "dist/packages/mercury-skypulse_${VERSION}_amd64.deb")"
    grep -q 'plugins/multimedia/.*mediaplugin' <<<"$DEB_CONTENTS"
    echo "Package complete: dist/packages/mercury-skypulse_${VERSION}_amd64.deb"
else
    RPM_TOP="$PROJECT_ROOT/build/package-linux/rpm"
    SOURCE_DIR="$RPM_TOP/source/mercury-skypulse-$VERSION"
    rm -f dist/packages/mercury-skypulse-*.rpm
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
    RPM_PACKAGE="$(find dist/packages -maxdepth 1 -name "mercury-skypulse-${RPM_VERSION}-1.*.x86_64.rpm" -print -quit)"
    if [[ -z "$RPM_PACKAGE" ]]; then
        echo "ERROR: rpmbuild did not produce the expected Fedora package." >&2
        exit 1
    fi
    rpm -qpi "$RPM_PACKAGE" >/dev/null
    RPM_CONTENTS="$(rpm -qpl "$RPM_PACKAGE")"
    grep -q 'plugins/multimedia/.*mediaplugin' <<<"$RPM_CONTENTS"
    RPM_REQUIREMENTS="$(rpm -qpR "$RPM_PACKAGE")"
    if grep -q '^libtiff[.]so[.]5' <<<"$RPM_REQUIREMENTS"; then
        echo "ERROR: RPM retained an unavailable optional libtiff.so.5 dependency." >&2
        exit 1
    fi
    if grep -E -q '^lib.*-[[:xdigit:]]{8}[.]so[.]' <<<"$RPM_REQUIREMENTS"; then
        echo "ERROR: RPM retained a private hash-named wheel-library dependency:" >&2
        grep -E '^lib.*-[[:xdigit:]]{8}[.]so[.]' <<<"$RPM_REQUIREMENTS" >&2
        exit 1
    fi
    echo "Package complete: dist/packages/mercury-skypulse-${RPM_VERSION}-1.*.x86_64.rpm"
fi

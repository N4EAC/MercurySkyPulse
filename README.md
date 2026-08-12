# MercurySkyPulse

[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-blue.svg)](LICENSE)
![Windows 10/11](https://img.shields.io/badge/Windows-10%20%7C%2011-0078D4.svg)
![macOS Apple Silicon](https://img.shields.io/badge/macOS-Apple%20Silicon-000000.svg)
![Linux planned](https://img.shields.io/badge/Linux-Fedora%20%7C%20Ubuntu%20planned-FCC624.svg)
![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB.svg)

MercurySkyPulse is a cross-platform, local-first station application built around
the independent [Mercury](https://github.com/Rhizomatica/mercury) HF modem
transport engine.

Mercury runs as its own process-isolated transport engine; MercurySkyPulse
communicates with it through documented interfaces. A small public
[MSP compatibility fork](https://github.com/N4EAC/mercury) adds conservative,
read-only Hamlib frequency telemetry while preserving this boundary:

- VARA-style ARQ TNC control TCP port (default `8300`);
- ARQ data TCP port (default `8301`);
- KISS broadcast TCP port (default `8100`) for capability beacons; and
- WebSocket status/spectrum endpoint and documented bounded controls (default
  `/websocket` on port `10000`).

## Status

The repository contains a feature-complete vertical-slice prototype with a
PySide6 desktop application and optional supervised Mercury child process. It
includes dockable operator UI, modem telemetry, ARQ chat and file transfer,
location and GPS workflows, capability beacons, station ping, a persistent BBS,
a loopback-only read-only web interface, optional PSK Reporter reception uploads,
offline signed licensing, and a trusted built-in plugin kernel. It is suitable for continued development and controlled
manual testing, but is not yet a production release.

The Navigator dock routes Overview and Signal to their dashboard sections and
opens Activity for diagnostics.

Mercury remains a process-isolated engine accessed through its documented UI
WebSocket and TNC TCP interfaces. Windows test packages include a pinned
MSP-compatible Mercury fork runtime so operators do not install or copy it
separately.

### Platform support

| Platform | Current status |
|---|---|
| Windows 10/11 x86-64 | Supported for engineering builds and live-radio testing through `build.exe.bat` |
| macOS Apple Silicon | Supported for engineering builds and live-radio testing through `build.app.sh` |
| Fedora Linux | Binary packaging planned after current RF validation |
| Ubuntu Linux | Binary packaging planned after current RF validation |

Linux remains a source-level architectural target, but no Linux binary package is
currently published. Intel macOS is not part of the presently validated build
matrix.

### Station chat

The Chat tab provides text-only station-to-station conversations. On the receiving
station, enter a callsign and choose **Listen**. On the initiating station, enter
both callsigns and choose **Connect**. Messages include timestamps and queued,
sent, delivered, or failed status. Delivered means the peer application returned
an acknowledgement; it is not a read receipt.

Conversation history is stored locally in the platform application-data directory.
The same connected station can receive files through **Send File…**. Transfers
may be paused or resumed. Every new incoming file requires operator acceptance.
Received content is stored under the
platform Downloads directory in `MercurySkyPulse`, after SHA-256 verification.
Previously received identical content is detected by checksum and not written a
second time. **Open Folder** reveals completed content. Outgoing progress remains
indeterminate while bytes are queued through Mercury and reaches 100% only after
the peer reports a verified checksum result. The initial file-size limit is 100 MiB.

Supported images are prepared automatically before transfer: orientation is
corrected, the longest edge is resized to at most 1920 pixels, opaque images are
optimized as JPEG, transparency is preserved with compressed PNG, and a compact
thumbnail is shown in the transfer UI. Source images are never modified.

### Position and GPS

The Setup window's GPS tab accepts manual decimal latitude/longitude or APRS-compatible
`DDMM.mmN/DDDMM.mmE` coordinates. It can use the operating system location source
or a serial NMEA GPS receiver at 4800 baud. Available serial/COM ports are listed
in an editable selector, so an unlisted port can still be entered manually.
Missing, non-finite, or negative receiver accuracy is treated as unknown without
discarding an otherwise valid coordinate fix. Manual position is retained locally;
GPS fixes are not stored as history.

After the operator starts GPS, MSP remembers that choice and automatically starts
the saved serial or system location source on later launches. If that source is
not present, GPS remains unavailable and reports the condition without selecting
or opening an unrelated COM port. Choosing **Stop GPS** disables automatic start.

**Share Location** sends the current validated position to the connected station.
Location is never transmitted automatically. Received locations are range-checked
and their APRS and decimal representations must agree before display. This is
coordinate compatibility only; MercurySkyPulse does not transmit APRS packets or
connect to APRS-IS.

GPS track retention is disabled by default. Enable **Retain GPS location updates**
to store subsequent fixes with timestamps and optional accuracy. The GPS setup tab
shows the retained point count and exports the track as GPX, Google Earth KML,
GeoJSON, or latitude/longitude CSV. Disabling retention stops new points but keeps
existing history available for later export.

### Station beacon

The Beacon tab advertises the station callsign, Maidenhead grid, software version,
and supported capabilities over Mercury's connectionless KISS broadcast port.
Beaconing
is Off by default and supports 1, 5, 10, 15, 30, or 60-minute intervals plus a
manual **Send Now** action.

Precise GPS coordinates are optional and disabled independently. When enabled,
the latest valid GPS-source fix and its timestamp are included; manual positions
are not substituted. This is a compact Mercury broadcast application beacon, not
an APRS packet or APRS-IS announcement.

### Station ping

The Ping tab sends a bounded request to the station connected through Mercury ARQ
and reports round-trip time, local SNR, remote SNR, remote bitrate, and remote
modem mode. RTT is measured locally with a monotonic clock and includes the radio
and application path. Pings time out after 15 seconds and only one may be active.

Mercury's current telemetry does not expose its exact FreeDV modulation name, so
the mode is reported as `ARQ` or `idle` unless Mercury supplies a future `mode` or
`modem_mode` status field.

### Station setup and radio

Edit → **Setup…** opens a separate window with **Radio**, **Audio**, **User**,
**GPS**, and **Reporting** tabs. The main window remains focused on operating views. Radio configures
CAT and PTT without making MercurySkyPulse a second
radio controller. For a managed local engine, it asks the selected Mercury
executable for its complete compiled Hamlib catalog with `mercury -K`; the list is
scrollable and searchable by manufacturer or model. Select a model, a discovered
COM/USB serial port (or manually enter a device/`ip:port`), and serial speed.
Mercury's WebSocket-reported capture and playback devices populate editable audio
selectors. When Mercury omits either list, locally discovered operating-system
audio names provide a fallback that Mercury resolves to its native device ID.
Choose **Save Station I/O and Restart Mercury** to persist the CAT and
audio device IDs in the application-owned Mercury configuration and restart the
managed modem once. Mercury remains the only process that opens audio, Hamlib,
and PTT. External Mercury profiles must be configured at their host.

While **Setup → Audio** is visible, MSP displays read-only live audio-path
diagnostics without keying the radio: selected friendly names and complete
Mercury-native endpoint IDs, inferred RX capture energy from Mercury's public
spectrum, decoded SNR, and spectrum sample rate/bin count. After five seconds it
distinguishes missing telemetry from telemetry with no energy above -100 dBFS and
suggests Windows Virtual Cable capture checks. Mercury does not currently publish
PCM channel peaks, playback level, Windows host API, or negotiated capture format;
MSP labels those limits rather than inventing values. ADR 0021 records this policy.

**TX Level Test** sends the station's normal real-call beacon every three seconds
for at most 12 seconds while allowing live modem TX-gain adjustment from -20
through 0 dB. Mercury's reported TX peak is displayed. The operator must
acknowledge that the test transmits RF, and an active ARQ link blocks or stops it.

Audio prefers capture/playback IDs reported by Mercury and falls back to editable
local device names when a Mercury list is unavailable. User stores the station
callsign and Maidenhead grid used by beaconing. GPS contains manual, system/serial
GPS, history/export, and sharing controls. Saving a valid manual position or
receiving a valid GPS position also
recalculates the proposed User-tab GRID, replacing stale placeholder text. Blank
manual coordinates produce a direct prompt to enter latitude and longitude. GRID
calculation is local and does not use an internet geolocation provider.

While Setup → Audio is visible, bounded spectrum telemetry supplies the labelled
inferred capture-energy diagnostic. MSP has no general signal-plot display.

### Reception reporting

Setup → **Reporting** provides optional, disabled-by-default PSK Reporter uploads.
When enabled, successfully decoded MSP beacons are reported with the station
callsign/GRID, antenna description, decoded station identity, Mercury's current
read-only CAT frequency, and ADIF mode `OFDM`. Mercury polls its existing Hamlib
session conservatively and suppresses polling during ARQ and transmit activity;
MSP does not open another CAT connection. Stale or unavailable frequency data
prevents a report. No message, BBS, file, credential, or precise GPS content is
uploaded.

The Reporting page includes a bounded, read-only activity log showing queued
receptions, receiver and sender fields, frequency, mode, timestamps, IPFIX packet
metadata, resolved destination, byte counts, and upload outcomes.

The main window also provides a movable, resizable **Radio Frequency** dock. It
displays Mercury's cached Hamlib reading and its age. It is deliberately read-only;
frequency and mode remain under direct operator control at the radio.

### BBS mailbox

For field-by-field setup, roles, connection steps, and security limitations, see
the [BBS usage guide](docs/BBS_GUIDE.md).

The BBS tab provides persistent Inbox, Outbox, Bulletins, and Files folders.
Operators can send addressed private messages, post public bulletins, upload files
to an application-owned catalog, and request remote catalog files for verified
download. Uploads are capped at 100 MiB and retain their exact SHA-256 identity.

The Access tab can optionally protect a station BBS with a shared password.
Protection starts disabled. The station commander enables it with a callsign and
10–256 character password, then assigns `user`, `operator`, or `commander` roles
to callsigns. Users may exchange private mail and request files; operators may
also publish bulletins and files. Connect to a protected BBS first, then use
**Authenticate to Connected BBS** before a protected operation. Passwords are
never sent or stored as plaintext. BBS traffic itself is not encrypted.

When BBS protection is enabled, the nonce/HMAC proof authenticates access for the
current ARQ session, and protected sender and file-owner fields must match the
authenticated callsign. In open mode those identity fields remain untrusted.
Non-BBS application protocols are not authenticated, and BBS authentication does
not provide encryption or traffic confidentiality. “Private” means addressed
mailbox content, not encrypted content.

The SQLite application database contains stations, contacts, conversations,
messages, settings, diagnostic logs, location history, BBS folders/messages/files,
and BBS security and role records. Foreign-key enforcement and write-ahead logging
are enabled, and the schema upgrades existing chat-history databases in place.

## Design principles

- Mercury remains independently buildable, runnable, upgradeable, and testable.
- MercurySkyPulse depends on documented wire contracts, not Mercury globals or private source internals.
- Transport-specific code remains behind adapter interfaces.
- Mercury TNC and KISS adapters carry opaque application bytes; message framing, chunking, authentication, and feature protocols live above them in `application_protocol`.
- Chat, files, BBS, mapping, web, logging, licensing, and encryption policy are MercurySkyPulse features, never Mercury modem responsibilities.
- Domain and application layers do not depend on TCP, WebSocket, UI, or operating-system details.
- A managed local Mercury process and a remote Mercury service should look equivalent to the application layer.
- New behavior is introduced with tests and documentation before crossing module boundaries.

## Repository layout

```text
MercurySkyPulse/
├── .github/workflows/           # Cross-platform automated tests
├── assets/icons/                # ICNS, ICO, and multi-resolution PNG artwork
├── apps/
│   └── desktop/                 # Alternate installed-package launcher
├── src/
│   ├── application/             # Collaboration use cases and neutral models
│   ├── application_protocol/    # MSP1/beacon codecs and event routing
│   ├── persistence/             # SQLite schema and repository
│   ├── platform_runtime/        # Process, file, GPS, web, and license adapters
│   ├── presentation/            # PySide6 UI and current composition root
│   ├── transport/
│   │   └── mercury/             # Opaque TNC/KISS and telemetry adapters
│   ├── domain/                  # Reserved placeholder
│   └── platform/                # Reserved placeholder
├── tests/
│   ├── unit/                    # Services, persistence, UI, and boundaries
│   ├── contract/                # Mercury wire-contract tests
│   └── integration/             # Reserved for real-Mercury tests
├── docs/
│   ├── ARCHITECTURE.md
│   ├── BBS_GUIDE.md
│   ├── LICENSE_FORMAT.md
│   ├── PLUGIN_SYSTEM.md
│   └── decisions/               # Architecture decision records
├── tools/run_tests.py           # Canonical test runner
├── AGENTS.md
├── CONTRIBUTING.md
├── PROJECT_STATUS.md
└── ROADMAP.md
```

`src/domain/`, `src/platform/`, several transport subdirectories, and
`tests/integration/` remain placeholders until approved migrations or real
integration tests populate them. The accepted architecture decisions are indexed
in [`docs/decisions/README.md`](docs/decisions/README.md).

## Mercury dependency

Mercury is a bundled runtime dependency for Windows engineering packages, not a
source dependency or in-process library. Source development may still launch a
separate checkout or address another host. `application.endpoints` defines typed managed-local,
unmanaged-local, and remote profiles for independent control, data, KISS, and
WebSocket endpoints, executable selection, reconnect policy, and receive limits.
The current desktop uses the backward-compatible managed-loopback default; a
preferences UI and persisted profile loader are not yet implemented. Remote
profiles require explicit acceptance that Mercury TNC/KISS traffic is not
authenticated or encrypted.

The architecture and intended dependency rules are described in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md). Planned implementation stages are in [`ROADMAP.md`](ROADMAP.md).

## Run the desktop application

Python 3.11 or newer is required.

```bash
python3 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
python -m pip install -e .
mercury-skypulse
```

Alternatively, after installation, run `python -m presentation`.

An interpreter launch can still display **Python** in the macOS menu bar because
macOS identifies the Python host bundle. Build and launch the named application
bundle for the correct **MercurySkyPulse** menu:

```bash
./build.app.sh
open dist/MercurySkyPulse.app
```

The script creates an isolated build environment, runs the aggregate tests, and
produces an unsigned engineering `.app` with MercurySkyPulse bundle metadata.
The bundle uses the project MSP radar icon rather than the Python host icon.
It also copies the runnable Mercury binary and license from the sibling Mercury
checkout into the app automatically. Set `MERCURY_EXECUTABLE` only when building
from a different local Mercury location; operators do not copy it after building.
Generated `build/`, `dist/`, and `.venv-build-macos/` content is ignored by Git.

### Application icon

The shared MSP radar artwork lives at `assets/icons/mercuryskypulse.png`.
Platform packaging uses `mercuryskypulse.icns` on macOS,
`mercuryskypulse.ico` on Windows, and the size-specific PNG files under
`assets/icons/linux/` on Linux. Qt also loads the packaged PNG at runtime so
development launches and application windows do not fall back to the Python icon.

To regenerate derived formats after intentionally replacing the master PNG,
install Pillow in a tooling environment and run:

```bash
python tools/generate_icons.py
```

### Windows test executable

On a Windows 10 or 11 development machine with Python 3.11 or newer installed,
run the repository-root builder from Command Prompt:

```bat
build.exe.bat
```

The script creates/reuses `.venv`, installs the project and PyInstaller, runs the
aggregate test suite, and creates a windowed one-directory test build at
`dist\MercurySkyPulse\MercurySkyPulse.exe`. Copy the entire
`dist\MercurySkyPulse` directory when testing on another computer. This is an
unsigned engineering build, not an installer or release artifact. It downloads
and includes the pinned MSP-compatible Mercury runtime automatically. The Windows
executable and taskbar use the same MSP radar artwork as macOS and Linux.

The builder downloads the Mercury 1.9.11 MSP compatibility build from the
public `N4EAC/mercury` fork, verifies its pinned archive SHA-256 digest, and
copies the complete portable runtime into the build. The exact corresponding
source commit is recorded in the package:

```text
dist\MercurySkyPulse\
├── MercurySkyPulse.exe
├── mercury\
│   ├── mercury.exe
│   ├── libhamlib-4.dll
│   ├── LICENSE
│   └── SOURCE.txt
└── _internal\
```

The first build requires internet access; later builds reuse a checksum-verified
cache under the Windows temporary directory. Download, integrity, extraction, or
copy failures stop the build rather than producing an incomplete package. The
runtime includes its GPL license and exact corresponding-source commit URL. Generated
Mercury files and the `dist` directory must not be committed to this repository.

The builder accepts Python 3.11 or newer through either the Windows `py` launcher
or `python` on `PATH`. If a build fails, it reports the failed stage and pauses so
the error remains visible when the batch file was opened by double-clicking. Run
it from an existing Command Prompt for the clearest diagnostic output.

### Mercury executable

MercurySkyPulse automatically starts Mercury with UI communication enabled. It looks for an executable in this order:

1. the explicitly configured executable, when endpoint-profile persistence is implemented;
2. `MERCURY_EXECUTABLE`;
3. the bundled `mercury/mercury` runtime inside a macOS app or
   `mercury\mercury.exe` beside a packaged Windows executable, followed by the
   legacy directly adjacent executable location;
4. the sibling `/Users/eduardo/development/mercury/mercury`-style checkout location; or
5. `mercury` on `PATH`.

To select an explicit build:

```bash
MERCURY_EXECUTABLE=/path/to/mercury .venv/bin/mercury-skypulse
```

Unexpected Mercury exits are detected and restarted automatically with bounded backoff. Use **Mercury → Restart Mercury** for a manual restart. Child-process output and restart events appear in the Activity panel.

The command toolbar plus Navigator and Activity docks can be moved, floated, and
resized. Workflow tabs can be reordered. Main-window geometry, dock/toolbar
placement and sizes, workflow-tab order, setup-window geometry, appearance/theme,
UI scale, and the selected GPS port are restored for the current OS user. Use
**Window → Reset Panel Layout** to restore the default dock arrangement.

### Field-test diagnostic log

MercurySkyPulse writes a persistent UTF-8 diagnostic log in the per-user
application-data directory under `logs/mercuryskypulse.log`. It records session
and platform details, Mercury output, TNC control events, ARQ and telemetry state
changes, errors, and file-transfer byte/status transitions. It intentionally
excludes chat/BBS message bodies, file contents, passwords, authentication proofs,
and tokens; suspected secret fields are redacted before writing.

Use **Mercury → Open Diagnostic Log Folder** to locate it. Logs rotate at 10 MiB
with ten retained backups. For radio-to-radio fault reports, collect logs from
both stations; timestamps are UTC so the two sides can be correlated.

Mercury itself owns audio and radio configuration. MercurySkyPulse consumes its telemetry and uses its documented ARQ TNC interface for text chat.

### Local web interface

While the desktop application is running, a read-only interface is available at
[`http://127.0.0.1:8765/`](http://127.0.0.1:8765/). It shows the dashboard,
station messages, current file transfers, station/modem status, and the latest
500 activity log lines. Use **Mercury → Open Local Web Interface** to open it.

The server binds only to IPv4 loopback and rejects every non-loopback client.
Only GET and HEAD are supported; POST, PUT, PATCH, and DELETE return HTTP 405.
No application files or directories are served. Set `MERCURYSKYPULSE_WEB_PORT`
before launch to select another local port; `0` chooses an available port.

### Offline licensing

MercurySkyPulse starts in Community edition when no license is installed. The
framework accepts offline Ed25519-signed JSON files with editions, feature flags,
expiration, and individual or organizational deployment metadata. Status appears
in the status bar, **Help → License Information**, and local dashboard. Existing
workflows are not gated during this framework phase.

Discovery checks `MERCURYSKYPULSE_LICENSE_FILE` and
`MERCURYSKYPULSE_LICENSE_KEYS`, then machine-wide files under
`/Library/Application Support/MercurySkyPulse`,
`%PROGRAMDATA%\MercurySkyPulse`, or `/etc/mercury-skypulse`, and finally the
per-user data directory. The key registry is
`{"schema":1,"keys":{"key-id":"BASE64_RAW_ED25519_PUBLIC_KEY"}}`.
Protect deployment files with OS permissions. No activation, telemetry, copy
protection, or hardware binding is performed.

The complete envelope and canonical signature procedure are documented in
[`docs/LICENSE_FORMAT.md`](docs/LICENSE_FORMAT.md). Private signing keys are never
part of the application or deployment package.

### Plugin system

Mercury transport, GUI themes, GPS, mapping export, BBS, the local web interface,
and logging are registered as trusted built-in plugins. The kernel provides API
compatibility, dependencies, explicit permissions, license requirements,
deterministic lifecycle, provider priority, and failure isolation. Status appears
under **Help → Plugin Information** and `/api/plugins` locally.

An encryption-provider extension point exists but has no provider. Third-party
discovery is intentionally disabled because in-process Python permissions are not
a sandbox. External plugins require the future out-of-process broker described in
[`docs/PLUGIN_SYSTEM.md`](docs/PLUGIN_SYSTEM.md) and ADR 0014.

Run the current dependency-boundary tests with:

```bash
python -m unittest discover -s tests -p 'test_*.py'
```

The test suite also constructs the complete Qt window using the offscreen platform, so it can run in headless CI. To force headless mode explicitly:

```bash
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -p 'test_*.py'
```

The canonical automated runner groups the main verification boundaries:

```bash
python tools/run_tests.py modem
python tools/run_tests.py protocol
python tools/run_tests.py transfer
python tools/run_tests.py gui
python tools/run_tests.py all
```

The modem suite tests telemetry parsing, executable discovery, crash detection,
and bounded restart behavior without radio hardware. Protocol tests cover framed
ARQ messages, BBS authentication events, location/ping events, and KISS beacons.
Transfer tests cover progress, pause/resume, checksums, duplicates, backpressure,
and unsafe input. GUI smoke tests construct all primary pages and dock panels with
Qt's offscreen platform. GitHub-hosted workflows are intentionally disabled; the
Apple Silicon Mac quality gate is authoritative:

```bash
scripts/check_local.sh
```

That script validates dependencies, compiles sources, runs the aggregate suite,
builds the macOS app, and verifies its identity, signature, icon, licenses, and
bundled Mercury runtime. Launching the managed-local package remains a manual,
RF-safe operator check because saved CAT/PTT settings may address real hardware.

Before release, the project still needs a persisted endpoint-profile UI,
real-Mercury integration tests, further plugin migration, packaging, and
platform/legal decisions described in the roadmap.

See [`CONTRIBUTING.md`](CONTRIBUTING.md) and [`AGENTS.md`](AGENTS.md) before making changes.

## License

MercurySkyPulse is free software licensed under the
[GNU General Public License, version 3 or later](LICENSE). You may use, study,
copy, modify, redistribute, and sell it under those terms. A distributor must
preserve the license and provide the corresponding source and the same freedoms
to recipients.

Copyright © 2026 Eduardo A. de Carvalho and MercurySkyPulse contributors.

Mercury is a separately maintained process and is distributed under its own
GPL-3.0-or-later terms. Packaged MSP builds retain Mercury's license and exact
corresponding-source information alongside its runtime.

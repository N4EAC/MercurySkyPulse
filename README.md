# MercurySkyPulse

MercurySkyPulse is a cross-platform, local-first station application built around
the independent [Mercury](https://github.com/Rhizomatica/mercury) HF modem
transport engine.

This repository intentionally does **not** vendor, fork, or modify Mercury. Mercury runs as its own transport engine; MercurySkyPulse communicates with it through Mercury's documented interfaces:

- VARA-style ARQ TNC control TCP port (default `8300`);
- ARQ data TCP port (default `8301`);
- KISS broadcast TCP port (default `8100`) for capability beacons; and
- read-only WebSocket status/spectrum endpoint (default `/websocket` on port
  `10000`) for UI telemetry.

## Status

The repository contains a feature-complete vertical-slice prototype with a
PySide6 desktop application and optional supervised Mercury child process. It
includes dockable operator UI, modem telemetry, ARQ chat and file transfer,
location and GPS workflows, capability beacons, station ping, a persistent BBS,
a loopback-only read-only web interface, offline signed licensing, and a trusted
built-in plugin kernel. It is suitable for continued development and controlled
manual testing, but is not yet a production release.

Mercury remains an independent executable and is accessed through its documented UI WebSocket and TNC TCP interfaces.

### Station chat

The Chat tab provides text-only station-to-station conversations. On the receiving
station, enter a callsign and choose **Listen**. On the initiating station, enter
both callsigns and choose **Connect**. Messages include timestamps and queued,
sent, delivered, or failed status. Delivered means the peer application returned
an acknowledgement; it is not a read receipt.

Conversation history is stored locally in the platform application-data directory.
The same connected station can receive files through **Send File…**. Transfers
show progress and may be paused or resumed. Received content is stored under the
platform Downloads directory in `MercurySkyPulse`, after SHA-256 verification.
Previously received identical content is detected by checksum and not written a
second time. The initial file-size limit is 100 MiB.

Supported images are prepared automatically before transfer: orientation is
corrected, the longest edge is resized to at most 1920 pixels, opaque images are
optimized as JPEG, transparency is preserved with compressed PNG, and a compact
thumbnail is shown in the transfer UI. Source images are never modified.

### Position and GPS

The Setup window's GPS tab accepts manual decimal latitude/longitude or APRS-compatible
`DDMM.mmN/DDDMM.mmE` coordinates. It can use the operating system location source
or a serial NMEA GPS receiver at 4800 baud. Manual position is retained locally;
GPS fixes are not stored as history.

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

### Station setup, radio, and tuning

Edit → **Setup…** opens a separate window with **Radio**, **Audio**, **User**, and
**GPS** tabs. The main window remains focused on operating views. Radio configures
CAT and PTT without making MercurySkyPulse a second
radio controller. For a managed local engine, it asks the selected Mercury
executable for its complete compiled Hamlib catalog with `mercury -K`; the list is
scrollable and searchable by manufacturer or model. Select a model, a discovered
COM/USB serial port (or manually enter a device/`ip:port`), and serial speed.
Mercury's WebSocket-reported capture and playback devices populate editable audio
selectors. Choose **Save Station I/O and Restart Mercury** to persist the CAT and
audio device IDs in the application-owned Mercury configuration and restart the
managed modem once. Mercury remains the only process that opens audio, Hamlib,
and PTT. External Mercury profiles must be configured at their host.

The Tune control sends Mercury's documented 1000 Hz `TUNE` carrier at the absolute
slider level from -60 through 0 dBFS. The last slider position is remembered.
MercurySkyPulse sends `TUNE OFF` after 12 seconds or when the operator stops,
disconnects, or closes the application; Mercury retains its independent 60-second
hard failsafe. Tuning is refused while an ARQ link is active. Always begin into a
dummy load at low drive and verify that PTT unkeys.

Audio uses capture/playback IDs reported by Mercury. User stores the station
callsign and Maidenhead grid used by beaconing. GPS contains manual, system/serial
GPS, history/export, and sharing controls. Saving a valid manual position or
receiving a valid GPS position also
recalculates the proposed User-tab GRID, replacing stale placeholder text. Blank
manual coordinates produce a direct prompt to enter latitude and longitude. GRID
calculation is local and does not use an internet geolocation provider.

The Overview page has independent **Spectrum** and **Waterfall** checkboxes. Both
are enabled by default and may be hidden separately.

### BBS mailbox

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

Mercury is an external runtime dependency, not a source dependency. During
development it may be launched from a separately checked-out Mercury repository
or addressed on another host. `application.endpoints` defines typed managed-local,
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

On macOS, interpreter-based development launches set both Qt metadata and the
native Cocoa process name so the system application menu displays
**MercurySkyPulse** rather than **Python**.

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
unsigned engineering build, not an installer or release artifact; Mercury remains
a separately supplied executable.

The builder accepts Python 3.11 or newer through either the Windows `py` launcher
or `python` on `PATH`. If a build fails, it reports the failed stage and pauses so
the error remains visible when the batch file was opened by double-clicking. Run
it from an existing Command Prompt for the clearest diagnostic output.

### Mercury executable

MercurySkyPulse automatically starts Mercury with UI communication enabled. It looks for an executable in this order:

1. `MERCURY_EXECUTABLE`;
2. the sibling `/Users/eduardo/development/mercury/mercury`-style checkout location; or
3. `mercury` on `PATH`.

To select an explicit build:

```bash
MERCURY_EXECUTABLE=/path/to/mercury .venv/bin/mercury-skypulse
```

Unexpected Mercury exits are detected and restarted automatically with bounded backoff. Use **Mercury → Restart Mercury** for a manual restart. Child-process output and restart events appear in the Activity panel.

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
Qt's offscreen platform. `.github/workflows/tests.yml` runs the aggregate suite on
Linux, macOS, and Windows using supported Python versions.

Before release, the project still needs a persisted endpoint-profile UI,
real-Mercury integration tests, further plugin migration, packaging, and
platform/legal decisions described in the roadmap.

See [`CONTRIBUTING.md`](CONTRIBUTING.md) and [`AGENTS.md`](AGENTS.md) before making changes.

## License

No project license has been selected yet. Mercury is GPL-3.0-or-later; contributors must evaluate distribution and integration obligations before choosing MercurySkyPulse's license and packaging model.

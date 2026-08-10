# MercurySkyPulse Project Status and Handoff

Last reviewed: 2026-08-09

This is the primary handoff for a new Codex session with no conversation history.
Read this file, then `AGENTS.md`, before changing code. The repository described
here is `/Users/eduardo/development/MercurySkyPulse`; the separate Mercury modem
checkout is not part of this project and must not be modified from this task.

## 1. Current purpose

MercurySkyPulse is a cross-platform, local-first station application built around
the independent Mercury HF modem. It provides the operator UI and collaboration
features while Mercury remains responsible for modem DSP, ARQ/KISS transport,
audio, CAT/PTT, and HF radio operation.

MercurySkyPulse communicates only through Mercury's documented process and wire
interfaces. It does not vendor, patch, link, or reach into Mercury internals.

The current product is a feature-complete vertical-slice prototype with enforced
architecture boundaries. It is suitable for continued development and controlled
manual testing, but it is not yet a production release.

### Repository state at handoff

- Pull requests #1–#8 are merged into `main` at `f2d14a8`. They contain the
  endpoint-profile and safety work, station setup, operational Navigator, the
  attempted macOS menu correction, GitHub Actions v7 updates, and the hardened
  Windows builder with bundled Mercury 1.9.11 runtime plus Windows GPS fixes.
- Current handoff branch: `agent/fix-windows-audio-theme`. It adds OS audio-device
  fallback, complete dark surface styling, and opt-in spectrum/waterfall defaults.
- Interpreter-based macOS launches can still display **Python** because macOS
  identifies the Python host bundle. `build.app.sh` now creates a named,
  unsigned `MercurySkyPulse.app` engineering bundle for correct menu identity.
- The worktree was clean when this handoff was committed. Always recheck
  `git status`, remote branches, and recent history before editing.

## 2. Mandatory architecture

The required dependency stack is:

```text
User Interface
    ↓
Messaging and Collaboration Services
    chat · file transfer · BBS · location/mapping · beacon · ping · web
    ↓
Application Protocol
    MSP1 framing · event routing · acknowledgements · chunking · BBS auth messages
    ↓
Mercury Transport Adapters
    opaque reliable bytes · opaque KISS payloads · typed modem telemetry
    ↓
Mercury Modem
    DSP · ARQ · broadcast transport
    ↓
Audio · CAT · PTT · HF radio
```

Rules that must not be weakened:

- Mercury must never own chat, files, BBS, mapping, web, logging, licensing,
  application authentication, compression, or encryption policy.
- `src/transport/mercury/tnc.py` and `beacon.py` carry opaque application bytes.
- `src/application_protocol/` owns MercurySkyPulse framing and feature-event
  demultiplexing.
- `src/application/` owns workflows, validation, access policy, and projections.
- `src/platform_runtime/` owns process, filesystem, GPS, image, HTTP, and license
  deployment adapters.
- `src/presentation/` owns PySide6 UI and the current composition root.
- `tests/unit/test_architecture_layers.py` statically enforces the most important
  dependency rules and must remain in the aggregate test suite.

Mercury transport is also registered as a trusted built-in plugin, but it exports
transport capabilities only. An alternative transport must implement the same
opaque-byte/modem-fact boundary rather than absorbing application features.

## 3. Implemented functionality

### Desktop UI

- PySide6 main window with operational Overview, Chat, Beacon, Ping, and BBS tabs.
- Separate Edit → Setup window prepared for additional configuration categories;
  its initial tabs are Radio, Audio, User, and GPS in that order.
- Movable, floatable, closable docks for navigation and activity. The Navigator
  routes Overview/Signal/Waterfall dashboard sections and opens Activity for
  diagnostics. The unused static Inspector was removed to preserve working space.
- Menu, toolbar, status bar, scalable fonts, high-DPI behavior, and system/light/
  dark themes with system/macOS/Windows style presets. Explicit palette and tab,
  input, header, pane, and viewport styling prevent native white gaps in dark mode.
- A shared green MSP radar icon is installed at runtime and packaged as native
  macOS ICNS, Windows ICO, and multi-resolution Linux PNG assets.
- Interpreter launchers set the process name before importing Qt and a Cocoa
  adapter attempts to label the native application-menu item. Manual testing still
  shows **Python**. A packaged `.app` with MercurySkyPulse bundle metadata is the
  recommended next resolution path; do not claim this issue is fixed yet.
- Live modem status cards, SNR, bitrate, spectrum, and rolling waterfall; spectrum
  and waterfall default off, can be enabled independently, and binary frames are
  not parsed while both views are disabled.
- Audio selectors prefer Mercury-native capture/playback IDs and use editable
  operating-system device names as a fallback when Mercury omits either list.
- GPS setup lists discovered serial/COM ports in an editable selector. Valid fixes
  remain usable when the receiver reports missing or invalid horizontal accuracy.
- Offscreen GUI construction tests for headless CI.

### Mercury process and telemetry

- Supervised process-isolated Mercury engine using `QProcess`; it is bundled as a
  required runtime component in Windows engineering packages.
- Executable discovery via `MERCURY_EXECUTABLE`, sibling checkout, or `PATH`.
- Frozen/package builds prefer `mercury/mercury.exe` inside the application folder
  and retain the legacy directly adjacent executable lookup.
- Launch arguments include `-G -U <UI port>` and, when radio setup is enabled,
  documented `-R <model> -A <device>` options plus `-C <application INI>` for CAT
  serial speed; default UI port is 10000.
- Unexpected-exit detection, bounded restart backoff, stable-run reset, manual
  restart/stop, merged output capture, and blocking shutdown.
- Read-only Mercury UI WebSocket client at
  `ws://127.0.0.1:10000/websocket` with reconnect backoff.
- Typed and bounded parsing for JSON modem status and binary spectrum frames.

### ARQ application protocol and chat

- Raw Mercury control port 8300 and reliable data port 8301 adapter.
- `MSP1` length-prefixed, bounded JSON application framing above Mercury.
- Maximum application frame payload: 8 KiB; maximum chat text: 2,048 characters.
- Callsign validation, listen/connect/disconnect commands, fragmented-stream
  decoding, resynchronization, message acknowledgement, and feature-event routing.
- Station-to-station chat with timestamps and queued/sent/delivered/received/
  failed states. Delivered is an application acknowledgement, not a read receipt.
- Persistent conversation history in SQLite.

### File and image transfer

- File offers, acceptance, 4 KiB chunks, progress, pause/resume, completion, and
  result events over the application protocol.
- SHA-256 verification, partial-file staging, duplicate detection, safe destination
  naming, path traversal protection, and one active outgoing transfer.
- File limit: 100 MiB.
- Automatic image orientation correction, maximum 1,920-pixel dimension, JPEG/PNG
  optimization, and 128-pixel thumbnail generation without modifying the source.

### Location, GPS, and mapping export

- Manual decimal coordinates and APRS-compatible uncompressed coordinates.
- System positioning or serial NMEA GPS receiver at 4,800 baud.
- Explicit location sharing; positions are never automatically shared.
- Optional GPS-history retention, disabled by default.
- GPX 1.1, KML 2.2, GeoJSON, and CSV export for mapping tools.
- Manual and remotely received positions are excluded from GPS history.
- Valid manual and GPS positions locally calculate the proposed User-tab grid;
  blank manual coordinates produce an operator-facing instruction rather than a
  raw numeric-conversion exception.

### Beacon and ping

- Compact `MSPB` capability beacon over Mercury's KISS broadcast port 8100.
- Manual beacon and selectable 1/5/10/15/30/60-minute intervals.
- Callsign, Maidenhead grid, software version, capabilities, and optional latest
  GPS-source fix.
- MSPB v1 advertises only its seven defined peer capabilities; local radio setup
  and tuning controls are deliberately not encoded as over-the-air capabilities.
- Ping request/response with monotonic RTT, local/remote SNR, remote bitrate, and
  modem mode; one in-flight ping and a 15-second timeout.

### Radio setup and tuning

- Searchable, scrollable catalog generated by the selected Mercury executable's
  documented `-K` Hamlib listing rather than a hardcoded radio list.
- Managed-local CAT/PTT selection using documented Mercury `-R/-A` options and an
  application-owned `-C` file for CAT serial speed; Mercury remains the sole
  Hamlib/PTT owner.
- Persistent model, device/address, serial speed, and absolute tune dBFS setting.
- Cross-platform COM/USB serial-port discovery with manual serial/network CAT
  fallback, plus Mercury-native capture/playback selectors populated from its
  documented WebSocket device lists. Radio and audio have separate explicit save
  actions; either causes one managed Mercury restart.
- Documented Mercury `TUNE`/`TUNE OFF` control with a -60..0 dBFS slider,
  active-link exclusion, explicit stop, 12-second application timeout, shutdown
  cleanup, disconnect warning, and Mercury's independent 60-second failsafe.

### BBS and access control

- Persistent Inbox, Outbox, Bulletins, and Files catalog.
- Private addressed mail, public bulletins, local upload, remote catalog request,
  and verified file serving through the file-transfer service.
- Optional shared BBS password; protection is off by default.
- Salted scrypt verifier at rest and 60-second nonce/HMAC-SHA-256 proof exchange;
  the plaintext password is neither stored nor transmitted.
- `user`, `operator`, and `commander` roles with centralized permission checks.
- Saving the station callsign initializes blank Chat and remote-BBS login
  callsign fields once without overwriting later operator edits.
- Protected sender/file-owner fields must match the authenticated callsign.
- Authentication state and challenges are cleared on disconnect.

### Persistence

- SQLite with foreign keys enabled, WAL mode, forward migration, and schema
  version 5.
- Tables: `stations`, `contacts`, `conversations`, `messages`, `settings`, `logs`,
  `location_history`, `bbs_folders`, `bbs_messages`, `bbs_files`, `bbs_security`,
  and `bbs_roles`.
- Application database filename: `chat-history.sqlite3` under Qt's platform
  application-data location.
- BBS-managed uploads live under the application-data `bbs-files` directory.
- Received transfers live under the platform Downloads directory in
  `MercurySkyPulse`.

### Local web interface

- Embedded standard-library HTTP server bound only to `127.0.0.1`, default port
  8765.
- Read-only dashboard, messages, transfers, station status, and bounded logs.
- JSON GET endpoints: `/api/dashboard`, `/api/messages`, `/api/transfers`,
  `/api/station`, `/api/logs`, and `/api/plugins`.
- GET/HEAD only; write methods return 405. No CORS permission or filesystem serving.
- Thread-safe bounded snapshots prevent the HTTP worker from touching Qt or SQLite.

### Offline licensing framework

- Offline Ed25519-signed JSON licenses using `cryptography`.
- Community, Standard, Professional, and Enterprise edition models.
- Feature flags, issue/not-before/expiration timestamps, organization, deployment
  ID, and seat metadata.
- Explicit, machine-wide, and per-user deployment paths for license/key registries.
- No activation, telemetry, copy protection, obfuscation, or hardware binding.
- License state is displayed, but current product workflows are not yet gated by
  feature flags.

### Plugin kernel

- Versioned API compatibility, immutable manifests, extension points, priorities,
  dependency ordering, reverse shutdown, explicit permissions, license-feature
  requirements, and failure containment.
- Trusted built-ins registered for Mercury transport, themes, GPS, mapping, BBS,
  web, and logging.
- Encryption-provider extension point exists with no provider.
- External discovery/dynamic import is intentionally disabled. In-process Python
  permissions are not a sandbox.

### Automated testing

- Standard-library `unittest` runner with `modem`, `protocol`, `transfer`, `gui`,
  and `all` groups.
- Current aggregate result at this review: 159 tests passing.
- GitHub-hosted workflows are intentionally disabled. `scripts/check_local.sh`
  is the authoritative Apple Silicon Mac compilation, test, dependency, and
  packaging quality gate.
- Tests require no display, real callsign traffic, Mercury process, radio, or RF.

## 4. Directory structure and important files

```text
MercurySkyPulse/
├── apps/desktop/main.py              Alternate installed-package launcher
├── assets/icons/                     Cross-platform MSP radar icon assets
├── build.exe.bat                     Windows 10/11 PyInstaller test builder
├── build.app.sh                      macOS PyInstaller application-bundle builder
├── docs/
│   ├── ARCHITECTURE.md               Full design specification
│   ├── LICENSE_FORMAT.md             Signed license envelope and canonical signing
│   ├── PLUGIN_SYSTEM.md              Plugin contract and migration rules
│   └── decisions/0001..0019          Accepted architecture decision records
├── src/
│   ├── application/                  Collaboration use cases and neutral models
│   ├── application_protocol/         MSP1/beacon codecs and protocol clients
│   ├── persistence/                  SQLite schema and repository
│   ├── platform_runtime/             OS/process/file/GPS/web/license adapters
│   ├── presentation/                 PySide6 pages, window, themes, composition
│   └── transport/mercury/            Opaque TNC/KISS and telemetry adapters
├── tests/
│   ├── contract/                     Application/Mercury wire contract tests
│   ├── unit/                         Services, persistence, security, UI, boundaries
│   └── integration/                  Placeholder; no real-Mercury tests yet
├── tools/run_tests.py                Canonical test runner
├── scripts/check_local.sh            Canonical Mac-local pre-commit quality gate
├── AGENTS.md                         Mandatory agent constraints
├── CONTRIBUTING.md                   Contributor and test-safety guidance
├── PROJECT_STATUS.md                 This handoff
├── README.md                         Current operator/developer overview
├── ROADMAP.md                        Current milestone and delivery sequence
└── pyproject.toml                    setuptools project and dependencies
```

Most important implementation files:

| File | Responsibility |
|---|---|
| `src/presentation/app.py` | Current dependency composition root and startup |
| `src/presentation/main_window.py` | Desktop lifecycle and signal wiring |
| `src/presentation/plugin_bootstrap.py` | Trusted built-in plugin registration |
| `src/application_protocol/messaging.py` | MSP1 frame/event contract |
| `src/application_protocol/client.py` | Application event routing over raw bytes |
| `src/application_protocol/beacon.py` | Beacon codec and protocol wrapper |
| `src/transport/mercury/tnc.py` | Raw control/reliable-byte TNC adapter |
| `src/transport/mercury/beacon.py` | Raw KISS broadcast adapter |
| `src/transport/mercury/telemetry/` | WebSocket lifecycle and telemetry parsers |
| `src/platform_runtime/mercury_process.py` | Mercury discovery/supervision/restart |
| `src/application/chat_service.py` | Conversations and text messaging |
| `src/application/file_transfer.py` | Transfer state machine and checksums |
| `src/application/bbs.py` | BBS workflows, password proof, roles, policy |
| `src/application/location.py` | Coordinates, GPS retention, sharing |
| `src/application/beacon.py` | Periodic beacon policy |
| `src/application/ping.py` | Ping correlation and RTT |
| `src/persistence/chat_repository.py` | SQLite schema v5 and persistence methods |
| `src/application/plugins.py` | Plugin kernel |
| `src/application/licensing.py` | License schema and entitlement evaluation |
| `src/application/endpoints.py` | Typed Mercury modes, endpoints, reconnect and safety policy |
| `src/application/radio.py` | Persisted radio selection and bounded tuning workflow |
| `src/platform_runtime/hamlib_catalog.py` | Mercury `-K` Hamlib catalog adapter |
| `src/platform_runtime/station_devices.py` | Cross-platform CAT/GPS COM and serial-port discovery |
| `src/platform_runtime/macos_application.py` | Native macOS process metadata and Cocoa application-menu labeling |
| `src/presentation/__init__.py` | Qt-free launcher bootstrap for native process metadata |
| `src/presentation/setup_window.py` | Radio/Audio/User/GPS configuration window |
| `src/platform_runtime/local_web.py` | Loopback-only read-only HTTP adapter |
| `tests/unit/test_architecture_layers.py` | Mercury/application dependency enforcement |

`src/domain/`, `src/platform/`, several transport subdirectories, and
`tests/integration/` remain placeholders. Do not delete placeholders casually;
either populate them as part of an approved migration or leave them intact.

## 5. How Mercury integration currently works

### Process lifecycle

`MainWindow` creates `MercuryProcessSupervisor(MercuryProcessConfig())`. Startup is
scheduled through Qt after the window is constructed. The supervisor finds an
executable, launches Mercury as a separate process, captures merged output, and
restarts unexpected exits with delays of 1/2/4/8/15/30 seconds. Restart attempts
reset after 30 seconds of stable runtime.

Discovery order is:

1. explicit `MercuryProcessConfig.executable` (not currently exposed in UI);
2. `MERCURY_EXECUTABLE`;
3. packaged macOS internal `mercury/mercury` or Windows
   `mercury/mercury.exe`, then a legacy directly adjacent executable;
4. sibling `../mercury/mercury` or `mercury.exe` checkout;
5. `mercury` on `PATH`.

Mercury remains authoritative for audio, CAT, PTT, modem DSP, ARQ, and RF safety.

When the persisted managed-local radio configuration is enabled, the supervisor
adds Mercury's documented `-R` model and `-A` device/address options. A minimal
application-owned INI supplies `radio_serial_speed`, `input_device`, and
`output_device`; it does not modify a Mercury checkout or a user-owned Mercury
configuration. Saving station I/O restarts the managed Mercury process once.
Unmanaged-local and remote Mercury instances must be configured on their host and
are deliberately rejected by this workflow.

### Telemetry path

`MercuryTelemetryClient` opens the default UI WebSocket. Text status messages are
converted into neutral `ModemStatus` values; binary frames become `SpectrumFrame`
values. `MainWindow` updates the dashboard, ping service, and web snapshot.
Spectrum is rendered live and retained only as a bounded waterfall in memory.

### Reliable ARQ path

`MercuryTncTransport` opens control/data sockets and knows only Mercury session
commands and opaque bytes. `ApplicationMessagingClient` sits above it, frames and
decodes MSP1 messages, sends peer acknowledgements, and routes application events
to chat, file, location, ping, and BBS services. Mercury never interprets these
feature event names.

### Broadcast path

`MercuryBroadcastTransport` handles the KISS socket and opaque payloads.
`BeaconProtocolClient` above it encodes/decodes the MSPB capability beacon.

### Current endpoint profiles

`MercuryEndpointProfile` models managed local, unmanaged local, and remote modes,
independent control/data/KISS/WebSocket endpoints, executable selection, bounded
reconnect policy, and receive limits. The composition root wires its selected
profile into process supervision and all clients. The current desktop selects the
backward-compatible managed-loopback default because no endpoint-profile UI or
persistent configuration loader exists yet. Remote profiles require explicit
acceptance of unauthenticated/unencrypted Mercury TNC and KISS transport risk.

### Radio catalog and tune path

`MercuryHamlibCatalog` asynchronously runs the selected local Mercury executable
with documented `-K` and parses a bounded output stream. The catalog is therefore
the full set compiled into that Mercury build, not a static project list. The
locally inspected Mercury 1.9.11 build returned 311 models; other builds may differ.

`RadioStationService` persists the selected model, device/address, serial speed,
and tune dBFS level in SQLite settings. It sends documented TNC `TUNE <dBFS>` and
`TUNE OFF` commands through `ApplicationMessagingClient`. Tuning is blocked while
an ARQ link is active or connecting, stops after 12 seconds without extending the
deadline when the slider moves, and attempts cleanup on stop/shutdown. If the
control socket is lost, `TUNE OFF` cannot be delivered; the UI warns the operator
and Mercury's independent 60-second transmit failsafe remains the final bound.

## 6. Build, run, and test

Python 3.11 or newer is required. The automated matrix currently targets 3.11 and
3.13. Dependencies are PySide6 6.8–6.x and cryptography 44–46.

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -e .
```

Launch:

```bash
mercury-skypulse
# or
python -m presentation
```

Select a Mercury executable when automatic discovery is unsuitable:

```bash
MERCURY_EXECUTABLE=/absolute/path/to/mercury mercury-skypulse
```

Select the local web port (`0` requests an ephemeral port):

```bash
MERCURYSKYPULSE_WEB_PORT=8765 mercury-skypulse
```

Optional license deployment variables:

```bash
MERCURYSKYPULSE_LICENSE_FILE=/path/site.license \
MERCURYSKYPULSE_LICENSE_KEYS=/path/license-public-keys.json \
mercury-skypulse
```

Canonical verification before handoff or commit:

```bash
scripts/check_local.sh
```

Last handoff verification on 2026-08-09 completed source compilation and the
aggregate suite successfully: 159 tests passed.

Focused suites:

```bash
python tools/run_tests.py modem
python tools/run_tests.py protocol
python tools/run_tests.py transfer
python tools/run_tests.py gui
```

Do not add tests that transmit RF or accidentally launch a developer's Mercury
binary for a mocked missing-engine case.

## 7. Important technical decisions

The ADR index is `docs/decisions/README.md`. Accepted decisions are:

| ADR | Decision |
|---|---|
| 0001 | Python 3.11+ and PySide6 desktop UI |
| 0002 | Mercury remains a supervised independent process |
| 0003 | Bounded text chat protocol over Mercury TNC bytes |
| 0004 | Verified resumable file-transfer state machine |
| 0005 | Non-destructive automatic image preparation |
| 0006 | Manual/GPS positions, APRS coordinate compatibility, explicit sharing |
| 0007 | Opt-in GPS history and interoperable mapping export |
| 0008 | Periodic compact connectionless capability beacon |
| 0009 | Correlated ARQ ping with monotonic RTT and telemetry snapshots |
| 0010 | Original unauthenticated local-first BBS boundary |
| 0011 | Optional shared-password BBS authentication and roles; supersedes 0010 when enabled |
| 0012 | Loopback-only read-only embedded web interface |
| 0013 | Offline signed licensing framework without hardware binding/copy protection |
| 0014 | Trusted built-in plugin kernel and incremental migration |
| 0015 | Automated test matrix and headless/cross-platform policy |
| 0016 | Mercury transports opaque bytes; application features remain above it |
| 0017 | Typed Mercury endpoint profiles and explicit remote safety boundary |
| 0018 | Mercury-owned Hamlib radio setup and bounded tuning |
| 0019 | Separate station setup window and local GRID derivation |
| 0020 | Pinned, checksum-verified Mercury runtime bundled in Windows test packages |

Additional standing decisions:

- SQLite is local-first persistence; database access stays off the HTTP worker.
- Third-party plugin loading is disabled until an authenticated out-of-process
  broker and package trust model exist.
- The encryption-provider extension point is intentionally empty.
- License entitlements are modeled but not enforced against current workflows.
- BBS password proofs authenticate access but do not encrypt radio traffic.
- The project does not yet have a selected legal/source-code license. Do not
  confuse that with the implemented product licensing subsystem.

## 8. Known bugs, risks, and incomplete work

### Documentation status

- README, roadmap, contributing guidance, and repository-layout descriptions were
  reconciled with the implemented vertical slice on 2026-08-08.
- The README now distinguishes optional protected-BBS session authentication from
  untrusted open-mode identity and unauthenticated non-BBS protocols.
- The roadmap records KISS beacon transport and the broader vertical slice as
  implemented, with architecture hardening and real integration as the current
  milestone.

### Runtime and protocol risks

- No real-Mercury integration tests exist. The current suite uses parsers, fake
  peers, mock process discovery, and GUI smoke tests.
- Radio setup and tune controls have no automated real-rig test; bench validation
  must begin with a dummy load, low dBFS drive, and independent PTT observation.
- The Hamlib catalog is available only when a local Mercury executable can be
  discovered. Its contents vary with the Hamlib backends compiled into that build.
- Audio selectors prefer lists published by Mercury WebSocket telemetry. Local
  operating-system capture/playback names fill missing lists, and editable fields
  preserve saved/manual IDs when a device is temporarily unavailable.
- Radio configuration is intentionally managed-local only. Unmanaged-local and
  remote Mercury CAT/PTT settings must be administered on the Mercury host.
- Tune cleanup is best-effort after a control-socket failure; the application
  cannot send `TUNE OFF` over a disconnected socket and relies on Mercury's
  independent 60-second failsafe. The 12-second path needs physical bench testing.
- Mercury compatibility is not negotiated against a known version/commit.
- Endpoint profiles are typed and wired, but there is no persistent loader or
  preferences UI; desktop startup therefore selects the managed-loopback default.
- TNC control lines and KISS frames/buffers are bounded with malformed-input
  counters and safe reset behavior. Further telemetry size/rate limits and
  structured metrics remain future hardening.
- Application acknowledgement write failures during disconnect races are caught
  and reported through the protocol client's error signal.
- File offers are automatically accepted; there is no operator consent/quarantine
  policy. Transfer resume is session-memory behavior, not restart-persistent.
- Application messages, files, locations, pings, and beacons are not encrypted or
  authenticated. Only protected BBS access has a proof exchange.
- The BBS uses one shared password. Anyone with it may claim a callsign that has a
  privileged role; per-station keys are not implemented.
- Image processing currently runs synchronously and may affect UI responsiveness
  for large images.
- Exact Mercury modulation mode is unavailable unless Mercury supplies `mode` or
  `modem_mode`; fallback is `ARQ`/`idle`.

### Persistence and observability gaps

- The `logs` table exists, but Activity/local-web logs are currently bounded
  in-memory text rather than persisted through the repository.
- No user-facing retention/deletion/export workflow exists for chat, BBS, or logs.
- No database backup/restore, corruption recovery, migration rollback, or schema
  compatibility testing across packaged releases exists.
- Transfer state is not persisted.

### Plugin/licensing gaps

- Built-in plugins are object-registration adapters; most objects are still
  constructed directly in `presentation/app.py`, and lifecycle remains primarily
  owned by `MainWindow`.
- No third-party package discovery, signature verification, broker IPC, sandbox,
  permission consent UI, scoped plugin storage, or constrained plugin UI exists.
- No encryption provider exists.
- Licensing feature flags do not currently gate UI or services.
- Trusted license keys are externally provisioned; there is no bundled production
  vendor key or issuance/revocation service in this repository.

### Product/release gaps

- `tests/integration/` is empty: no audio loopback, actual TNC/WebSocket/KISS,
  crash/reconnect, packaging, or RF-safe integration suite.
- An unsigned PyInstaller one-directory Windows test builder bundles the verified
  Mercury 1.9.11 portable runtime. There is no installer, signed application
  bundle, update mechanism, release automation, compatibility matrix, or supported
  OS-version policy.
- No project legal license has been selected; Mercury distribution/GPL obligations
  still require review.
- New Window remains a placeholder. Navigator destinations and Edit → Setup are
  implemented.
- Interpreter launches may still show **Python** in the macOS menu bar. The named
  `MercurySkyPulse.app` builder is implemented, but the unsigned bundle still
  needs manual validation and eventual signing/notarization for release.
- Local web is intentionally read-only, loopback-only, and manually refreshed. It
  has no authentication and must not be exposed beyond loopback without a new ADR.
- APRS support is coordinate-format compatibility only, not APRS packet or APRS-IS
  interoperability.

## 9. Current development milestone

**Milestone: vertical-slice prototype complete; architecture hardening and real
integration are next.**

The project has enough working breadth to exercise its intended architecture:
desktop UI, Mercury supervision/telemetry, ARQ messaging, transfers, location,
beacon, ping, BBS, persistence, local web, licensing, plugins, and tests. The next
milestone should not add another large end-user feature. It should make the current
vertical slices configurable, bounded, integration-tested, and replaceable through
stable ports.

Exit criteria for the next milestone:

- endpoint profiles are persisted and selectable for managed local, unmanaged
  local, and explicitly acknowledged remote Mercury;
- all remaining incoming telemetry sizes, rates, and timeouts are explicitly bounded;
- a pinned Mercury build passes RF-safe TNC/WebSocket/KISS integration tests;
- built-in Mercury/application protocol creation moves behind typed plugin ports;
- documentation and roadmap accurately match behavior; and
- packaging/licensing obligations and supported platforms are decided.

## 10. Exact recommended next steps

Perform these in order. Do not start with a new product feature.

1. **Add profile persistence and preferences.** Load and select the implemented
   typed profiles without weakening local/remote validation or changing the
   managed-loopback default.

2. **Finish moving connection lifecycle out of `MainWindow`.** Introduce application
   ports/coordinators for process supervision and telemetry. Keep Qt sockets in
   adapters. Wire profiles in the composition root and add tests for managed local,
   unmanaged local, missing engine, and remote profiles.

3. **Create real-Mercury integration fixtures.** Pin a compatible Mercury
   revision, use null/FIFO/simulated audio with no radio keying, then test startup,
   WebSocket status/spectrum, TNC connect/disconnect, opaque byte transfer, KISS
   beacon payloads, crash restart, and clean shutdown. Keep this separate from the
   fast unit suite.

4. **Bench-validate radio setup and tuning.** With explicit operator control, a
   dummy load, minimum practical drive, and independent PTT/power observation,
   verify catalog selection, CAT serial settings, managed restart, tune-level
   changes, explicit stop, the 12-second stop, disconnect behavior, and Mercury's
   failsafe across representative radios. Never run this as an unattended test.

5. **Finish the built-in plugin migration.** Define typed transport, telemetry,
   position, mapping, logging, and encryption ports. Move built-in construction and
   lifecycle from `presentation/app.py`/`MainWindow` into plugin factories. Do not
   enable external Python discovery.

6. **Harden transfer and persistence UX.** Add operator acceptance/quarantine for
   incoming files, persisted transfer metadata/resume policy, chat/BBS retention
   controls, log persistence/redaction policy, and database backup/restore tests.

7. **Choose application security direction.** Decide whether station identity and
   end-to-end encryption use per-station keys, a plugin provider, or remain out of
   scope. Keep encryption above Mercury. Do not imply confidentiality before this
   decision is implemented and tested.

8. **Resolve release prerequisites.** Select the repository's legal license after
   Mercury GPL review, define supported OS versions, add installers/bundles,
   signing/notarization, dependency locking, release CI, upgrade testing, and a
   Mercury compatibility matrix.

9. **Only then prioritize additional user features.** New collaboration features
    should be plugins/services over the established application protocol and must
    include contract, integration, security, and migration tests.

## 11. Safe continuation checklist

At the start of the next Codex session:

1. `cd /Users/eduardo/development/MercurySkyPulse`.
2. Read `AGENTS.md`, this file, and any ADR relevant to the requested change.
3. Inspect the current files and verify documentation claims against source.
4. Preserve Mercury as an independent external engine.
5. Do not modify `/Users/eduardo/development/mercury` unless the user opens a
   separate Mercury task and explicitly requests it.
6. Keep application features above opaque Mercury transports.
7. Preserve unrelated workspace changes and use `apply_patch` for edits.
8. Add/update ADRs for cross-cutting decisions and tests for behavior changes.
9. Run `scripts/check_local.sh` before handoff or commit.
10. Keep automated tests radio-safe: mocks and protocol fakes must not discover,
    launch, key, or tune an installed Mercury/radio accidentally.
11. Report assumptions, limitations, test results, and any remaining manual steps.

# MercurySkyPulse Project Status

## Current stage

MercurySkyPulse (MSP) is a cross-platform PySide6 communications application built
around the independent Mercury HF modem. The implemented vertical slice supports
controlled live-radio testing on macOS and Windows. More station-to-station RF
validation is required before a production release.

The source tree, tests, documentation, and packaging are maintained in this
repository. Mercury remains a separate process and implementation boundary.
Packaged engineering builds include the compatible Mercury runtime required by
the application.

MSP is licensed under GPL-3.0-or-later. Windows 10/11 x86-64 and Apple Silicon
macOS are the current engineering-test platforms. Initial x86-64 Ubuntu `.deb`
and Fedora `.rpm` builders are implemented and await native Linux validation.

## Architecture

```text
MSP user interface
    ↓
Application services
    chat · files · BBS · beacon · ping · location · reception reporting
    ↓
MSP application protocol
    framing · validation · acknowledgements · transfers
    ↓
Mercury documented interfaces
    TNC control/data · KISS broadcast · WebSocket telemetry/controls
    ↓
Mercury
    modem DSP · ARQ · audio · Hamlib CAT/PTT · radio
```

MSP owns operator workflows, persistent application data, diagnostics, and
application protocols. Mercury owns modem generation and decoding, audio I/O,
CAT, PTT, and RF transport. MSP does not open a second CAT connection or access
Mercury internals.

## Implemented application features

- Supervised managed-local Mercury process with typed unmanaged-local and remote
  endpoint profiles, bounded reconnection, and explicit remote safety policy.
- Station chat with conversations, delivery acknowledgements, persistent SQLite
  history, explicit confirmed deletion, UTC last-contact display, conservative
  cleanup of 30-day-old empty attempts, and automatic incoming ARQ listening
  under the saved station callsign.
- Verified file transfer with bounded framing, pause/resume, acceptance controls,
  SHA-256 verification, duplicate detection, and a dedicated download directory.
- Capability beacons over Mercury KISS broadcast transport.
- Bounded five-minute CQ discovery over the broadcast transport, with explicit
  Answer CQ handoff into the existing Mercury ARQ connection workflow.
- Periodic beacon scheduling pauses during every active ARQ session and for 300
  seconds after each CQ call, then restarts with a fresh interval only when idle.
- Station ping with round-trip time and modem telemetry exchange.
- Persistent BBS mailbox, bulletins, file catalog, optional password protection,
  authenticated ARQ-session identity binding, and commander role controls.
- Manual position, serial/system GPS, Maidenhead GRID calculation, position
  history, export, and location sharing.
- Loopback-only read-only web status interface.
- Trusted built-in plugin registry and offline signed licensing framework.
- Persistent rotating diagnostic log suitable for radio-to-radio test collection.
- Disabled-by-default PSK Reporter uploads for decoded MSP beacons, using bounded
  aggregation and current read-only Mercury CAT frequency telemetry. CQ calls and
  ARQ traffic are not PSK Reporter inputs.
- Explicitly enabled, manual wttr.in weather retrieval from the current station
  position or saved GRID center, with bounded preview and operator-controlled
  insertion into Chat. A connection-gated Chat WX button performs the asynchronous
  fetch without reopening Setup. Weather is not fetched automatically or added to
  beacons.

## Desktop interface

- Unified operator console with Chat as the central surface and dockable Station
  Status, Beacon, Ping, Location, transfer-in-Chat, PSK Reporter Activity, BBS,
  Radio Frequency, and Activity views. Station Status includes Mercury/TNC state,
  modem sync, TX/RX, SNR, bitrate, frequency, peer, current GRID, next-beacon
  countdown or paused state, and workflow state.
- Explicit `Listening as: CALLSIGN` identity plus a compact status-bar radio LED:
  slow blinking green for receive and steady red for transmit.
- Separate Setup window with Radio, Audio, User, GPS, Reporting, and Weather tabs.
- Movable, floatable, closable, and resizable Activity dock.
- Movable, floatable, closable, and resizable read-only Radio Frequency dock.
- Persistent window, dock, toolbar, theme, scale, Setup-window, and GPS-port
  settings, with resettable dock placement, visibility, tabification, and sizes.
- System, light, and dark themes with macOS and Windows style presets.
- Native MSP application name and icon in packaged macOS and Windows builds.
- No general waterfall, spectrum, oscilloscope, or constellation display.
  Bounded spectrum telemetry is used only for Audio diagnostics while that page
  is visible.

## Station and Mercury configuration

### Radio and CAT/PTT

- Radio models come from the selected Mercury runtime's compiled Hamlib catalog.
- The user selects a model, serial/COM/USB or network CAT address, and serial speed.
- MSP saves the selection and configures managed Mercury through documented
  startup/configuration inputs.
- Mercury remains the only Hamlib and PTT owner.
- Radio frequency and operating mode remain manually controlled at the radio.
  Mercury publishes a conservatively polled, cached read-only frequency for MSP
  display and reception reporting; MSP never opens a second CAT connection.

### Reception reporting

- PSK Reporter is opt-in and disabled by default.
- Successfully decoded MSP beacons use the saved station identity, antenna,
  decoded sender identity, and fresh Mercury frequency telemetry.
- Reports use ADIF mode `OFDM`, are deduplicated and bounded, and contain no
  messages, BBS data, files, credentials, or precise GPS coordinates.
- Setup displays a bounded activity log with the report fields and IPFIX/UDP
  delivery metadata passed to the reporting adapter.

### Audio

- Capture and playback selections prefer Mercury-native device identifiers.
- OS device discovery supplies editable fallback names when Mercury omits a list.
- Saving Audio configuration updates the managed Mercury configuration and
  restarts Mercury when required.
- Audio diagnostics show selected endpoint names/IDs, inferred capture energy,
  decoded SNR, and spectrum frame information without transmitting RF.

### TX Level Test

- The former independent tone workflow is not part of MSP.
- TX Level Test uses the normal encoded Mercury beacon waveform and the configured
  real callsign and GRID.
- The test sends immediately and at 3, 6, and 9 seconds, then stops scheduling at
  12 seconds.
- Modem TX gain is adjustable from -20 through 0 dB through Mercury's documented
  `set_tx_gain` WebSocket command.
- Mercury's reported TX peak is displayed in dBFS.
- The control is explicitly named **TX Level Test** and therefore carries no
  redundant RF-warning checkbox. The test requires saved station identity, is
  blocked during an active/linking ARQ session, and stops on link,
  telemetry loss, Setup closure, application shutdown, or explicit Stop.
- Mercury remains responsible for PTT, waveform generation, gain application, and
  completing any frame already accepted for transmission.

### User and GPS

- User setup stores the station callsign and GRID used by Chat, BBS defaults, and
  beaconing.
- Manual or GPS positions calculate a local Maidenhead GRID proposal for review.
- GPS setup lists detected serial/COM ports and permits a manual port value.
- An operator-enabled GPS source automatically resumes on later launches; missing
  saved hardware fails safely without probing unrelated serial ports.

## Runtime and packaging

- Python 3.11 or newer and PySide6 6.8–6.x are supported for source operation.
- `build.app.sh` creates the Apple Silicon macOS engineering application bundle.
- `build.exe.bat` creates the Windows 10/11 engineering executable and bundles the
  pinned, checksum-verified Mercury compatibility runtime from the public
  `N4EAC/mercury` fork. That runtime includes the read-only Hamlib frequency
  telemetry required by MSP reporting and display.
- `packaging/windows/MercurySkyPulse.iss` wraps that payload in a per-user Inno
  Setup installer with MSP branding when Inno Setup 6 is present.
- `build.linux.sh` creates an Ubuntu `amd64` `.deb` or Fedora `x86_64` `.rpm` on
  the native target and bundles the supplied compatible Linux Mercury runtime.
- `scripts/check_local.sh` is the required Mac-local quality gate. It validates
  dependencies, compiles sources, runs the aggregate tests, builds the macOS app,
  and verifies bundle identity, icon, signature, and Mercury runtime.
- GitHub-hosted workflows are disabled. GitHub is used for version control,
  collaboration, issues, and requested releases.

## Current validation priority

The unified dockable operator console governed by ADR 0028 is implemented for
field validation. Its purpose is at-a-glance awareness and simultaneous access to
all operating functions without leaving Chat. Radio/audio/CAT, identity,
GPS-source, manual-position, and reporting preferences remain in the separate
Setup window. Validate panel density, restored layouts, peer targeting, and
complete feature parity during the next two-station tests.

Continue controlled two-station RF testing on representative Windows and macOS
systems. Capture the persistent log from both stations and validate:

1. startup, audio routing, CAT/PTT, and clean shutdown;
2. chat acknowledgement and reconnect behavior;
3. file transfer, duplicate handling, pause/resume, and checksum completion;
4. beacon, ping, BBS, and location exchange;
5. TX Level Test gain changes, reported peak, ALC response, and 12-second stop;
6. recovery after temporary audio, TNC, KISS, or telemetry interruption.

Real-RF tests remain operator-controlled and are never part of unattended
automation.

## Engineering rules for the next session

1. Read `AGENTS.md` and inspect the current worktree before editing.
2. Preserve the Mercury process boundary and documented-interface integration.
3. Keep protocol inputs bounded and validated.
4. Add or update tests with behavior changes.
5. Run `scripts/check_local.sh` before committing.
6. Do not commit or push unless the user authorizes it for the current task.

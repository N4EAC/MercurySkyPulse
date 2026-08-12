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
- Station chat with conversations, delivery acknowledgements, and persistent
  SQLite history.
- Verified file transfer with bounded framing, pause/resume, acceptance controls,
  SHA-256 verification, duplicate detection, and a dedicated download directory.
- Capability beacons over Mercury KISS broadcast transport.
- Station ping with round-trip time and modem telemetry exchange.
- Persistent BBS mailbox, bulletins, file catalog, optional password protection,
  authenticated ARQ-session identity binding, and commander role controls.
- Manual position, serial/system GPS, Maidenhead GRID calculation, position
  history, export, and location sharing.
- Loopback-only read-only web status interface.
- Trusted built-in plugin registry and offline signed licensing framework.
- Persistent rotating diagnostic log suitable for radio-to-radio test collection.
- Disabled-by-default PSK Reporter uploads for decoded MSP beacons, using bounded
  aggregation and current read-only Mercury CAT frequency telemetry.

## Desktop interface

- Operational tabs: Overview, Chat, Beacon, Ping, and BBS.
- Separate Setup window with Radio, Audio, User, GPS, and Reporting tabs.
- Movable, floatable, closable, and resizable Navigator and Activity docks.
- Movable, floatable, closable, and resizable read-only Radio Frequency dock.
- Reorderable workflow tabs and persistent window, dock, toolbar, tab, theme,
  scale, Setup-window, and GPS-port settings.
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
- The operator must acknowledge RF transmission. The test requires saved station
  identity, is blocked during an active/linking ARQ session, and stops on link,
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
- `scripts/check_local.sh` is the required Mac-local quality gate. It validates
  dependencies, compiles sources, runs the aggregate tests, builds the macOS app,
  and verifies bundle identity, icon, signature, and Mercury runtime.
- GitHub-hosted workflows are disabled. GitHub is used for version control,
  collaboration, issues, and requested releases.

## Current validation priority

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

# Mercury SkyPulse Roadmap

This roadmap explains what works today and what should happen next. Work is
listed in practical order. Dates are intentionally omitted because RF testing,
native packaging, and upstream Mercury review determine the pace.

## Where the project stands

Mercury SkyPulse has a working cross-platform vertical slice suitable for
controlled amateur-radio field testing. The implemented application includes:

- a unified, dockable operator workspace centered on Chat;
- supervised managed-local Mercury plus typed unmanaged-local and explicitly
  acknowledged remote endpoint profiles;
- station listening, connectionless CQ discovery, ARQ chat, acknowledgements,
  ping, periodic beaconing, and location exchange;
- bounded ten-second Opus voice messages with capability and link-quality gates;
- verified file and image transfer with consent, progress, pause/resume,
  cancellation, checksums, and receiver-confirmed delivery;
- a persistent BBS with optional password protection and authenticated role
  controls;
- Hamlib CAT/PTT setup, read-only frequency and ARQ mode telemetry, GPS/manual
  position, weather composition, and optional PSK Reporter uploads;
- persistent diagnostic logs, a loopback-only read-only web interface, and a
  trusted built-in plugin kernel; and
- macOS, Windows, Fedora, and Ubuntu engineering build paths.

The project is still alpha engineering software. Real-RF validation, connection
hardening, native package validation, signing, upgrades, and release policy are
not complete.

## Next milestone — Safe and predictable station operation

These items should be completed before expanding the feature set.

### 1. Add automatic callsign identification

Design and implement FCC-compatible station identification for an active radio
communication. MSP should identify with the configured station callsign at the
required interval and at the end of a communication without disrupting ARQ,
voice, file transfer, or operator traffic.

Before implementation, confirm the applicable rule, record the behavior in an
ADR, define exactly which over-the-air frame provides identification, and add
timing, disconnect, missing-callsign, and queue/backpressure tests.

### 2. Harden connection and recovery behavior

- Validate the new caller-initiated, BUFFER-aware MSP session handshake over RF
  in both call directions and with a previous MSP build for compatibility.
- Finish moving process and connection lifecycle logic out of `MainWindow` and
  behind stable application ports.
- Improve cancellation, reconnects, backpressure, startup readiness,
  shutdown, and actionable connection errors.
- Add compatibility checks and clear behavior for unsupported Mercury versions.
- Add RF-safe integration tests for TNC, WebSocket, KISS, crash/restart, and
  shutdown behavior against a separately built Mercury executable.

## Next field-test cycle — Paired-station RF validation

After the identification work, run controlled two-station
tests and save the persistent log from both ends. Validate in this order:

1. startup, audio routing, CAT/PTT, frequency telemetry, and clean shutdown;
2. listen, connect, disconnect, and reconnect;
3. text acknowledgement and queued/sent/delivered/failed presentation;
4. voice recording, link gating, transfer progress, playback, and cooldown;
5. file offer, acceptance, transfer, pause/resume, cancellation, duplicate
   handling, and checksum completion;
6. beacon scheduling, CQ hold, ping, GPS/location, BBS, weather, and PSK Reporter;
7. recovery from temporary audio, TNC, KISS, or telemetry interruption; and
8. layout restoration, panel density, peer targeting, and at-a-glance status on
   representative displays.

Real-RF tests remain operator-controlled and must never run unattended.

## Mercury integration follow-up

- Follow upstream review of the read-only frequency and ARQ payload-mode
  telemetry change.
- Once accepted upstream, rebase the N4EAC compatibility branch, run the full
  Mercury suite and Windows cross-build, and repin MSP packages to the upstream
  revision.
- Keep Mercury process-isolated and communicate only through documented
  command-line, TNC/data, KISS, and WebSocket interfaces.
- Preserve managed-local as the packaged default while completing the persisted
  profile UI/loader for unmanaged-local and explicitly acknowledged remote use.

## Operator convenience improvements

These are useful but should follow the connection-safety milestone.

### LAN access to the read-only web interface

Allow another computer on the same trusted LAN to open MSP's read-only web
interface. This must be explicitly enabled; loopback-only binding remains the
secure default. The work requires:

- bind-address and access settings with visible status;
- bounded access controls and non-loopback contract tests;
- clear firewall guidance; and
- a warning that an unencrypted LAN interface exposes station telemetry to
  other devices on that network.

### BBS message-waiting notice

After the connected identity is resolved, send at most one bounded,
session-deduplicated notice containing only the waiting-message count. Show a
non-modal **Retrieve? Yes / Not now** prompt and keep retrieval operator
initiated. Protected mode must wait for authenticated identity binding; open
mode must continue to mark claimed identity as untrusted. Add adversarial
identity and session tests before implementation.

### Optional operator voice announcements

The MP3 files under `assets/voices/` are reference assets. A later feature may
play them for CQ, beacon, connection, and disconnection events through the
voice-chat output device, controlled by a persistent mute/enable setting.

## Native packages and Alpha validation

- Apple Silicon macOS Alpha 2 DMG: built and locally validated.
- Windows 10/11 x86-64: rebuild the Alpha 2 Inno Setup installer and repeat
  audio, CAT/PTT, GPS, voice, and RF tests.
- Fedora 42 x86-64: rebuild the Alpha 2 RPM and validate installation, desktop
  registration, audio, CAT/PTT, GPS, RF behavior, and uninstall.
- Ubuntu x86-64: build and validate the DEB on a native Ubuntu machine.
- Maintain a Mercury/OS compatibility matrix and verify every bundled runtime's
  source revision, checksum, license material, and required telemetry.

GitHub Actions remain disabled for routine development. The Apple Silicon Mac
and `scripts/check_local.sh` are the required local quality gate; OS-specific
installers must additionally be validated on their native operating systems.

## Release-readiness work

Complete these items before calling MSP production-ready:

- history retention controls and backup/recovery behavior;
- accessibility and keyboard-navigation review;
- stable configuration migration and upgrade policy;
- complete dependency, GPL source, and redistribution notices;
- signed/notarized installer strategy and release verification instructions;
- finalized supported OS versions and compatibility policy; and
- reproducible packaging and release procedures that do not depend on GitHub
  Actions.

## Longer-term architecture work

- Complete migration of built-in capabilities to typed plugin factories without
  enabling untrusted in-process discovery.
- Resolve consumers through typed extension ports rather than concrete adapters.
- Add alternate-provider contract tests for transport, themes, positioning,
  mapping, BBS, web, and logging.
- Before third-party plugins are allowed, implement an authenticated
  out-of-process broker with package verification, permission consent,
  revocation, scoped storage, and constrained UI contributions.

The guiding rule is to harden and validate existing radio workflows before
adding another large product capability.

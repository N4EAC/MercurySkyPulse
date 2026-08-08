# ADR 0002: Supervise Mercury as an independent child process

Status: Accepted

## Context

MercurySkyPulse must launch Mercury internally, detect crashes, restart it automatically, and display modem telemetry without modifying or linking Mercury internals.

## Decision

Mercury remains an independent executable. A Qt `QProcess` supervisor launches it with UI communication enabled, captures output, detects unexpected exits, and restarts it with bounded exponential backoff. Backoff resets only after 30 seconds of stable runtime.

MercurySkyPulse consumes the documented read-only WebSocket interface for modem status and binary spectrum frames. The GUI derives its waterfall from a bounded rolling history of spectrum frames. No TNC control/data connection or messaging is introduced.

Executable discovery uses, in order:

1. an explicitly configured path;
2. the `MERCURY_EXECUTABLE` environment variable;
3. the sibling `../mercury/mercury` checkout binary; and
4. `mercury` on `PATH`.

## Consequences

- Mercury crashes do not crash the GUI and are visible in the Activity panel.
- Local Mercury is stopped before the GUI event loop exits.
- Status, SNR, bitrate, spectrum, and waterfall are available through typed, validated telemetry objects.
- A Mercury executable must already be built or installed; MercurySkyPulse never edits or builds Mercury at runtime.
- Default operation opens Mercury's own configured audio, TNC, broadcast, and UI ports even though MercurySkyPulse only consumes UI telemetry in this phase.


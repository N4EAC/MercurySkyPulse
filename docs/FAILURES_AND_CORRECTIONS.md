# Field failures and corrections

This privacy-neutral record preserves engineering lessons from controlled field
tests. It intentionally excludes station callsigns, operator identities, exact
locations, frequencies, and captured application payloads.

## 0.1.2 — Symmetric validation traffic stalled

**Observed failure:** Mercury established an ARQ link at both endpoints, but both
MSP clients immediately queued an application validation probe. On a half-duplex
link the competing traffic did not complete before validation timed out.

**Correction:** Session validation became role-based. Only the caller initiates
the existing bounded probe; the listener acknowledges it. Older unsolicited
probes remain accepted and acknowledged for compatibility. Diagnostics now show
probe, acknowledgement, and Mercury BUFFER progress.

## 0.1.2 — Listener expired while caller BUFFER was advancing

**Observed failure:** With caller-only validation, the caller's queued probe
began advancing near the 30-second deadline. The listener could not observe the
remote BUFFER and cancelled the provisional session at 30 seconds, even though
the caller had made progress.

**Correction in 0.1.3 — Sirius:** The 30-second BUFFER no-progress deadline now
belongs only to the caller and restarts when its Mercury BUFFER decreases. The
listener waits for the caller probe under the independent 90-second maximum
deadline. Both roles retain bounded cancellation and restore listening after a
failed validation.

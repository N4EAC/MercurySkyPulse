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

## 0.1.3 — Progress arrived at the caller timeout boundary

**Observed failure:** The caller's first BUFFER decrease and its 30-second timer
event arrived in the same event-loop interval. The timer was processed first and
cancelled validation. Mercury later delivered the already-queued probe, causing
the listener to queue an acknowledgement and briefly expose a one-sided
connected state.

**Correction:** Validation is now a three-way, progress-driven state machine:
caller probe, listener acknowledgement, and caller readiness. The listener stays
provisional until readiness arrives, so feature traffic cannot be released into
a cancelled peer session. Any endpoint with locally queued handshake traffic
uses a 60-second no-progress guard which restarts on BUFFER decreases and valid
handshake events. A separate 180-second ceiling bounds the entire attempt.
Versioned probes retain the earlier behavior only when communicating with a
legacy client that cannot send the readiness frame.

## 0.1.3 — Validation and optional traffic exhausted a low-rate session

**Observed failure:** A successful direct call required more than two minutes
for both applications to show connected. A short text message then waited almost
three minutes for delivery because automatic voice-capability events had placed
roughly 750–800 bytes in Mercury's queue. In a subsequent CQ-answer attempt, the
listener's 198-byte JSON acknowledgement was still making BUFFER progress when
the caller's response deadline expired and cancelled the link.

**Correction in 0.1.4 — Canopus:** Voice chat, separate voice audio, codec
dependencies, capability negotiation, and disposable presence events are
removed. The three peer-confirmation events now use fixed 14-byte, versioned
binary frames with one shared random token. Caller role is established before
issuing Mercury controls, so direct calls and CQ answers use the same race-safe
path. Operator text no longer waits behind automatic voice or presence traffic.

## 0.1.4 — Bidirectional text submissions inflated the half-duplex queue

**Observed failure:** Paired-station testing confirmed faster connection and text
delivery, but operators submitting messages in both directions produced
overlapping PTT intervals. A receiver acknowledgement and additional application
messages accumulated hundreds of bytes while the reverse path was still active.
The asymmetric low-rate direction then required repeated RF turns to drain.

**Correction:** MSP now admits one outbound text message per station at a time.
Later messages remain locally queued until receiver-confirmed delivery and local
Mercury `BUFFER 0`. Disconnect clears the in-memory queue so unsent text cannot
cross station sessions. The correction adds no RF frames and preserves Mercury's
native ISS/IRS, piggyback `HAS_DATA`, and `TURN_REQ`/`TURN_ACK` arbitration.

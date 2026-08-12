# ADR 0021: Public audio-path diagnostics

## Status

Accepted for implementation.

## Context

Windows exposes virtual and physical audio endpoints through several host APIs.
The same friendly name may identify different capture/playback endpoints, making
one-way audio failures difficult to diagnose. Mercury reports selected native
device IDs and RX spectrum frames through its documented WebSocket, but it does
not publish PCM channel peaks, playback levels, host-API names, or the physical
capture stream's negotiated format.

## Decision

- Show Mercury's selected capture/playback friendly names and complete native IDs.
- While Setup → Audio is visible, request bounded spectrum processing solely for
  audio-path diagnostics; no general signal plot is active.
- Derive a bounded capture-energy indication from the maximum finite RX spectrum
  bin. Label it as inferred spectrum energy, not a calibrated PCM meter.
- Show the spectrum frame's sample rate and bin count, plus Mercury's decoded SNR.
- Distinguish missing telemetry from a live spectrum that remains below -100 dBFS
  for five seconds.
- Do not infer or fabricate playback level, host API, physical sample format, or
  channel count. State when Mercury's public telemetry does not provide them.
- Diagnostics are read-only and never start PTT, CAT, or RF transmission.

## Consequences

Operators can verify that Mercury is receiving non-silent samples and identify the
exact Windows endpoint without external guessing. This cannot prove correct modem
level or distinguish radio signal from local noise. Native PCM meters and playback
level require a future documented Mercury telemetry capability.

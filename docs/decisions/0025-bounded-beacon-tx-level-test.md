# ADR 0025: Bounded real-beacon TX level test

## Status

Accepted.

## Context

Operators need the normal encoded Mercury waveform while adjusting radio ALC.
Mercury provides a documented live `set_tx_gain` WebSocket command, TX gain/peak
status, and the broadcast path used by MSP beacons.

## Decision

- Add an explicitly acknowledged **TX Level Test** to Radio setup.
- Use the configured real callsign and GRID in normal MSP beacon frames. Never
  invent an identity or hide that the action transmits RF.
- Send immediately and every three seconds, with scheduling stopped at 12 seconds.
- Limit the operator control to -20..0 dB even though Mercury accepts up to +20 dB.
- Apply gain only through Mercury's documented WebSocket command and display
  Mercury's reported `tx_peak_dbfs`.
- Refuse start without saved identity or during an active/linking ARQ session.
  Stop on a new link, telemetry loss, explicit stop, Setup close, or shutdown.
- Do not open CAT or generate modem samples in MSP.

## Consequences

The test uses the actual encoded broadcast waveform and normal gain stage, making
it more representative for ALC adjustment. It is intermittent rather than a
continuous carrier and is real on-air beacon traffic. Frames already accepted by
Mercury may finish after MSP stops scheduling; Mercury retains PTT authority.

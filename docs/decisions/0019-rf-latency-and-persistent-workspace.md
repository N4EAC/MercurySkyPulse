# ADR 0019: RF latency, truthful delivery state, and persistent workspace

## Status

Accepted for implementation.

## Context

Paired Windows RF logs showed successful checksum-verified transfers taking from
roughly one-and-a-half to three-and-a-half minutes. Fixed 15-second ping and
60-second BBS challenge deadlines expired while valid traffic remained queued.
Outgoing transfer progress reached 100% when bytes were merely handed to Mercury,
not when the peer received them. Operators also need deliberate file acceptance,
visible peer identity, durable setup choices, and a restorable working layout.

## Decision

- Treat Mercury `BUFFER` reports as link activity and expose the queued-byte count
  through the transport/application boundary.
- Use a three-minute ping inactivity deadline and restart it on relevant queue
  activity. Use a five-minute BBS authentication challenge deadline.
- Do not describe locally enqueued bytes as RF delivery progress. Outgoing progress
  remains indeterminate until the peer returns a checksum result.
- Require explicit operator acceptance for incoming files in the desktop wiring;
  retain an injectable automatic policy for deterministic protocol tests.
- Persist appearance, main/setup geometry, dock/toolbar state, central-tab order,
  and the selected GPS port in per-user application settings. Do not auto-start GPS.
- Keep Navigator and Activity as movable/resizable docks, the command bar as a
  movable toolbar, and make the central workflow tabs reorderable. Central workflow
  pages remain tabs rather than independent floating windows.
- Log identifiers, state transitions, offsets, queue sizes, and outcomes, but never
  message bodies, file contents, passwords, or authentication proofs.

## Consequences

HF operations no longer fail merely because normal delivery exceeds terrestrial
UI assumptions. Transfer display distinguishes enqueueing from verified delivery.
The operator must accept every new incoming file, including a requested BBS file.
Layout restoration is local to the OS user and can be reset from the Window menu.
The three/five-minute values remain bounded defaults and may later become endpoint
profile policy after more RF measurements.

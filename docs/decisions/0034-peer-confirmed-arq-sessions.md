# ADR 0034: Peer-confirmed ARQ sessions

## Status

Accepted.

## Context

Real-RF testing demonstrated an asymmetric Mercury handshake: the calling
Mercury instance emitted `CONNECTED` while the called instance remained
`PENDING` and later cancelled. Treating the local indication as a complete MSP
session enabled application traffic that the peer could not receive and left the
operator with a false connected state.

## Decision

MSP treats Mercury's local `CONNECTED` indication as provisional. Only the
calling endpoint sends one bounded `session_probe` over the established opaque
ARQ byte stream. The listening endpoint returns one `session_probe_ack`
containing the probe identifier. Unsolicited probes remain acknowledged for
compatibility with earlier symmetric-probe clients.

An outgoing Mercury call is cancelled after 60 seconds without a local
`CONNECTED` indication. Once Mercury reports local connection, the caller has a
30-second no-progress deadline which restarts whenever Mercury's BUFFER
decreases. The listener cannot observe that remote progress and waits under the
independent 90-second maximum deadline. Any applicable timeout sends Mercury's
documented `DISCONNECT` command, reports an actionable operator message, and
allows automatic listening to resume after Mercury returns ready.

The probe is MSP application framing, not a Mercury protocol extension. Chat,
voice, files, BBS, location, and other session traffic remain disabled during
the provisional `validating` state.

## Consequences

- A one-sided Mercury connection is no longer presented as a usable MSP link.
- Two compatible MSP clients exchange one small probe and acknowledgement at
  session startup.
- Clients without this validation protocol cannot establish an application
  session with this MSP version and time out safely.
- Mercury remains responsible for ARQ establishment; MSP independently verifies
  that its peer application can exchange framed data.

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

MSP treats Mercury's local `CONNECTED` indication as provisional. Each MSP
endpoint sends one bounded `session_probe` over the established opaque ARQ byte
stream and returns one `session_probe_ack` containing the probe identifier. MSP
publishes its application session as connected only after its own probe is
acknowledged by the peer.

An outgoing Mercury call is cancelled after 60 seconds without a local
`CONNECTED` indication. Once Mercury reports local connection, peer validation
has 30 seconds to complete. Either timeout sends Mercury's documented
`DISCONNECT` command, reports an actionable operator message, and allows the
normal automatic-listen workflow to resume after Mercury returns ready.

The probe is MSP application framing, not a Mercury protocol extension. Chat,
voice, files, BBS, location, and other session traffic remain disabled during
the provisional `validating` state.

## Consequences

- A one-sided Mercury connection is no longer presented as a usable MSP link.
- Two compatible MSP clients exchange two small probes and acknowledgements at
  session startup.
- Clients without this validation protocol cannot establish an application
  session with this MSP version and time out safely.
- Mercury remains responsible for ARQ establishment; MSP independently verifies
  that its peer application can exchange framed data.

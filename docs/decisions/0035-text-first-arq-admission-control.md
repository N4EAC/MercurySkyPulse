# ADR 0035: Text-first ARQ admission control

## Status

Accepted for 0.1.4 Canopus.

## Context

Paired-station RF logs showed improved connection and message latency after the
compact Canopus handshake, but also showed both stations keying during overlapping
intervals. The clearest application symptom was bidirectional buffer growth: a
receiver acknowledgement and additional locally submitted messages raised a
Mercury queue from 112 bytes to 355 bytes while the reverse path was still active.
The tested channel was strongly asymmetric, so queued work took many RF turns to
drain.

Mercury already implements the conventional half-duplex ISS/IRS model. The caller
starts as ISS, the callee starts as IRS, pending reverse data is advertised in an
ACK with `HAS_DATA`, and Mercury uses `TURN_REQ`/`TURN_ACK` when piggybacking is not
available. MSP must not add a second over-the-air token protocol or infer physical
channel ownership from its local `BUFFER` value.

## Decision

MSP admits at most one outbound text message per station into Mercury at a time.
Additional operator messages remain in the local persistent conversation with the
visible `queued` state. The next message is submitted only after:

1. the receiving MSP has acknowledged the preceding application message;
2. Mercury reports that the local transmit buffer has drained to zero;
3. no file transfer owns the application path; and
4. the same validated ARQ session remains connected.

Disconnect clears the in-memory submission queue and marks unsettled persistent
messages failed, so text cannot leak into a later station session. The logic is
event-driven and adds no routine RF control frames, timers, polling, or connection
round trips. Mercury remains solely responsible for RF retransmission and ISS/IRS
turn exchange.

## Consequences

- Operators may type freely while MSP presents later messages as queued.
- Text cannot create an unbounded Mercury backlog from one station.
- Mercury can use its existing piggyback turn path with less competing application
  data and fewer collision-amplifying retries.
- A message on a poor path still takes the time required by the selected FreeDV
  mode; MSP does not misrepresent queue admission as RF delivery.
- Simultaneous first messages remain a condition Mercury's native turn FSM must
  arbitrate. RF validation must confirm that bounded application input is
  sufficient before considering any Mercury protocol change.

## Evidence and alternatives

Mercury's public ARQ reference documents its stop-and-wait FSM, caller/ISS and
callee/IRS roles, `HAS_DATA` piggyback turnover, and explicit `TURN_REQ`/
`TURN_ACK`. Other FreeDV/Codec2 applications similarly keep application traffic
above the modem link rather than creating an independent UI-level RF protocol.

Rejected alternatives:

- fixed multi-second sleeps, because they penalize clean links and do not establish
  distributed ownership;
- a new MSP turn frame after every message, because it duplicates Mercury and costs
  an additional low-rate RF control transmission;
- local `BUFFER 0` as permission to transmit, because it contains no information
  about the remote station's queue or current RF turn; and
- loading all composed messages immediately, because it recreates the observed
  bidirectional backlog.

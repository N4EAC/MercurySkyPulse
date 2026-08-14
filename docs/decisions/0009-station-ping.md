# ADR 0009: Station ping and modem telemetry response

## Status

Accepted.

## Decision

Ping is a bounded request/response on an established Mercury ARQ application-data
session. The request carries only its correlation identifier. The responder
returns a snapshot of its latest Mercury WebSocket telemetry: SNR, bitrate, and
modem mode. The requester calculates RTT with its own monotonic clock and combines
the response with the local SNR snapshot captured when the request was sent.

Only one request may be in flight per application instance. Requests time out
after 15 seconds. Late or unmatched responses are ignored; numeric ranges,
finiteness, mode length, and correlation are validated before presentation.

Mercury's current status JSON does not publish the specific FreeDV modulation
identifier. Mercury SkyPulse accepts a future `modem_mode` or `mode` field when
present and otherwise reports the truthful operating family `ARQ` when linked or
`idle` when not linked. It does not infer private mode mappings from Mercury
source code.

## Consequences

- RTT includes Mercury application queues, radio transmission, peer processing,
  and the return path; it is not raw TCP latency.
- Local and remote SNR are measured by different receivers and are not expected
  to match.
- A ping requires an established station session and does not use the broadcast
  beacon interface.

# ADR 0017: Typed Mercury endpoint profiles and remote safety boundary

## Status

Accepted

## Context

The vertical slice constructed a supervised Mercury process and all Mercury
clients with hardcoded loopback ports. TNC data was implicitly derived as control
port plus one, reconnect timing lived inside adapters, and no type distinguished a
managed local process from an already-running local or remote engine. Enabling
remote hosts without first bounding receive buffers would also expose
memory-growth denial of service risks. Mercury's TNC and KISS TCP interfaces do
not provide authentication or confidentiality.

## Decision

`application.endpoints` defines an immutable `MercuryEndpointProfile` containing:

- `managed-local`, `unmanaged-local`, and `remote` run modes;
- optional executable selection for managed-local mode only;
- independent TNC control, ARQ data, KISS broadcast, and WebSocket endpoints;
- a bounded exponential reconnect policy; and
- explicit TNC control-line and KISS frame/buffer limits.

The default profile preserves the existing supervised process and loopback ports
8300, 8301, 8100, and `ws://127.0.0.1:10000/websocket`. Local modes reject any
non-loopback endpoint. Remote mode rejects loopback, unspecified, and multicast
addresses, cannot select or supervise an executable, and requires the caller to
set `allow_insecure_remote=True`. That flag is an explicit risk acknowledgement;
it does not make transport secure. Operators should use a trusted private network
or authenticated tunnel until Mercury provides protected transports.

Adapters receive primitive profile values from the composition root and do not
import application features. TNC control input and KISS frames/buffers reset
safely when limits are exceeded and report malformed input. Application delivery
acknowledgement failures during disconnect races are reported rather than escaping
the receive callback.

## Consequences

- Managed, unmanaged, and remote topologies share one validated configuration
  model without moving network code into the application layer.
- Data and control ports may vary independently.
- Remote use is possible only through an explicit insecure-transport decision and
  cannot accidentally launch a local Mercury process.
- Existing users retain current loopback behavior without configuration changes.
- Endpoint persistence and preferences UI remain separate future work.

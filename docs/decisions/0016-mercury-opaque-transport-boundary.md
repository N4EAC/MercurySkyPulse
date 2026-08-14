# ADR 0016: Mercury is an opaque transport boundary

## Status

Accepted

## Context

Application features had begun depending on a `MercuryChatClient`, and the
Mercury adapter directory contained Mercury SkyPulse message and beacon codecs.
That naming and dependency direction risked making the modem responsible for
collaboration behavior.

## Decision

Mercury owns modem DSP, ARQ/KISS transport, audio, CAT, PTT, and radio behavior.
It does not own chat, files, BBS, mapping, web, authentication policy, feature
compression, application chunking, or encryption semantics.

`MercuryTncTransport` exposes documented control/session events and opaque
reliable byte reads/writes. `MercuryBroadcastTransport` exposes opaque KISS
broadcast payloads. `application_protocol` owns Mercury SkyPulse framing, event
demultiplexing, acknowledgements, bounded application payloads, and beacon codec.
Application services own workflows, persistence, checksums, roles, and access
policy. Presentation consumes application projections only.

Static tests prohibit application services from importing transport adapters,
application protocols from importing feature services/transports, and Mercury
adapters from containing feature event identifiers. A narrow transport dependency
on the neutral modem-status projection is allowed under dependency inversion.

## Consequences

Mercury can be replaced by another byte transport without moving collaboration
features into the replacement modem. New compression, encryption, or message
types belong in versioned application-protocol providers. Mercury changes are
needed only for actual modem, audio/CAT/radio, or documented transport behavior.

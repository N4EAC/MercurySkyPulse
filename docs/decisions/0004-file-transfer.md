# ADR 0004: Verified file transfer over Mercury ARQ

## Status

Accepted.

## Decision

File transfer is an application protocol layered on Mercury's documented reliable
ARQ data socket. A sender first transmits a bounded offer containing a safe display
name, byte count, and SHA-256 digest. Accepted files are streamed in ordered 4 KiB
chunks. Pause and resume exchange the receiver's byte offset; neither operation
depends on TCP packet boundaries.

Receivers write to a hidden partial file in the MercurySkyPulse downloads
directory. The partial file is atomically renamed only after its byte count and
SHA-256 digest match the offer. Existing verified checksums are recorded in local
settings and checked against the actual file before a duplicate is suppressed.
Different content with the same name receives a numbered destination name.

The initial limit is 100 MiB. File names never select a directory, file contents
are not interpreted, and incomplete/checksum-failed files are not exposed as
completed downloads.

## Consequences

- SHA-256 detects corruption and duplicates; it is not sender authentication.
- Transfer confidentiality and peer authentication remain properties of the radio
  link and deployment, not this protocol version.
- Only one outgoing transfer is actively pumped at a time. Metadata can represent
  multiple incoming transfers.

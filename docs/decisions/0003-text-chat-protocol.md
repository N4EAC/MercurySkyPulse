# ADR 0003: Text chat over the Mercury TNC interface

## Status

Accepted.

## Decision

MercurySkyPulse uses Mercury's documented VARA-style control socket (port 8300)
and reliable application-data socket (port 8301). Mercury remains an independent
process and is not modified.

Application data uses a length-prefixed, versioned JSON envelope with the `MSP1`
magic. The only payload is UTF-8 text, limited to 2048 characters. A peer
application acknowledgement advances an outgoing message from `sent` to
`delivered`. This is a transport/application receipt, not proof that a person read
the message.

Conversation metadata and text history are stored in a local SQLite database in
the operating system's application-data location. There is no attachment, file,
or arbitrary binary-payload feature.

The application schema contains `stations`, `contacts`, `conversations`,
`messages`, `settings`, and diagnostic `logs`. SQLite `user_version`
tracks forward schema upgrades; the version 2 migration preserves databases from
the original chat-only schema.

## Consequences

- Both stations need a compatible MercurySkyPulse text protocol implementation.
- Chat inherits the confidentiality properties of the radio link; content is not
  end-to-end encrypted by this first protocol version.
- Framing is independent of TCP packet boundaries and can evolve through its
  explicit version field.

# ADR 0010: Unauthenticated local-first BBS

## Status

Accepted.

## Decision

Mercury SkyPulse provides a persistent BBS over an established Mercury ARQ
application session. The SQLite version 4 schema adds system folders (`Inbox`,
`Outbox`, `Bulletins`, and `Files`), mailbox messages, and a file catalog.

Private messages contain sender, recipient callsign, subject, body, timestamp, and
status. Bulletins omit a recipient and are stored in the shared bulletin folder.
Subjects are limited to 120 characters and bodies to 4096 characters so every
mail event remains within the existing bounded frame.

BBS upload copies a selected file into application-owned storage, computes
SHA-256, records metadata, and advertises the catalog entry to the connected peer.
A download sends a catalog request; the owner serves the application-owned file
through the existing verified file-transfer pipeline only if its current checksum
still matches. BBS files are sent raw so automatic image preparation does not
change the catalog checksum.

## Trust boundary

Authentication is deliberately not implemented in this phase. Callsign, sender,
recipient, bulletin author, and file owner fields are unverified assertions from
the connected application. “Private” means addressed and filed as private mail;
it does not mean authenticated, confidential, or end-to-end encrypted. The UI
displays this warning prominently.

## Consequences

- Mail and catalog data persist locally and survive restart.
- Duplicate event identifiers are idempotently ignored for messages.
- File transfer retains its size, path, staging, and checksum protections.
- Signing, identity keys, authorization, spam controls, moderation, forwarding,
  multi-hop routing, quotas, and retention controls require later designs.

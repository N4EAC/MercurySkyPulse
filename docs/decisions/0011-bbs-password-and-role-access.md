# ADR 0011: Optional BBS password and role access

## Status

Accepted

## Context

The first BBS deliberately treated callsigns as untrusted. Stations now need an
optional shared password and commander-controlled role-based access without
coupling authentication to Mercury internals.

## Decision

Protection is off by default. Enabling it stores a random salt and scrypt-derived
256-bit verifier; plaintext passwords are never persisted or logged. ARQ peers
authenticate with a fresh bounded nonce and HMAC-SHA-256 proof, so the password
is not transmitted. ADR 0019 increased the original 60-second deadline to five
minutes after paired RF logs showed valid proofs expiring in Mercury's queue. A
proof binds the BBS session to one callsign and local role.

- `user`: private mail and file download requests.
- `operator`: user rights plus bulletins and file publication.
- `commander`: operator rights plus local protection and role administration.

Protected inbound operations pass one deny-by-default policy check. Sender and
file-owner fields must match the authenticated callsign. Disconnects clear
sessions. Commander administration requires a local password unlock and is not
exposed over radio.

## Consequences

The verifier is password-equivalent material, so the SQLite file needs host
filesystem protection. Captured proofs cannot be replayed, but traffic is not
encrypted. A shared password cannot distinguish stations that know the same
secret; per-user keys and encrypted transport remain future work.

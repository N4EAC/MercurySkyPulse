# ADR 0033: Remove product licensing and the unused encryption hook

## Status

Accepted

## Context

Mercury SkyPulse is GPL-3.0-or-later free software intended to provide the same
station features to every operator. The offline product-licensing framework
introduced editions and signed feature entitlements without gating a current
workflow. It added a cryptographic dependency, deployment files, UI status, and
maintenance work without supporting the project's distribution goals.

MSP also exposed an empty `encryption-provider` plugin extension point. No
provider, user interface, or wire protocol implemented traffic encryption. The
placeholder could nevertheless confuse operators about whether amateur-radio
traffic was obscured.

The optional BBS password mechanism is distinct: it uses one-way password
verification and a nonce/HMAC proof to authenticate access, but BBS traffic
remains readable over the radio link. Package signatures and checksums likewise
authenticate software artifacts rather than encrypt radio traffic.

## Decision

Remove the offline product-license schema, Ed25519 deployment adapter, editions,
feature entitlements, license UI and dashboard state, license-aware plugin fields,
and the `cryptography` dependency. Remove the unused `encryption-provider`
extension point and all claims that MSP provides or is preparing radio-traffic
encryption.

Retain the GPL-3.0-or-later project license, bundled dependency license notices,
release integrity checks, and optional BBS password authentication. Application
payloads sent through Mercury are not encrypted by MSP.

This decision supersedes ADR 0013 and the licensing/encryption portions of ADR
0014. It does not weaken transport bounds, session validation, BBS access policy,
or release-integrity verification.

## Consequences

- Every MSP build exposes the same feature set without activation, editions, or
  entitlement files.
- Operators have an unambiguous statement that MSP does not encrypt RF traffic.
- The runtime no longer depends on `cryptography` solely for product licensing.
- BBS passwords are still never stored or sent as plaintext, while BBS message
  content remains unencrypted.
- Adding radio-traffic encryption later would require a new explicit ADR and a
  regulatory/interoperability review; it is not a dormant plugin capability.

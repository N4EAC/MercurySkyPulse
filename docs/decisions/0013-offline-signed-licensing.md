# ADR 0013: Offline signed licensing framework

## Status

Accepted

## Context

Mercury SkyPulse needs edition and feature entitlements that work without a
network service and can be deployed centrally. This phase excludes copy
protection and machine binding.

## Decision

Licenses are bounded JSON envelopes containing schema, signing key ID, payload,
and a base64url Ed25519 signature. The signature covers canonical JSON containing
the schema, key ID, and complete payload. Verification uses the maintained
`cryptography` implementation behind an application protocol.

Payloads support edition, feature flags, subject/type, organization, deployment
ID, seat metadata, issue/not-before/expiration times, and license ID. Times are
offset-aware and evaluated in UTC. Invalid, untrusted, future, and expired
licenses grant no licensed features. No license produces Community edition.

Discovery checks explicit environment paths, a machine-wide directory, then the
per-user application-data directory. A separately provisioned public-key registry
supports key rotation and organizational deployment. Operating-system permissions
protect both files.

The framework exposes `is_enabled(feature)` but does not retroactively disable
existing workflows. Product enforcement requires explicit edition policy.

## Consequences

Checks require no network, account, daemon, or clock server. Clock rollback is
not detected. Users able to replace trusted keys control this trust boundary.
There is no hardware fingerprint, machine identifier, obfuscation, activation,
telemetry, anti-debugging, or usage tracking.

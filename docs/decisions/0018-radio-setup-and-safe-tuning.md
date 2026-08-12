# ADR 0018: Mercury-owned Hamlib radio setup

## Status

Accepted.

## Context

MSP needs radio-model and CAT/PTT setup without creating a second owner of the
radio connection or maintaining a catalog that differs from Mercury's Hamlib
build.

## Decision

- Obtain the searchable radio catalog from the selected Mercury runtime with its
  documented `-K` option.
- Persist model ID, CAT device/address, serial speed, and Mercury-native audio
  device identifiers.
- Apply managed-local station settings through Mercury's documented `-R`, `-A`,
  and application-owned `-C` configuration inputs.
- Enumerate local serial/COM/USB ports with an editable network/manual fallback.
- Keep Mercury as the only process that opens Hamlib, controls PTT, and operates
  audio devices.
- Configure unmanaged-local and remote Mercury stations at their Mercury host.

## Consequences

The model list matches the packaged Mercury runtime, CAT/PTT has one owner, and
station configuration remains explicit. Applying managed station settings may
restart Mercury. Real-radio validation remains operator-controlled.

# ADR 0015: Mac-local automated quality gate

## Status

Accepted

## Context

MercurySkyPulse needs repeatable modem, protocol, transfer, and GUI verification
without requiring radio hardware, a running Mercury instance, or a display.

## Decision

The standard runner is `python tools/run_tests.py`. It uses the standard-library
`unittest` framework and provides `modem`, `protocol`, `transfer`, `gui`, and
`all` suites. It forces Qt's offscreen platform unless the caller already chose a
platform. Protocol tests use generated, non-sensitive wire fixtures. Transfer
tests connect in-memory fake peers and write only inside temporary directories.
Modem process tests use the Python executable or mock discovery and never launch
the user's Mercury build for missing-engine cases.

`scripts/check_local.sh` is the required quality gate on the primary Apple Silicon
Mac. It validates dependencies, compiles sources, runs the aggregate suite, builds
the macOS application, and validates the packaged identity and Mercury runtime.
Routine GitHub-hosted workflows remain disabled.

## Consequences

The four named groups can be run independently for quick diagnosis while `all`
remains the code-test gate. The canonical local script additionally validates
packaging. RF tests remain operator-controlled because they require station
hardware. Automated tests never use real callsigns, private keys, or
transmit-capable radio paths.

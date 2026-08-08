# ADR 0015: Automated test matrix

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

GitHub Actions compiles and runs the aggregate suite on Linux, macOS, and Windows
with Python 3.11 and 3.13. The workflow receives read-only repository permission,
has a bounded timeout, and does not require secrets, network services, audio,
radio hardware, or station credentials.

## Consequences

The four named groups can be run independently for quick diagnosis while `all`
remains the release gate. Real-Mercury integration, audio loopback, packaging,
and RF tests remain separate future tiers because they require controlled
fixtures and platform resources. Tests must never use real callsigns, traffic,
private keys, or transmit-capable radio paths.

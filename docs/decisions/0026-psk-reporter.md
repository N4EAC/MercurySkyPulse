# ADR 0026: Optional PSK Reporter reception uploads

## Status

Accepted.

## Decision

- Add an opt-in Setup → Reporting page for PSK Reporter.
- Report successfully decoded MSP beacons as automatically extracted receptions.
- Use the configured local callsign/GRID as receiver identity and the decoded
  beacon callsign/GRID as sender identity.
- Use Mercury's cached, read-only Hamlib frequency telemetry and accept a report
  only while that value is no more than 30 seconds old. Mercury polls the existing
  CAT session conservatively and suppresses polling during active ARQ or transmit.
- Report Mercury as ADIF mode `OFDM` and include the configured antenna and MSP
  software version.
- Encode PSK Reporter's IPFIX profile locally and send UDP datagrams to
  `report.pskreporter.info:4739` through a cross-platform Qt adapter.
- Deduplicate a sender/frequency pair for five minutes, queue reports for at least
five minutes with randomized delay, flush a bounded queue when full, keep
datagrams below 1400 bytes, and include
  templates in the first three uploads and at least hourly afterward.
- Do not upload message contents, BBS data, files, credentials, or precise GPS
  coordinates. Reporting stops immediately when disabled.

## Consequences

macOS, Windows, and Linux use the same application service, IPFIX encoder, and Qt
UDP transport. Reports depend on current Mercury frequency telemetry and correct
station identity.
UDP delivery is best effort, as required by the PSK Reporter protocol.

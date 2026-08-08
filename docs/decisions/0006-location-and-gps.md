# ADR 0006: Position, GPS, APRS, and location sharing

## Status

Accepted.

## Decision

MercurySkyPulse represents positions internally as validated WGS84 decimal
latitude and longitude. Operators can set a manual position using decimal values
or APRS uncompressed coordinates in `DDMM.mmN/DDDMM.mmE` format. Manual position
is stored locally in application settings.

The platform GPS adapter supports the operating system's default positioning
source and serial NMEA receivers at 4800 baud. GPS fixes update local current
position and optional horizontal accuracy but are not persisted as history.

Location sharing is an explicit operator action over the established Mercury ARQ
session. No fix is shared automatically. The bounded event includes decimal
coordinates, APRS coordinates, source, timestamp, and optional accuracy. A
receiver validates ranges and requires the APRS and decimal representations to
agree before displaying the station position. Received locations do not replace
the local position and are not persisted in this version.

## Consequences

- System GPS availability and permissions depend on the operating system.
- USB/Bluetooth receivers must expose a serial NMEA stream and the operator must
  provide its port name.
- APRS output is coordinate-compatible but this feature does not itself transmit
  an APRS packet or connect to APRS-IS.
- Location is sensitive operational data. The UI states the sharing boundary and
  requires a deliberate action for every transmission.

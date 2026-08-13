# ADR 0008: Periodic connectionless broadcast beacon

## Status

Accepted.

## Decision

MercurySkyPulse supports an opt-in connectionless application beacon over
Mercury's documented KISS-over-TCP broadcast interface (default port 8100). It is
not an APRS packet. The default interval is Off; selectable intervals are 1, 5,
10, 15, 30, and 60 minutes. The persisted profile contains callsign, Maidenhead
grid, interval, and whether GPS may be included.

Every compact binary beacon carries a validated callsign, 4/6/8-character Maidenhead locator,
MercurySkyPulse software version, and a bounded normalized capability list.
Optional coordinates are included only when the operator enables GPS inclusion
and a valid GPS-source fix has been observed. Coordinates include their fix
timestamp separately from the beacon timestamp.

The compact versioned payload fits Mercury's conservative broadcast datagram
budget and advertises capabilities as a fixed bit set. KISS framing uses the
standard data command and implements stream fragmentation plus escaping.

Periodic attempts made without a ready broadcast interface enter a waiting state without
repeated error prompts. Manual Send Now reports failures immediately. Turn Off
persists interval zero and stops the scheduler.

Station Status reads the scheduler's actual remaining time and displays a live
next-beacon countdown. Interval zero is shown as `Manual`, distinguishing disabled
periodic scheduling from a failed beacon transport while retaining Send Now.
Automatic beacons are paused throughout an active ARQ session. Transmitting a CQ
starts or refreshes a 300-second pause; scheduling resumes with a fresh full
interval only after the CQ hold has expired and no ARQ session is active. Station
Status displays `Paused` while either hold applies. Explicit manual transmissions
remain operator-controlled.

## Consequences

- Receiving stations learn station identity, grid, version, capabilities, and
  optionally precise coordinates at the selected cadence.
- Grid is always sent; users wanting less precise disclosure should choose an
  appropriately coarse 4-character locator and leave GPS disabled.
- Capabilities are product-defined rather than arbitrary user text, limiting
  spoofing surface and keeping payloads interoperable.

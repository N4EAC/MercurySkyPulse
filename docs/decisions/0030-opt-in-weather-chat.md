# ADR 0030: Opt-in internet weather for chat composition

## Status

Implemented; service reliability validation pending

## Context

Field operators may benefit from sharing concise weather near their saved station
position. MSP must remain fully useful offline, must not infer position from an IP
address, and must not silently disclose station coordinates to an internet service.
The existing compact beacon format must remain interoperable and size bounded.

## Decision

MSP provides a manual Weather page in Setup. Internet weather access is disabled
until the operator explicitly enables it. A fetch uses the current manual/GPS
position when available, otherwise the geographic center of the saved Maidenhead
GRID. The adapter requests bounded JSON from `https://wttr.in/latitude,longitude`
with an explicit timeout; it never makes an unlocated request and therefore never
uses wttr.in IP geolocation.

The application validates and reduces the response to condition, temperature,
humidity, wind, pressure, source location, and observation time. Setup provides a
read-only preview. A compact, connection-gated **WX** button in Chat runs the same
asynchronous fetch and inserts the result directly into the composer.
The operator chooses whether current GPS/manual coordinates may be used or the
saved GRID center must always be used. Fetching never sends RF traffic. Weather
is not automatically refreshed, sent, stored in chat history, or added to
capability beacons in this slice.

## Consequences

- MSP startup and all radio workflows remain independent of internet availability.
- Enabling the feature discloses the selected coordinates to wttr.in only when the
  operator presses Fetch or WX.
- The public service may fail or rate-limit requests; errors leave existing preview
  text in place and do not affect Mercury.
- Beacon weather requires a later versioned, bounded protocol decision.

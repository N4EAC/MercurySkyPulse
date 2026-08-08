# ADR 0007: Opt-in GPS history and mapping export

## Status

Accepted.

## Decision

GPS fix retention is disabled by default and controlled by an explicit persistent
setting. When enabled, only locally acquired GPS fixes are appended to the
`location_history` table with WGS84 latitude/longitude, UTC timestamp, and optional
horizontal accuracy. Manual positions and locations shared by another station are
not added to the track.

Retained tracks can be exported as:

- GPX 1.1 for general GPS and mapping applications;
- KML 2.2 for Google Earth and compatible tools;
- GeoJSON with longitude-first coordinates for web/GIS tools; or
- CSV with conventional timestamp, latitude, longitude, and accuracy columns.

Exports are written to a temporary sibling and atomically renamed into the user
selected destination. An empty track is rejected. Export does not enable
retention, transmit the track, or delete retained data.

## Consequences

- GPS tracks are sensitive location history and consume storage until a future
  retention/deletion workflow is implemented.
- Disabling retention stops new inserts but deliberately preserves points already
  retained for later export.
- Mapping services may apply their own upload limits, privacy policies, and format
  interpretations after the user imports an exported file.

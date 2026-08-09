# ADR 0019: Separate station setup window

## Status

Accepted

## Context

Station hardware, identity, and GPS configuration consumed scarce space in the
main operational tab strip and made it harder to add future configuration areas.

## Decision

The main window contains operational views only. Edit → Setup opens a reusable
window whose initial tabs are Radio, Audio, User, and GPS. Radio remains first and
the structure permits additional configuration tabs.

Spectrum and waterfall rendering have independent, default-on visibility controls.
Hidden views stop consuming incoming frames for rendering/history.

Manual coordinates and GPS fixes are validated locally and calculate a proposed
six-character Maidenhead grid in the User tab. The operator reviews and explicitly
saves station identity. No internet geolocation service is used.

## Consequences

- The primary window has more room for operating workflows.
- CAT and audio saves remain separate explicit actions, each restarting only a
  managed Mercury instance when its configuration changes.
- Position and GRID setup work offline and disclose no location to third parties.

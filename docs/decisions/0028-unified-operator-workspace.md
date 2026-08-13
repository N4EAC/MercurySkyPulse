# ADR 0028: Plan a unified dockable operator workspace

## Status

Implemented; field validation pending

## Context

The tab-oriented vertical slice proves each workflow independently, but it makes
the operator leave Chat to inspect or invoke another activity. During a live HF
session, chat, link state, transfers, ping results, position, received beacons,
PSK Reporter activity, and BBS session state may all matter at once. The operator
must be able to understand MSP's current state at a glance and use every operating
function without losing the current conversation or another active workflow. The
existing Navigator duplicates direct tab and panel access without adding useful
state.

## Decision

Remove the Navigator/workspace dock. Evolve the main operating surface into a
saved, resizable set of Qt dock panels backed by the existing application
services. Stage this work rather than replacing all workflow pages at once:

1. Establish a central Chat panel and compact peer/session header.
2. Add dockable Ping and Location panels whose actions operate on the current
   authenticated/connected peer without changing the selected chat.
3. Add read-only Beacon/Reception, File Transfer, PSK Reporter Activity, and BBS
   Session panels using existing typed projections and bounded logs.
4. Persist visibility, placement, tabification, sizes, and a safe default layout;
   retain **Window → Reset Panel Layout**.
5. Retire the old central tabs only after their widgets and complete functionality
   move intact to the workspace; retain the same application-service wiring.

The workspace is the complete operational console, not a read-only dashboard.
It must retain access to chat/listen/connect/disconnect, file send/accept/control,
manual and periodic beacon operations, ping, directed location sharing, BBS
mail/bulletin/file/session operations, and reception-reporting activity. Status
must distinguish Mercury process, telemetry, radio transmit/receive, ARQ link,
active peer, queued transfer, GPS validity, and reporting state without requiring
a tab change.

A saved valid station callsign is also the default incoming ARQ identity. MSP
issues `MYCALL` and `LISTEN ON` when the TNC becomes ready and again after a TNC
reconnection or completed session. Callsign changes during an active ARQ session
are deferred until Mercury returns to ready. The console shows the listening
identity, and a tiny accessible status-bar LED projects Mercury telemetry as green
for receive and red for transmit.

Configuration remains in the separate Setup window: Radio/CAT/PTT, Audio, station
identity, GPS source/manual-position configuration, and PSK Reporter preferences.
Setup may be opened from the console but its fields are not duplicated in
operational docks. Current operational values such as frequency, callsign/GRID,
GPS validity, and reporting outcome may be shown read-only where useful.

Panels coordinate through application services. They do not open Mercury sockets,
CAT, audio, GPS, databases, or reporting transports directly. A shared active-peer
selection prevents Ping, location, file, and BBS actions from silently targeting
different stations.

Location sharing is a directed application-protocol action over the active ARQ
session; it is not restricted to periodic beaconing. The workspace will expose a
clear **Send Location to Connected Station** action using the current validated
manual/GPS position and calculated GRID. It must show the destination and refuse
to send when no peer or valid position exists. It never broadcasts location or
starts GPS implicitly merely because the panel is visible.

“BBS users” initially means authenticated/current BBS session identities and
roles known from actual protocol state. A general on-air presence directory is
not inferred from beacons and would require a separately specified bounded
protocol.

## Consequences

- Operators can keep Chat visible while sending a ping, sharing location, or
  monitoring transfer and reporting activity.
- No existing operational feature may be removed merely because its original tab
  is retired; migration is complete only when the action, state, errors, and
  accessibility behavior are available from the workspace.
- Existing tested services and wire protocols remain authoritative; presentation
  composition changes do not move responsibilities into Mercury.
- The default layout must remain usable on smaller Windows systems and every
  panel must be closable so inactive diagnostics do not consume space.
- Dense simultaneous updates require bounded models and coalesced disposable
  telemetry, not unbounded widget creation.
- The staged migration needs GUI tests for restored layouts, peer targeting,
  narrow screens, keyboard navigation, and both color themes.

## Implementation note

Chat is the central widget. Station Status provides the unified Mercury process,
telemetry, modem sync, TX/RX, SNR, bitrate, frequency, ARQ peer, location, and
workflow projection. The redundant Station Overview dock was removed. Beacon,
Ping, directed Location, BBS, PSK
Reporter Activity, Radio Frequency, and Activity are independent docks; file
transfer remains part of Chat so its progress stays beside the active peer. The
default layout tabifies related side docks and initially closes bottom Activity
and Reporting docks to preserve room for Chat on
smaller screens. BBS opens as a floating resizable dock by default because its
mailbox and access workflows cannot safely share the remaining vertical space;
the operator may deliberately dock it elsewhere. Summary states remain visible
and every panel can be moved, floated, resized, or shown from View or the toolbar.
Layout state version 6 removes obsolete saved Station Overview placement and
prevents pre-console dock state from hiding the
new panels on first launch.

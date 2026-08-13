# ADR 0029: Bounded broadcast CQ discovery

## Status

Implemented; real-RF validation pending

## Context

An operator cannot initiate an ARQ connection without already knowing the other
station's callsign. Periodic capability beacons advertise presence but do not
express an immediate invitation to connect. A CQ call must work without an ARQ
session and must not require MSP to control radio frequency or mode.

## Decision

MSP adds a versioned, bounded CQ frame to its existing connectionless KISS
broadcast application protocol. A CQ contains only the caller's validated
callsign, Maidenhead grid, MSP version, and UTC timestamp. Frames are rejected if
malformed, future-dated, or older than five minutes. The receiver keeps a bounded,
expiring caller list in Chat.

**Call CQ** transmits one CQ frame using the station identity saved in Setup and
starts or refreshes a 300-second periodic-beacon hold.
**Answer CQ** copies the selected caller into the existing Chat destination and
starts the normal Mercury ARQ connection. CQ does not change CAT, frequency,
mode, PTT policy, periodic beacon scheduling, or PSK Reporter input. PSK Reporter
continues to observe only decoded MSP capability beacons.

QSY is outside this protocol. Operators must remain on the common frequency while
connecting. Retuning either radio during an active ARQ session removes the RF path
and can stall or terminate the session; MSP makes no continuity guarantee.

## Consequences

- Unknown MSP stations can discover an immediate caller without a prior session.
- Receiving a CQ is passive; answering remains an explicit operator action.
- Caller lists cannot grow without bound and stale invitations disappear.
- A future coordinated-QSY protocol would require a separate safety and failure
  decision rather than implicit VFO manipulation.

# ADR 0012: Loopback-only read-only web interface

## Status

Accepted

## Context

Operators need a local browser view of MercurySkyPulse state without creating a
second control surface or exposing application data to the LAN.

## Decision

An embedded standard-library HTTP server binds exclusively to IPv4 loopback
(`127.0.0.1`). It has dashboard, message, transfer, station-status, and bounded
activity-log pages plus equivalent JSON GET endpoints. It implements only GET and
HEAD; mutation methods return 405. The server independently verifies that each
client address is loopback and supplies no CORS permission.

The HTTP worker never touches Qt widgets or SQLite. A thread-safe application
projection receives copies through existing presentation signals. Projections
are bounded to 250 conversations, 1,000 messages, 250 transfers, and 500 log
lines. Responses disable caching and framing and apply a restrictive content
security policy.

## Consequences

The interface is available only while the desktop process is running and is not
a remote administration interface. Other processes running as the local user
may still connect, so sensitive content remains subject to workstation security.
No authentication is added because the socket is loopback-only and read-only;
any future write operation or non-loopback bind requires a new security design.

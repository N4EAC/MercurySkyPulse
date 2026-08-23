# ADR 0036: Self-contained operator speech

## Status

Accepted for initial validation in 0.1.5 Arcturus; connected callsign
announcements expanded with ITU/NATO phonetics in 0.1.6 Vega.

## Context

Local spoken notices can help an operator who is away from the display and can
improve accessibility for operators with limited vision. Depending on cloud
speech services, operating-system voices, or prerecorded announcement assets
would make behavior inconsistent across supported systems and complicate
offline field operation.

## Decision

MSP packages the pinned eSpeak NG 1.52.0 command-line runtime and its speech data.
MSP invokes it without a shell to render bounded text into a local mono WAV;
Qt Multimedia plays the result through the system's default output. The initial
validation phrase is `Mercury Sky Pulse`, requested shortly after the desktop
window opens. A peer-validated session also requests `Connected to` followed by
the callsign expanded with ITU/NATO phonetic words, spoken digits, `stroke`, and
`dash` as needed.

eSpeak NG provides intelligible formant synthesis and alphanumeric pronunciation
suitable for future callsign announcements. Generated audio is cached in MSP's
application-data directory. Text is whitespace-normalized, limited to 256
characters, and passed as one argument rather than interpreted by a shell.
Rendering has a ten-second deadline. Failures are non-fatal and appear in the
Activity log.

The engine is local only. It does not use Mercury audio, transmit over RF,
require a microphone or second audio configuration, call a cloud service, use
an operating-system speech API, load a trained model, or retain prerecorded
voice assets.

## Consequences

- The test phrase behaves consistently and offline on macOS, Windows, and Linux.
- Packages gain a pinned GPL-3.0-or-later eSpeak NG runtime and data directory;
  corresponding source and license information travel with each package.
- Future announcements must remain sparse, actionable, configurable, and must
  never delay or compete with radio traffic.

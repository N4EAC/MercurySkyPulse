# ADR 0032: Session-scoped compressed voice messages

## Status

Accepted.

## Decision

MSP voice messages are short compressed audio artifacts carried by a dedicated,
bounded MSP application protocol over Mercury's opaque reliable ARQ byte stream.
They are not live FreeDV audio and Mercury remains unaware of recording,
compression, playback, cooldowns, and user-interface presence.

Recordings are limited to 10 seconds and 256 KiB. Capture, local playback,
discard, and replacement do not require an ARQ connection; this permits safe
microphone setup without RF traffic. Recordings may be sent only while an
identified ARQ session is connected, both clients advertise the compatible voice
protocol, the reported link bitrate is sustained at or above 500 bit/s, and no
ordinary file transfer is offered, queued, active, paused, verifying, or awaiting
acknowledgement. Voice uses one serialized transfer and cannot be paused or
resumed. Disconnect deletes incomplete outgoing and incoming artifacts.

The connectionless capability beacon includes `voice-chat` so an operator can
discover that the station software supports the feature. Actual MIME/protocol
compatibility is still negotiated after ARQ connection and is never inferred
solely from the beacon.

A sender may deliver one recording every 120 seconds. The cooldown starts only
after the receiver verifies the byte count and SHA-256 digest and acknowledges
delivery. Completed received recordings remain local until their conversation is
deleted.

Presence is advisory and sparse: one bounded `typing` or `recording_audio` event
is sent at the start of an activity period. There are no periodic heartbeats;
receiver-side TTLs and normal message arrival clear stale indicators. Presence is
never retried.

## Consequences

- Audio-device capture and playback remain separate from Mercury modem devices.
- Voice microphone device and bounded 0–100% capture level persist locally; the
  live dBFS meter is diagnostic and does not transmit.
- Platform multimedia codecs can differ; the sender selects only a mutually
  advertised MIME type and otherwise disables voice.
- Link-quality gating is conservative and cannot predict exact transfer time.
- Voice cannot delay, resume in, or leak into a later ARQ session.

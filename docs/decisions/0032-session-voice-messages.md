# ADR 0032: Session-scoped compressed voice messages

## Status

Superseded by the 0.1.4 Canopus efficiency release. Voice chat, its separate
audio configuration, codec dependencies, capability advertisement, and RF
events were removed after field testing showed that their negotiation and
transfer costs conflicted with MSP's text-first emergency-communications goal.

## Decision

MSP voice messages are short compressed audio artifacts carried by a dedicated,
bounded MSP application protocol over Mercury's opaque reliable ARQ byte stream.
They are not live FreeDV audio and Mercury remains unaware of recording,
compression, playback, cooldowns, and user-interface presence.

Recordings are limited to 10 seconds and 8 KiB of compressed data. Capture, local playback,
discard, and replacement do not require an ARQ connection; this permits safe
microphone setup without RF traffic. Recordings may be sent only while an
identified ARQ session is connected, both clients advertise the compatible voice
protocol, both endpoints report their received link bitrate sustained at or above
500 bit/s through readiness transitions piggybacked on the bounded capability
exchange, and no
ordinary file transfer is offered, queued, active, paused, verifying, or awaiting
acknowledgement. Voice uses one serialized transfer and cannot be paused or
resumed. Disconnect deletes incomplete outgoing and incoming artifacts.

Qt recorder output is temporary and may vary substantially by platform. Before a
draft becomes sendable, MSP resamples the full recording (up to ten seconds) to
8-kHz mono and encodes constant-bitrate Opus in Ogg. The encoder retries from
5.2 kbps downward when necessary and accepts output only after verifying a valid,
non-empty artifact no larger than 8 KiB. Operators never select a file-size or
codec parameter.

Protocol version 2 uses 384-byte chunks and stop-and-wait receiver
acknowledgements. The sender advances displayed progress only after the peer
confirms each offset, and it submits another chunk only when Mercury reports its
BUFFER at or below 256 bytes. After the last chunk, the sender displays a
verification state until the receiver validates size and SHA-256 and returns the
delivery result. A voice offer itself remains locally queued until Mercury reports
BUFFER 0. Offer, chunk, and completion response timeouts count only after the
local Mercury queue drains, so a slow pre-existing backlog cannot create a false
peer timeout.
This intentionally favors half-duplex stability over throughput.

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

While voice or file data is pending—including a paused file—MSP holds new chat
text in the local conversation as visibly queued and suppresses disposable
presence events. Queued text is submitted in order when bulk traffic releases
the session. Voice and file transfer exclude each
other. Incoming, progress, verification, ready-to-play, and delivered notices are
local UI/log snapshots derived from the transfer frames already required by the
protocol; they add no separate RF notification traffic.
Outgoing Chat snapshots advance from queued to sent only after peer participation
and to delivered only after receiver checksum confirmation. The recording UI is
locked against asynchronous link-readiness updates during capture, displays a
fixed-width `10` through `00` countdown, and colors Record/Play only while the
corresponding recorder/player state is active.

## Consequences

- Audio-device capture and playback remain separate from Mercury modem devices.
- PyAV's packaged FFmpeg libraries provide the same bounded Opus encoding path on
  macOS, Windows, and Linux; platform Qt encoder bitrate behavior is not trusted.
- Voice microphone device and bounded 0–100% capture level persist locally; the
  live dBFS meter is diagnostic and does not transmit.
- Platform multimedia codecs can differ; the sender selects only a mutually
  advertised MIME type and otherwise disables voice.
- Link-quality gating is conservative and cannot predict exact transfer time.
- The sender remains disabled until both peers advertise sustained readiness.
  The receiver still rejects an offer with `link-poor` if its link degrades;
  sender-only telemetry is insufficient on an asymmetric RF path.
- Late results cannot overwrite a terminal failed/delivered transfer state.
- Station Status reports the active voice or file state through one Transfer card.
- Older protocol-1 voice clients are deliberately incompatible with protocol 2.
- Voice cannot delay, resume in, or leak into a later ARQ session.

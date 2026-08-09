# ADR 0018: Mercury-owned Hamlib radio setup and bounded tuning

## Status

Accepted

## Context

Real-station testing requires selecting a radio, configuring its CAT endpoint,
letting Mercury key PTT, and producing a controlled tuning carrier. Duplicating
Hamlib inside MercurySkyPulse would create two competing radio owners and violate
the established boundary that Mercury owns CAT, PTT, audio, and modem behavior.
Hardcoding Hamlib's model catalog would also become stale and could disagree with
the Hamlib version compiled into the selected Mercury executable.

Mercury documents `-K` to list its compiled Hamlib models, `-R/-A` to select a
model and CAT device/address, and the TNC commands `TUNE <level>`, `TUNE ?`, and
`TUNE OFF`. Tune level is absolute dBFS from -60 through 0. Mercury refuses tune
during an active link/burst and has a 60-second hard auto-unkey timer.

## Decision

MercurySkyPulse will:

- enumerate models by executing the selected managed Mercury binary with `-K`;
- parse and display that runtime catalog in a scrollable, searchable UI;
- persist the selected model ID, device/address, CAT serial speed, and tune dBFS locally;
- enumerate local COM/USB serial ports through Qt with an editable manual/network
  CAT fallback;
- consume Mercury's documented WebSocket capture/playback device lists and
  persist the selected Mercury-native audio device IDs;
- apply CAT/PTT settings to a managed Mercury process through documented `-R/-A`
  arguments plus an application-owned minimal `-C` configuration for the
  documented `radio_serial_speed`, `input_device`, and `output_device` settings,
  followed by one explicit process restart;
- never open the CAT device or invoke Hamlib directly;
- issue tuning only through Mercury's TNC control socket;
- impose a 12-second application timer, send `TUNE OFF` on timeout, explicit
  stop, shutdown, or disconnect, and retain Mercury's independent 60-second
  failsafe; and
- present `-60..0` dBFS as an absolute tune level, separate from normal modem TX
  gain.

Unmanaged-local and remote profiles may use tuning through their documented TNC
control endpoint, but MercurySkyPulse cannot restart or reconfigure their radio.
Their operators must configure CAT/PTT at the Mercury host. Radio application is
disabled while Mercury is linked, and Mercury remains the final authority that
may reject unsafe tune requests.

## Consequences

- The model list always matches the actual managed Mercury/Hamlib build.
- Only one process owns CAT and PTT.
- Applying a radio selection interrupts the managed modem process and therefore
  requires an explicit operator action.
- Audio choices match the running Mercury build's own device enumeration rather
  than a second audio library's potentially incompatible identifiers.
- A catalog cannot be enumerated without a discoverable local Mercury executable;
  the UI reports that limitation instead of shipping a stale list.
- Real-radio verification remains a deliberate bench procedure; automated tests
  use generated catalog output and fake control ports and never key hardware.

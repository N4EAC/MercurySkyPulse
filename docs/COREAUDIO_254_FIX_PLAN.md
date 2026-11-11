# Mercury issue #254: macOS capture investigation and fix plan

Prepared: 2026-09-05. Status: planned; implementation awaits Rafael's response
and work in a separate Mercury task. Issue: https://github.com/Rhizomatica/mercury/issues/254

## Objective and boundaries

Restore reliable USB radio capture on macOS Tahoe, identify the actual failure,
and submit a small Mercury PR with reproducible evidence. Keep CAT/PTT, modem
framing, ARQ timing, and MSP application protocols unchanged. Avoid introducing
new audio dependencies or silently routing radio audio to another device.

This document is an MSP handoff artifact. Implementation belongs in the separate
Mercury repository under its own instructions. No Mercury source was modified
to prepare this plan. No issue comment or PR is submitted by this plan.

## Evidence and limits of the diagnosis

- Test host: macOS Tahoe 26.6.2, build 25G83, Apple Silicon arm64.
- Host application: Mercury SkyPulse 0.1.7, packaged application.
- Bundled Mercury: 1.9.13, revision
  `7febb89062e1380487592b42011092d84c60cd5c`.
- Radio: Yaesu FT-710; Hamlib model 1049, serial speed 115200;
  Hamlib 4.7.2, SHA 40f63488f.
- Configuration: CoreAudio, capture and playback device ID `124`, left capture
  channel. Device IDs changed between tests; 124 is a run-specific identifier.
- Mercury reports capture opening at float32 / 48000 Hz / 1 channel / 40 ms;
  playback at float32 / 48000 Hz / 2 channels / 40 ms.
- At 18:55:19 UTC: `capture stalled 5196 ms`, followed by repeated
  `capture reopen failed: AudioStreamBasicDescription`.
- After restart at 18:55:37 UTC: `ffaudio.read: AudioDeviceStart`, followed by
  `capture stalled 2005 ms` and the same reopen error, approximately every 200 ms.
- TCC at 18:55:38 UTC attributes microphone access for the Mercury subprocess
  to MSP and records `authValue=2, authReason=2, error=(null)` for requests
  416.890 and 416.891. Permission was allowed during these failures.
- Frequency reading and WebSocket connection worked. The Audio page received
  no RX spectrum. Successful playback *opening* does not establish working TX.

These observations localize a failure to Mercury's capture/backend path, but
do not prove its cause or exclude device/driver behavior, USB re-enumeration,
application packaging effects, or an additional telemetry problem. The earlier
claim that permission was the root cause was too strong: restoring the missing
usage declaration was necessary packaging work, but did not resolve capture.
Do not describe this as a proven Tahoe regression without comparative testing.

Exact-revision source was inspected in the cached macOS source archive named
`mercury-7febb89062e1380487592b42011092d84c60cd5c`. The sibling development
checkout is at a different revision and must not substitute for this baseline.
The public issue could not be retrieved during planning; read Rafael's current
response and check for overlapping upstream changes before implementation.

## 1. Establish the reproduction and instrument failures

In the separate Mercury task, read repository instructions, preserve existing
changes, and create an isolated `codex/` branch from Rafael's preferred base.
Compare that base with the failing revision and record source/dependency/compiler
versions. Retain the original executable for comparison.

First add diagnostics without changing lifecycle behavior:

- Preserve the actual `OSStatus` for start, stop, IOProc creation/destruction,
  stream-format/property queries, and device discovery. Report signed decimal,
  hexadecimal, and a printable FourCC when applicable, alongside the API name.
- Record selected and resolved device ID, input/output scope, negotiated ASBD
  fields, IOProc existence, and start/stop state. Do not log raw audio.
- Count callback invocations and bytes using synchronization suitable for the
  realtime callback. Report summaries from the worker thread; never format
  strings, allocate memory, or take a blocking logging lock in the callback.
- Record enumeration before failure and before reopen, including device alive
  state and input stream availability. Retain stable UID locally for comparison
  and redact identifying values in public attachments.
- Rate-limit repeated errors while retaining first failure, changed errors,
  repeat counts, recovery, and shutdown results.

Reproduce with the same radio and configuration after permission is granted.
Use an isolated configuration with no CAT/PTT and no application-generated
transmission for initial receive-only diagnostics. Compare the same executable
standalone and bundled, serially, under operator control. Do not run competing
Mercury instances against the same radio or reset system-wide audio/privacy.

Decision gate: obtain the underlying start/property error and callback counts
before naming the root cause. If capture works but MSP still lacks spectrum,
investigate publication/parsing separately. If permission is pending, permit its
completion before evaluating the no-samples watchdog.

## 2. Implement the smallest supported correction

Primary file: `audioio/ffaudio/ffaudio/coreaudio.c`.
Shared recovery owner: `audioio/audioio.c` (`radio_capture_thread`).

### Start/stop lifecycle

The baseline calls start on every empty nonblocking read and has no started
flag. Check whether the measured OSStatus implicates repeated start calls.
If warranted, track started state per stream and make successful start
idempotent; mark started only after `AudioDeviceStart` succeeds. Preserve an
accurate state on failure. Verify playback/drain too, since the start helper is
shared by both directions. Audit read/write error signs against ffaudio's
contract; an error must never be interpreted as captured byte count.

### Callback-safe resource cleanup

The baseline frees the ring before destroying the IOProc, and assigns `b->dev`
only late in open. Audit partial-open failures as well as the watchdog path.
Record ownership as resources are acquired. Stop and detach the IOProc while
its callback context and ring remain valid; release memory only after callback
quiescence is guaranteed by the API. Validate that guarantee against Apple
documentation. If stop/destroy fails, do not release memory still reachable by
a callback. Never destroy with a zero/unassigned device or invalid IOProc.
Keep cleanup safe when called on partially initialized and already-closed state.

### Reopen and format negotiation

The first open retries `FFAUDIO_EFORMAT`, whereas watchdog reopen currently
does not. Reuse bounded negotiation on reopen. If rate, channel count, or sample
format changes, rebuild dependent frame sizing, conversion buffers, channel
selection, and resampler state before processing data. If that cannot fit the
PR safely, reject the changed format clearly and require a controlled audio
restart; never continue using stale sizing or resampling assumptions.

For `AudioStreamBasicDescription` failures, log the actual property-query error
and device validity. Do not assume a symbol named "Description" means the
format is unsupported. Do not change the master/main element alias merely on
suspicion. Check whether the original ID still resolves to the selected device.
If it disappeared, report that fact. Persistent UID selection/rebinding is a
separate enhancement unless necessary and agreed with Rafael; never silently
switch to the Mac microphone or speakers.

### Recovery policy

Agree with Rafael whether recovery changes belong in this PR or a follow-up.
Prefer a bounded, cancellable retry schedule (provisional: four delays of
250 ms, 500 ms, 1 s, and 2 s), then a clear failed-capture state. Exact timing
must follow measured initialization behavior and existing Mercury conventions.
Reset success only after data flows; silence containing zero-valued samples is
valid data and must not trigger a stall. Shut down promptly during retry waits.
Keep existing control/status interfaces available for corrective configuration.
Use existing audio-health reporting where possible; do not invent MSP commands.

Avoid altering Linux/Windows stall policy as a side effect. Any shared-path
change must be independently covered and justified. Do not gate the entire
fix on unverified assumptions about half-duplex RF timing.

## 3. Automated verification before hardware testing

Add focused behavioral tests to Mercury's existing test harness, with a small
injectable CoreAudio-call seam or C stubs as appropriate. Validate behavior:

| Scenario | Required result |
| --- | --- |
| Open then many empty nonblocking reads | One successful start; no busy restart loop |
| Start fails, then succeeds | Original OSStatus retained; state changes only on success |
| Valid silent samples | Counted as capture activity; no watchdog reopen |
| Partial-open failure at each acquisition | Only owned resources cleaned up, once |
| Stop/destroy while callbacks are possible | Context/ring retained until callbacks cannot access them |
| Reopen requests format negotiation | Bounded retry and updated format-dependent processing, or explicit failure |
| Device disappears | Clear error; no silent default-device fallback |
| Repeated recovery failure | Bounded attempts/log volume; responsive shutdown |
| Playback start, drain, stop, restart | No regression from shared helper changes |

Run Mercury's documented complete suite and native arm64 build. Use available
sanitizers for the lifecycle harness; do not claim sanitizer success proves
real hardware race freedom. Run practical Windows cross-build and shared-code
tests where supported. Record Linux/Windows runtime validation as outstanding
if no host is available. No GitHub Actions changes are part of this work.

## 4. Operator-controlled acceptance test

Record UTC times, exact binary revision/hash, selected device, and configuration
for baseline and fixed runs. Capture logs locally and sanitize shared excerpts.

1. Receive-only capture from the FT-710 for at least ten minutes: sustained
   callbacks/sample counts and RX spectrum, no start/reopen errors or growing
   logs/memory. Confirm radio noise/audio is actually present independently.
2. Ten controlled start/stop cycles, including quit/relaunch: no lingering
   Mercury process, invalid IOProc use, crash, or resource leak.
3. USB disconnect/reconnect while idle: correct failed state and explicit
   recovery/reselection if needed; no wrong-device capture or playback.
4. Repeat with the exact fixed runtime inside the signed MSP app. Verify the
   microphone permission, capture diagnostics, status telemetry, and frequency.
5. With the operator ready and a suitable load: short TX/PTT tests followed by
   receive recovery. Check actual output, PTT release, and concurrent frequency
   polling. Then perform a short two-station decode/chat test when available.

If any test fails, preserve the first diagnostic failure and return to the
relevant stage. Do not mask capture failure by forcing the MSP meter to show
energy, increasing RF power, or assuming that successful open proves audio flow.

## 5. Review, PR, and subsequent MSP integration

Prepare a focused PR referencing #254 after local validation, with before/after
OSStatus and callback evidence, source revision, test results, unresolved limits,
and a concise explanation of each shared-code change. Keep findings that are
not necessary to fix this reproduction in separate follow-ups. Submit only
under the user's publication authorization and Rafael's agreed scope.

Once the tested revision is accepted for MSP, pin and checksum its runtime,
rebuild MSP, and verify the bundled revision. Run `scripts/check_local.sh` and
repeat packaged radio testing under operator control. Do not silently distribute
an unverified runtime to other platforms. Existing local MSP permission/refresh
changes remain separate from the Mercury PR.

Ready-to-start deliverables: diagnostic patch and baseline evidence; minimal
fix and focused tests; operator validation record; reviewable PR; then a
separately validated MSP runtime update.

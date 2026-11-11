# CoreAudio #254: operator-controlled receive-only test

This separate test window reuses MSP's audio diagnostics, telemetry parser, and
Mercury process supervisor. It does not start the normal MSP application or load
its station settings, database, beacon scheduler, speech, chat, BBS, file, GPS,
PSK Reporter, TNC or KISS clients. It has no transmit controls. It explicitly
sets CoreAudio, left capture, and `[ptt] method = none`; Hamlib is disabled.
The bundled runtime and normal MSP settings are untouched.

The tested patch fixes confirmed failed-open IOProc ownership problems. The
September 7 initial hardware observation maintained spectrum publication for
ten minutes without targeted capture errors, but restart validation was incomplete.
A complete resolution of FT-710 stalls remains **unverified**. Its base is `8796c25a`,
different from the earlier failed `7febb890` runtime; before/after differences
cannot automatically be attributed exclusively to the patch.

## Start when ready

1. Quit normal MSP and any other Mercury instance. Connect and power the FT-710;
   **USB Audio Device is available only while the radio is connected**. Keep
   external VOX/audio-triggered PTT disabled for this receive-only observation.
2. In Terminal run:

   ```sh
   cd /Users/eduardo/development/MercurySkyPulse
   ./scripts/test_coreaudio_254.command
   ```

   You may also double-click the `.command` file. Opening the test window does
   not start Mercury. This launcher uses the source Python environment, so macOS
   may request microphone access for Terminal/Python separately from normal MSP.
   The previous MSP permission does not guarantee permission for this launcher.
3. Press **Refresh Audio Devices**. This runs only Mercury's `-z` enumeration
   action with an isolated configuration. Select the FT-710's current USB
   **capture and playback** devices. Nothing defaults to ID 124 or to the Mac
   microphone/speakers. If USB is missing, reconnect the radio and refresh.
4. Press **Start selected devices — receive only**. Verify Activity identifies
   the actual executable as:

   `/private/tmp/mercury-coreaudio-254-first-fix/mercury`

   Its required SHA-256 is:

   `44886b01c98d0bc2f1845d6e912e885a04f6d4e3df4da646d760cfebce9ef430`

   A missing, changed, or unresolved override is refused. No fallback to the
   bundled executable is allowed. The exact hash, not the embedded base revision
   alone, identifies this uncommitted patch build. Keep its temporary directory
   available until testing is complete.
5. Confirm Mercury's startup lists the selected USB devices, CoreAudio, and PTT
   disabled. Approve microphone permission if prompted. Then press **Begin
   10-minute reception after permission is granted**. The timer is observation
   time, not proof that audio works. A spectrum-frame count above zero means
   Mercury has published RX samples; record the energy reading and radio audio
   conditions. Zero SNR without a decoded signal is not a capture failure.

## Ten minutes, then ten restarts

For the repeat test after the reviewed September 7 reception, you may press
**Begin restart-only retest** once the initial process publishes spectrum.
This skips repeating the ten-minute observation; it does not claim a new pass.
Wait at least 30 seconds with fresh spectrum before the first restart.

- Leave the initial run for ten minutes and observe the radio's receive audio.
  The window records telemetry/spectrum counts every five seconds and marks the
  observation complete. If capture fails, preserve that result; do not label an
  elapsed timer as success. Stop early if you need to investigate.
- After the observation, click **Controlled restart** ten times, one at a time.
  Each click stops the owned Mercury process asynchronously, then starts
  the same binary and selections. Automatic crash restarts are disabled.
- Observe each run for at least 30 seconds, including run 10. The button requires
  fresh spectrum and at least 30 seconds before stopping a running process.
  Launch attempts do not count: the counter advances only on process startup.
  A separate RX-observed count confirms fresh samples after 30 seconds.
  If launch fails, retry does not consume a restart number. Record whether capture returned, energy
  appeared, and errors occurred. The countdown does not issue restarts itself.
- **Stop Mercury** is always available. Close the window after the last run.
  Forced shutdown after ten seconds is explicitly logged and must be reported.
  The event loop remains active for WebSocket closure. After a 500 ms grace
  period the launcher terminates only its owned Mercury process. If shutdown
  remains pending three seconds later, it collects a one-second macOS stack
  sample of that child. The sampler has a bounded lifetime; sampling failure
  does not authorize elevated debugging or change any radio settings.
- To change devices after beginning a run, close the window and open a new
  session. Previous session logs remain available. No saved normal settings are
  restored because none were changed.

Do not connect another TNC/WebSocket controller to this diagnostic Mercury.
Dedicated ports are 18300/18301 (TNC), 18100 (broadcast), and 19000 (telemetry).
Only the read-only telemetry connection is used by the harness; it sends no
commands. Run in the controlled local test environment. PTT disabled does not
disable external hardware VOX.

## Evidence collection

The window displays its unique UTC session folder beneath:

`/Users/eduardo/development/MercurySkyPulse/run/coreaudio-254/`

It contains:

- `manifest.json`: binary path/hash, host version, test mode, validation reference.
- `receive-only.ini`: isolated actual Mercury configuration, including selections.
- `mercury-NN.log`: complete merged raw stdout/stderr for each attempt, including
  startup. Failed attempts may leave empty logs. Activity maps attempt numbers
  to successful process cycles. File 00 is the first attempt.
- `shutdown-NN.sample.txt`: diagnostic stack samples if shutdown is slow.
- `activity.log`: UTC markers, executable confirmation, enumeration, restarts,
  process exits, startup output, five-second telemetry and spectrum counts.

After closing the test window, replace SESSION with the folder displayed there:

```sh
./scripts/test_coreaudio_254.command --collect "/Users/eduardo/development/MercurySkyPulse/run/coreaudio-254/SESSION"
```

This creates a timestamped ZIP beside the session folder and a
`RECEPTION_REPORT.txt` identifying `capture stalled`, `capture reopen failed`,
`AudioDeviceStart`, unexpected TX indicators, and forced-stop evidence. It does
distinguish start attempts from raw-log engine initializations. Neither count
alone proves capture or clean shutdown. It does
not start Mercury. Keep the whole ZIP, not only error matches: a successful
reception log and startup context matter too. Review for local paths and any
received station details before sharing; collection does not publish anything.

Provide a short note with initial RX result, each of ten restart results, whether
permission was requested, any USB reconnect, and whether you heard radio audio
independently. No RF TX or two-station connection is part of this test.

## Software checks and rollback

The revised harness checks bind availability with `SO_REUSEADDR`, permitting
departed TCP connections while rejecting a live listener. Software tests cover
both cases using ephemeral loopback sockets, plus unsuccessful launch counting,
fresh-spectrum gating, asynchronous stop, and bounded child stack sampling with
mocked processes. No installed Mercury is launched by those tests.

Read-only source inspection found a ten-second `alarm(10)` shutdown watchdog in
Mercury's main function, consistent with the first test's code 14 exit. That
does not locate the blocked component. The prior harness's synchronous wait
prevented Qt event-loop progress during WebSocket close; the revised asynchronous
stop removes that confounder. A continued delay needs the new stack evidence
before attributing it to CoreAudio or changing Mercury.

`./scripts/test_coreaudio_254.command --check` verifies the override/hash and
prints the isolated configuration without starting Mercury, enumerating audio,
or opening the GUI. Automated checks use synthetic inputs and mocked processes;
they do not validate physical reception.

To return to normal operation, close the diagnostic window and launch normal
MSP. The override is set only in the test launcher's process environment. No
runtime replacement, installer rebuild, commit, push, or publication is needed.

The patch's existing validation report records 13/13 lifecycle tests passing,
native/cross-build and null/FIFO integration results, plus an unrelated existing
test failure and macOS test compilation workaround. Read that report before
claiming all Mercury tests pass:

`/Users/eduardo/.codex/automations/mercury-coreaudio-issue-254-first-fix/artifacts/VALIDATION.md`

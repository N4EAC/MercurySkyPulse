# ADR 0020: Bundle a pinned Mercury runtime in Windows test packages

## Status

Accepted

## Context

Windows operators expect the generated Mercury SkyPulse test folder to run without
manually locating or copying Mercury. Local-executable discovery repeatedly
produced incomplete packages and startup errors. Mercury publishes an official
portable Windows archive, while its documented integration remains process and
wire based. MSP additionally requires the read-only Hamlib frequency field added
by its public Mercury compatibility fork; the upstream release archive cannot
provide that telemetry.

Mercury is GPL-3.0. A complete runtime requires the console engine,
Hamlib, USB/runtime DLLs, and example configuration. Copying only `mercury.exe`
does not create a complete runtime.

## Decision

`build.exe.bat` downloads a pinned Mercury 1.9.12 compatibility archive from the
public `N4EAC/mercury` fork, verifies its SHA-256 digest, extracts the complete
runtime, and places it under `dist\MercurySkyPulse\mercury`. The archive contains
the GPL license and the builder writes the exact corresponding-source commit URL
into the package.

The pinned revision incorporates upstream maintainer review of MSP's telemetry
patch: optional CAT frequency polling uses a non-blocking mutex attempt and an
atomic cache, slow CAT reads are measured, failed PTT commands clear the local
PTT-active state, and the current WebSocket status schema is preserved. The
cross-build archiver correction is maintained as a separate upstream change.

Mercury is bundled as a required Mercury SkyPulse runtime component for Windows,
but remains an independently supervised child process. Mercury SkyPulse continues
to use only documented command-line, TNC/KISS, and WebSocket interfaces. No
Mercury source is copied into this repository or linked into the Python process.

The Windows engineering builder requires network access on the first build. Its
verified archive cache is stored outside the repository under the user's temporary
directory. A missing download, digest mismatch, incomplete archive, or copy error
fails the build rather than producing an incomplete application folder.

## Consequences

- Windows test packages need no manual Mercury installation or executable copy.
- Mercury and its required DLLs travel together under a versioned runtime folder.
- Updating Mercury requires an explicit version, source commit, filename, URL,
  archive digest, compatibility test, and ADR/status update.
- The public fork carries the small MSP integration patch and makes the complete
  corresponding source available under Mercury's GPL-3.0 license.
- Generated Mercury binaries remain excluded from Git; only the builder policy and
  integrity metadata are committed.
- Any distribution beyond controlled engineering tests requires legal review of
  Mercury GPL obligations and the still-undecided Mercury SkyPulse license.
- Managed Mercury remains process-isolated; this decision does not authorize
  importing Mercury internals or moving application features into Mercury.

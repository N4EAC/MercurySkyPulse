# ADR 0020: Bundle a pinned Mercury runtime in Windows test packages

## Status

Accepted

## Context

Windows operators expect the generated MercurySkyPulse test folder to run without
manually locating or copying Mercury. Local-executable discovery repeatedly
produced incomplete packages and startup errors. Mercury publishes an official
portable Windows archive, while its documented integration remains process and
wire based.

Mercury 1.9.11 is GPL-3.0 and its official `w64` archive contains the console
engine, UI executable, Hamlib, USB/runtime DLLs, and example configuration. Copying
only `mercury.exe` does not create a complete runtime.

## Decision

`build.exe.bat` downloads the pinned official Mercury 1.9.11 portable archive,
verifies its published SHA-256 digest, extracts the complete runtime, and places it
under `dist\MercurySkyPulse\mercury`. The builder also downloads and verifies the
corresponding GPL license and writes the exact source URL into the package.

Mercury is bundled as a required MercurySkyPulse runtime component for Windows,
but remains an independently supervised child process. MercurySkyPulse continues
to use only documented command-line, TNC/KISS, and WebSocket interfaces. No
Mercury source is copied into this repository or linked into the Python process.

The Windows engineering builder requires network access on the first build. Its
verified archive cache is stored outside the repository under the user's temporary
directory. A missing download, digest mismatch, incomplete archive, or copy error
fails the build rather than producing an incomplete application folder.

## Consequences

- Windows test packages need no manual Mercury installation or executable copy.
- Mercury and its required DLLs travel together under a versioned runtime folder.
- Updating Mercury requires an explicit version, filename, URL, archive digest,
  license digest, compatibility test, and ADR/status update.
- Generated Mercury binaries remain excluded from Git; only the builder policy and
  integrity metadata are committed.
- Any distribution beyond controlled engineering tests requires legal review of
  Mercury GPL obligations and the still-undecided MercurySkyPulse license.
- Managed Mercury remains process-isolated; this decision does not authorize
  importing Mercury internals or moving application features into Mercury.

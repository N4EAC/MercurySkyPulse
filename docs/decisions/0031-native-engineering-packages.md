# ADR 0031: Native engineering packages wrap a bundled Mercury runtime

- Status: Accepted
- Date: 2026-08-13

## Context

MSP needs transferable Windows, Ubuntu, and Fedora engineering packages for
controlled RF testing. A package that depends on an operator manually copying
Mercury is incomplete. Native Linux executables cannot be built or meaningfully
validated on the project's primary macOS build host.

## Decision

The existing PyInstaller one-directory application remains the common payload.

- Windows uses Inno Setup 6 to wrap the complete portable payload in a per-user
  installer with the MSP icon and the pinned, checksum-verified Mercury runtime.
- Ubuntu builds an `amd64` `.deb` on Ubuntu using `dpkg-deb`.
- Fedora builds an `x86_64` `.rpm` on Fedora using `rpmbuild`.
- Each Linux build bundles a compatible Linux Mercury executable, both Mercury
  license files, and source provenance. If no executable is supplied, it fetches
  the checksum-pinned MSP compatibility source revision and builds it locally.
  It rejects runtimes missing the MSP `radio_frequency_hz` telemetry capability.
- Linux installs under `/opt/mercuryskypulse` with a command symlink, desktop
  entry, and hicolor MSP icon.
- Fedora debugsource generation is disabled because the RPM wraps an already
  built PyInstaller payload rather than compiling sources inside `rpmbuild`.
- Outputs remain unsigned engineering artifacts until a release-signing policy
  is accepted.

## Consequences

Operators receive one artifact without manual runtime assembly. Windows may
still produce a portable directory when Inno Setup is unavailable, but reports
that no installer was created. Ubuntu and Fedora packages must be built and
tested on their respective distributions.

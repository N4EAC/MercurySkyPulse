# Contributing to MercurySkyPulse

MercurySkyPulse is an active vertical-slice prototype with desktop, protocol,
persistence, platform, and Mercury-adapter implementations. Contributions should
harden or extend the existing application without redesigning it, while preserving
Mercury as an independent engine and keeping module boundaries explicit.

Contributions are accepted under the repository's
[`GPL-3.0-or-later`](LICENSE) license. By submitting a contribution, you agree
that it may be distributed under those terms and that you have the right to
submit it.

## Before contributing

1. Read `README.md`, `docs/ARCHITECTURE.md`, `ROADMAP.md`, and `AGENTS.md`.
2. Confirm that the change belongs in MercurySkyPulse. Mercury engine bugs and
   protocol changes belong in the separate public Mercury fork and require an
   explicit Mercury task.
3. For a new dependency, language, framework, build system, or cross-cutting convention, add or update an ADR first.
4. Keep the change limited to one architectural concern where practical.

## Dependency rules

- `domain` is a reserved pure-domain boundary and must not import application,
  transport, platform, or presentation code when populated.
- `application` owns workflows, validation, access policy, neutral models, and
  external ports; it must not import Mercury adapters.
- `application_protocol` owns MSP1/beacon framing, feature-event routing,
  acknowledgements, authentication messages, and related validation.
- `transport/mercury` owns documented Mercury TNC, KISS, and telemetry wire
  details and carries opaque application bytes.
- `platform_runtime` owns process supervision, filesystem, image, GPS, local HTTP,
  mapping export, and license deployment adapters.
- `persistence` owns SQLite schema and repository behavior.
- `presentation` owns PySide6 UI coordination and the current composition root;
  UI code consumes application services and typed modem projections.
- `apps/desktop` is an alternate installed-package launcher.
- `build.exe.bat` creates an unsigned PyInstaller one-directory Windows test build
  after running the aggregate suite. It downloads the pinned MSP-compatible
  Mercury runtime, verifies its SHA-256 digest, and includes the full runtime,
  GPL license, and exact corresponding-source commit URL. Do not commit Mercury
  binaries, caches, or the builder's
  `build/` or `dist/` output.
- `packaging/windows/MercurySkyPulse.iss` creates the per-user installer from the
  complete Windows payload. `build.linux.sh` creates `.deb` and `.rpm`
  engineering packages only on their native target and requires a compatible
  Linux Mercury executable plus its licenses. Never commit generated packages.
- Tests may depend inward or instantiate outer adapters, but production dependencies must follow the architecture.

## Mercury integration rules

- Do not copy or edit Mercury source files in this repository.
- Do not rely on Mercury process globals, internal structs, or undocumented symbols.
- Prefer TCP and WebSocket contracts documented by Mercury.
- Treat host names, ports, executable paths, and timeouts as configuration.
- Isolate protocol parsing and serialization from socket lifecycle code.
- Add contract fixtures/tests whenever Mercury wire behavior is implemented or updated.
- Document the minimum compatible Mercury version or commit once compatibility work begins.

## Change workflow

- Discuss or document architectural changes before implementation.
- Add tests proportionate to every implementation change.
- Run `scripts/check_local.sh` on an Apple Silicon Mac before committing. During
  development, use `python tools/run_tests.py modem`, `protocol`, `transfer`, or
  `gui` for a focused suite, but do not substitute focused checks for the local
  aggregate and packaging gate.
- GitHub Actions are intentionally disabled. Do not add or enable a hosted
  workflow without the repository owner's explicit request.
- Update documentation when module ownership, configuration, or Mercury compatibility changes.
- Avoid generated artifacts, credentials, local Mercury binaries, logs, captures, and build outputs in commits.

## Commit and review guidance

- Use focused commits with imperative summaries.
- Explain why a dependency or boundary change is necessary.
- Call out compatibility assumptions and platform-specific behavior.
- Never include real station credentials, private keys, personal callsign data, or sensitive traffic captures in tests.

## Test safety

- Tests must run without transmitting RF or requiring radio hardware.
- Mock missing Mercury discovery so a developer's installed engine is never launched accidentally.
- Use generated callsigns and payloads rather than captured personal traffic.
- Use temporary directories for transfer and database fixtures.
- Keep GUI automation compatible with `QT_QPA_PLATFORM=offscreen`.
- Real-Mercury integration and audio tests belong in an explicitly controlled integration tier.

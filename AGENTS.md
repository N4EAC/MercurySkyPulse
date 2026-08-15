# Agent Instructions

These instructions apply to the entire Mercury SkyPulse repository.

## Project intent

Mercury SkyPulse integrates with Mercury as a process-isolated transport engine.
Windows engineering packages bundle a pinned, checksum-verified MSP-compatible
Mercury runtime from the public `N4EAC/mercury` fork as required by ADR 0020,
while source trees and implementation boundaries remain separate. Never modify a Mercury checkout as part of work in this
repository unless the user explicitly opens a separate Mercury task and requests
it there.

## Current project stage

The repository contains a trusted built-in plugin kernel, PySide6 GUI, loopback-only read-only web interface, supervised Mercury process, UI WebSocket telemetry, station chat/ping, an optionally password-protected BBS mailbox/bulletin/file catalog, verified file transfer, image preparation, GPS/manual positioning, location workflows, and periodic beacons over Mercury's documented interfaces. MSP has no product activation, feature editions, or radio-traffic encryption. Application history uses local SQLite. Protected BBS identity fields are bound to the authenticated ARQ session; open-mode identity fields remain untrusted. Do not add unrelated product logic unless the user explicitly requests it. Preserve remaining placeholder directories until real modules replace them.

## Architecture boundaries

- Keep domain code independent of Mercury, networking, UI frameworks, and OS APIs.
- Define use cases and external requirements in the application layer.
- Put Mercury TNC/WebSocket protocol adapters under `src/transport/mercury/`.
- Put process supervision, filesystem, and OS integrations under `src/platform/`.
- Put UI-facing coordination under `src/presentation/` and executable wiring under `apps/desktop/`.
- Keep Mercury wire parsing and WebSocket lifecycle under `src/transport/mercury/`; presentation consumes typed status and spectrum objects.
- Keep process launch/crash/restart behavior under `src/platform_runtime/`.
- Keep messaging and file-transfer protocols versioned, size-bounded, and independently validated.
- Keep application framing, compression, chunking, authentication, and feature event names above Mercury adapters under `src/application_protocol/` or application plugins. Mercury TNC/KISS adapters carry opaque bytes and modem facts only.
- Never make Mercury responsible for chat, file transfer, BBS, mapping, web, logging, or other application features.
- Communicate with Mercury only through documented interfaces. Do not use its private globals or internal data structures.
- Preserve the managed bundled Mercury process as the packaged default while
  retaining typed unmanaged-local and explicitly acknowledged remote profiles.
- Treat the in-process plugin registry as trusted-built-in modularity only; do not dynamically import third-party code without the out-of-process broker and package trust model.

## Working rules

- Read the nearest `AGENTS.md` before editing; a more specific nested file may add constraints.
- Inspect the worktree before changing files and preserve unrelated user changes.
- Prefer small, reviewable changes and update relevant documentation.
- Record major technology or boundary decisions in `docs/decisions/` before implementation.
- Add tests with future implementation changes, especially Mercury contract tests.
- Preserve `tests/unit/test_architecture_layers.py`; new imports must follow UI → services → application protocol → transport adapter → Mercury.
- Do not commit binaries, secrets, traffic captures, logs, generated build output, or local machine configuration.
- When the user explicitly requests a packaged artifact in Git, compress any
  artifact larger than GitHub's 50 MB recommended threshold before staging it;
  commit the compressed archive instead of the oversized raw artifact.
- Do not run destructive commands or rewrite history.

## Mac-first local quality gate

- Use the user's local Apple Silicon Mac as the primary build, test, validation,
  and packaging environment.
- Do not create, enable, modify, or depend on GitHub Actions unless the user
  explicitly requests GitHub Actions in the current task. Never re-enable a
  workflow because a tool, dependency, template, or framework recommends CI.
- Keep `.github/workflows/` free of active workflows that automatically consume
  GitHub-hosted runner minutes.
- Treat local validation as the required quality gate; never assume GitHub CI
  will catch a problem.
- Before every commit, run all checks appropriate to the change on this Mac:
  diff/format hygiene, dependency validation, source compilation, the aggregate
  unit/contract/GUI suite, practical integration checks, packaging validation,
  and non-RF application smoke tests where safe.
- Prefer macOS-native and Apple Silicon-compatible tools and commands.
- If any required local check fails, correct the problem before committing or
  pushing unless the user explicitly directs otherwise.
- Do not push automatically. Push only when the user has authorized pushing as
  part of the current task.
- When a task would normally use GitHub Actions, implement an equivalent,
  reproducible local script or command first.
- Before committing, report a short summary of files changed, local checks run,
  pass/fail status, warnings, and unresolved issues.
- Use GitHub primarily for version control, backup, collaboration, issues, and
  explicitly requested releases.

## Verification

Run `scripts/check_local.sh` as the canonical pre-commit gate. It validates the
local environment, compiles Python sources, runs the aggregate suite, creates and
checks the macOS application bundle, and verifies its bundled Mercury runtime.
Focused `modem`, `protocol`, `transfer`, and `gui` suites are available during
development but do not replace the aggregate gate. GUI smoke tests require
PySide6 and use the offscreen Qt platform. Tests must never launch a developer's
installed Mercury executable for a mocked missing-engine case or require RF
hardware. Automated launch of the packaged managed-local application is not a
safe routine check because saved CAT/PTT settings may address real RF hardware;
perform that smoke test manually under explicit operator control.

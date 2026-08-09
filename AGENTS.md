# Agent Instructions

These instructions apply to the entire MercurySkyPulse repository.

## Project intent

MercurySkyPulse integrates with Mercury as a process-isolated transport engine.
Windows engineering packages bundle a pinned, checksum-verified official Mercury
runtime as required by ADR 0020, while source trees and implementation boundaries
remain separate. Never modify a Mercury checkout as part of work in this
repository unless the user explicitly opens a separate Mercury task and requests
it there.

## Current project stage

The repository contains a trusted built-in plugin kernel, PySide6 GUI, modular offline signed licensing framework, loopback-only read-only web interface, supervised Mercury process, UI WebSocket telemetry, station chat/ping, an optionally password-protected BBS mailbox/bulletin/file catalog, verified file transfer, image preparation, GPS/manual positioning, location workflows, and periodic beacons over Mercury's documented interfaces. Application history uses local SQLite. Protected BBS identity fields are bound to the authenticated ARQ session; open-mode identity fields remain untrusted. Do not add unrelated product logic unless the user explicitly requests it. Preserve remaining placeholder directories until real modules replace them.

## Architecture boundaries

- Keep domain code independent of Mercury, networking, UI frameworks, and OS APIs.
- Define use cases and external requirements in the application layer.
- Put Mercury TNC/WebSocket protocol adapters under `src/transport/mercury/`.
- Put process supervision, filesystem, and OS integrations under `src/platform/`.
- Put UI-facing coordination under `src/presentation/` and executable wiring under `apps/desktop/`.
- Keep Mercury wire parsing and WebSocket lifecycle under `src/transport/mercury/`; presentation consumes typed status and spectrum objects.
- Keep process launch/crash/restart behavior under `src/platform_runtime/`.
- Keep messaging and file-transfer protocols versioned, size-bounded, and independently validated.
- Keep application framing, compression, chunking, authentication, feature event names, and encryption above Mercury adapters under `src/application_protocol/` or application plugins. Mercury TNC/KISS adapters carry opaque bytes and modem facts only.
- Never make Mercury responsible for chat, file transfer, BBS, mapping, web, logging, licensing, or other application features.
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
- Do not run destructive commands or rewrite history.

## Verification

Compile Python sources and run `python tools/run_tests.py all`. Focused `modem`, `protocol`, `transfer`, and `gui` suites are available, but do not replace the aggregate handoff run. GUI smoke tests require PySide6 and use the offscreen Qt platform. Tests must never launch a developer's installed Mercury executable for a mocked missing-engine case or require RF hardware.

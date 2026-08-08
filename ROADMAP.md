# MercurySkyPulse Roadmap

This roadmap records the completed vertical-slice work and sequences the
architecture hardening required before a production release. Dates remain
intentionally omitted.

## Phase 0 — Project foundation (complete)

- Establish the standalone repository and module boundaries.
- Document the Mercury integration contract and dependency rules.
- Add contributor and agent guidance.
- Establish contribution, test-safety, and repository hygiene rules.

Exit criteria: the folder structure and documentation define module ownership and
prohibit changes to Mercury from this repository. **Met.**

## Phase 1 — Architecture decisions (partially complete)

- Python 3.11+ and PySide6 are selected for the initial presentation shell in ADR 0001.
- Select the complete packaging, formatting, linting, and test toolchain beyond the current setuptools/unittest baseline.
- Confirm initial supported platform versions and packaging targets.
- Define complete endpoint configuration and secret-handling conventions.
- Formalize the already-selected managed-local, unmanaged-local, and remote
  Mercury modes as typed endpoint profiles.
- Select a project license after reviewing Mercury's GPL integration implications.
- Record decisions as ADRs in `docs/decisions/`.

Exit criteria: accepted ADRs define a minimal, reproducible toolchain without introducing product features.

The language/UI, process, protocol, transfer, location, beacon, ping, BBS, web,
licensing, plugin, test, and opaque-transport decisions are recorded in ADRs
0001–0016. Packaging targets, configuration conventions, supported platforms,
Mercury compatibility, and the project legal license remain open.

## Phase 2 — Mercury contract layer (prototype complete; hardening remains)

- TNC commands, notifications, application framing, and connection lifecycle used
  by the current slice have executable contracts.
- WebSocket JSON status and binary-spectrum schemas used by MercurySkyPulse have
  bounded parsers and contract tests.
- Protocol parser/serializer unit tests use generated, non-sensitive fixtures.
- Add compatibility checks against a separately built Mercury executable.
- Define capability negotiation and behavior for unsupported Mercury versions.

Exit criteria: adapters can be developed against executable contract tests without importing Mercury source code.

## Phase 3 — Transport adapters (vertical slice complete; hardening remains)

- Read-only Mercury UI WebSocket telemetry and spectrum contracts are implemented.
- Supervised local Mercury launch, crash detection, and bounded automatic restart are implemented.
- Control/ARQ data, KISS broadcast, and telemetry adapters are implemented
  independently.
- Add cancellation, reconnect, timeout, backpressure, and structured error behavior.
- Keep socket/WebSocket libraries contained in `src/transport/mercury/`.
- Add integration tests against local and remote Mercury instances.

Exit criteria: the application layer can use transport ports without knowing protocol or network details.

Text messaging, verified file transfer, application acknowledgements, location,
ping, BBS events, and compact capability beacons are implemented above opaque
Mercury transports. Remaining work includes explicit input bounds, stronger
timeout/backpressure/error behavior, broader command coverage, endpoint profiles,
and real-Mercury integration tests.

## Phase 4 — Mercury runtime management (managed-local prototype complete)

- The optional platform adapter for launching and supervising local Mercury is
  implemented with crash detection and bounded restart backoff.
- Support connecting to an already-running local or remote Mercury engine.
- Define startup readiness, shutdown, logs, crash recovery, and version inspection.
- Ensure the process manager never edits or patches a Mercury checkout.

Exit criteria: managed and unmanaged Mercury instances implement the same application-facing port.

## Phase 5 — Application shell (vertical slice complete)

- Initial operator journeys and application services are implemented.
- PySide6 presentation, composition, status projections, and primary workflow
  pages are implemented.
- Continue moving process/connection lifecycle out of `MainWindow` and expose
  endpoint configuration and actionable connection errors.

Exit criteria: a minimal application can connect to Mercury and display verified state without bypassing architectural boundaries.

## Phase 6 — Product capabilities (vertical slice complete; release work remains)

- Implemented slices include chat, file/image transfer, location/GPS export,
  beacon, ping, BBS, local web, offline licensing, and built-in plugins.
- Add persistence/retention controls, observability, diagnostics, accessibility,
  packaging, backup/recovery, and upgrade policy.
- Establish release automation and Mercury/OS compatibility matrices.

The next milestone should harden existing behavior rather than add another large
product feature.

## Phase 7 — Plugin migration

- The versioned kernel and initial trusted built-in registrations are implemented.
- Migrate direct construction to plugin factories one capability at a time.
- Resolve consumers through typed extension ports rather than concrete adapters.
- Add alternate-provider contract tests for transport, themes, positioning, mapping, BBS, web, logging, and encryption.
- Implement the authenticated out-of-process broker before third-party loading.
- Add package verification, permission consent, revocation, scoped storage, and constrained UI contributions.

Exit criteria: the shell contains policy and composition only, built-ins are
replaceable through stable ports, and untrusted code cannot run in the desktop
process.

## Current milestone — Architecture hardening and real integration

Work should proceed in this order:

1. Define a typed endpoint profile and ADR for managed local, unmanaged local,
   and remote Mercury while preserving current loopback defaults.
2. Move process and connection construction out of `MainWindow` behind stable
   application ports and plugin factories.
3. Bound TNC control lines and KISS frames/buffers, handle disconnect races, and
   add adversarial contract tests before enabling remote endpoints.
4. Pin a compatible Mercury revision and add RF-safe TNC, WebSocket, KISS,
   crash/reconnect, and shutdown integration tests.
5. Complete built-in plugin migration without enabling third-party in-process
   discovery.
6. Decide packaging, supported platforms, compatibility policy, and legal/source
   licensing obligations.

# Mercury SkyPulse Software Design Specification

Status: Proposed architecture

Scope: Pre-implementation design

Audience: Maintainers, contributors, security reviewers, UI designers, plugin authors, and release engineers

## 1. Purpose and scope

Mercury SkyPulse is a cross-platform desktop application built around the independent Mercury HF modem engine. Mercury owns modem DSP, audio and radio I/O, PTT, ARQ, broadcast framing, and its published transport interfaces. Mercury SkyPulse owns operator workflows, connection orchestration, durable application state, diagnostics, optional Mercury process supervision, and a safe extension model.

This specification defines the intended software boundaries before an implementation language, UI toolkit, or package system is selected. It does not authorize application logic yet. Technology selections and material changes to this design require architecture decision records (ADRs) in `docs/decisions/`.

The primary integration boundary is a process boundary. Mercury SkyPulse does not
vendor or link Mercury internals. Its separately maintained public compatibility
fork adds only bounded read-only telemetry required by MSP and preserves the
documented TCP and WebSocket boundary. This permits independent upgrades, remote
operation, fault isolation, and clear ownership of radio hardware.

The runtime layering is mandatory:

```text
User Interface
    ↓
Messaging and Collaboration Services
    chat · files · BBS · mapping · web
    ↓
Application Protocol
    framing · compression · chunking · authentication · encryption providers
    ↓
Mercury Transport Adapters
    opaque reliable bytes · opaque KISS payloads · modem telemetry
    ↓
Mercury Modem
    DSP · ARQ · broadcast transport
    ↓
Audio · CAT · PTT · HF radio
```

No feature may move downward merely because it uses Mercury. Mercury transport
adapters do not know application event names, folders, conversations, files,
roles, maps, web routes, or encryption policy.

## 2. Objectives

### 2.1 Product objectives

Mercury SkyPulse should:

1. Provide a coherent operator experience for configuring, observing, and using a Mercury transport engine.
2. Work with Mercury running locally, on another machine, or as an optionally supervised local sidecar.
3. Present transport health, radio state, data movement, and failures in language an operator can act on.
4. Preserve usable operation on intermittent, high-latency, low-bandwidth HF links.
5. Retain local configuration, connection profiles, non-sensitive history, and diagnostics across restarts.
6. Permit future features through explicit application ports and a permissioned plugin system.
7. Behave consistently across supported desktop operating systems while respecting native conventions.

### 2.2 Engineering objectives

- Keep domain and use-case logic independent of Mercury protocols, UI frameworks, databases, and operating systems.
- Depend on versioned, tested Mercury wire contracts rather than private C symbols or memory layouts.
- Isolate failure-prone I/O behind cancellable adapters with timeouts, bounded queues, and structured errors.
- Make state transitions deterministic and testable without a radio or running Mercury instance.
- Prefer immutable snapshots and events at concurrency boundaries.
- Make security-sensitive capabilities explicit, least-privileged, auditable, and disabled by default.
- Support reproducible builds, automated compatibility tests, and signed release artifacts.

### 2.3 Non-objectives

Mercury SkyPulse will not:

- implement, replace, or modify Mercury modem DSP or ARQ;
- directly control audio devices or radio PTT when Mercury owns those resources;
- duplicate Mercury's complete `mercury.ini` schema;
- guarantee delivery beyond the semantics reported by Mercury;
- require Mercury to run in the same process;
- expose arbitrary in-process plugin code by default;
- provide multi-user server functionality in the first release; or
- assume permanent network access or cloud services.

### 2.4 Quality attributes

Priorities, in order, are safety, correctness, recoverability, interoperability, usability, observability, portability, and performance. The application is control-plane heavy; predictable behavior and bounded resource use matter more than raw throughput.

Target architectural qualities:

| Attribute | Design response |
| --- | --- |
| Reliability | Explicit state machines, idempotent reconciliation, bounded retries, durable settings, crash-safe database writes. |
| Safety | Mercury remains PTT owner; RF actions require clear state, confirmation, and bounded duration. |
| Testability | Ports/adapters, protocol codecs separated from sockets, deterministic clocks, contract fixtures. |
| Portability | Platform services behind interfaces; paths and endpoints are configuration; no domain-level OS assumptions. |
| Extensibility | Versioned application and plugin contracts; feature discovery; inward dependency direction. |
| Security | Local-first defaults, authenticated remote transport policy, secret-store abstraction, permissioned out-of-process plugins. |
| Maintainability | Small modules with single ownership, ADRs, schema migrations, structured telemetry, compatibility matrix. |

## 3. System context

```text
 Operator
    |
    v
+------------------------- Mercury SkyPulse --------------------------+
| Presentation -> Application services -> Domain model               |
|                         ^                |                          |
|                         | ports          | domain events            |
|   +---------------------+----------------+----------------------+   |
|   | Mercury adapters | persistence | plugins | platform services |   |
|   +---------+--------+-------------+---------+-------------------+   |
+-------------|--------------------------------------------------------+
              | documented TCP / WebSocket contracts
              v
+-------------------------- Mercury ---------------------------------+
| TNC control | ARQ data | KISS broadcast | UI telemetry/control     |
| ARQ | modem/FreeDV | audio | radio/CAT/PTT                         |
+--------------------------------------------------------------------+
              |
              v
      Sound interface and radio
```

External actors and systems are:

- **Operator:** configures endpoints and station identity, observes link state, initiates supported workflows, and reviews diagnostics.
- **Mercury:** authoritative transport engine and source of modem/link/PTT telemetry.
- **Operating system:** supplies process, filesystem, credential store, notifications, networking, accessibility, and power/session lifecycle.
- **Plugins:** optional, separately versioned extensions communicating through a restricted plugin protocol.
- **Diagnostic/export destination:** operator-selected files; no implicit cloud upload.

## 4. Architectural style

Mercury SkyPulse uses a ports-and-adapters architecture with unidirectional dependencies and event-driven integration at I/O boundaries.

Native engineering packages preserve the process boundary: PyInstaller packages
MSP while a compatible Mercury executable and its license/source provenance are
placed beside it as a supervised runtime. Windows uses Inno Setup around the
portable directory; Ubuntu and Fedora wrap the equivalent native Linux directory
as `.deb` and `.rpm` packages. Packaging never links Mercury into MSP.

```text
apps/desktop -> presentation -> application -> domain
      |                              ^
      +-> transport/mercury ---------+
      +-> persistence ---------------+
      +-> plugins -------------------+
      +-> platform ------------------+
```

Rules:

1. The domain imports nothing from outer layers.
2. The application layer imports domain types and declares ports required by use cases.
3. Outer adapters implement application ports.
4. Presentation invokes application commands and renders application projections; it does not open sockets or query the database directly.
5. Adapters do not call each other. Cross-adapter workflows pass through application services.
6. The desktop composition root is the only module that chooses concrete implementations.
7. Transport callbacks are normalized into typed application events before reaching use cases.
8. Long-running work is cancellable and reports progress/state through defined channels.

The runtime is conceptually a single-user desktop process plus an independent Mercury process and optional plugin processes. Internal concurrency must not leak into domain APIs. A single serialized application event loop or equivalent actor/state-store model is preferred for mutable session state, while I/O adapters may use workers behind queues.

## 5. Runtime topology and lifecycle

### 5.1 Supported topologies

| Topology | Description |
| --- | --- |
| Remote engine | Mercury SkyPulse connects to Mercury on another trusted host. Mercury lifecycle is external. |
| Local unmanaged | The operator starts Mercury independently; Mercury SkyPulse connects over loopback. |
| Local managed sidecar | Mercury SkyPulse starts a configured Mercury executable, waits for readiness, monitors it, and requests orderly shutdown. |

All topologies implement the same `MercuryEndpoint` application port. Application use cases must not branch on local versus remote except when presenting lifecycle capabilities.

### 5.2 Application startup

1. Resolve platform directories and initialize structured logging.
2. Open the local database and apply forward-only migrations transactionally.
3. Load settings and endpoint profiles; validate without contacting Mercury.
4. Initialize secret-store references and plugin catalog.
5. Construct application services and initial disconnected projection.
6. Create presentation surfaces.
7. On explicit user choice or configured safe auto-connect, start/connect to Mercury.
8. Reconcile actual Mercury capabilities and state before enabling commands.

Startup must remain usable when Mercury is absent, misconfigured, incompatible, or offline.

### 5.3 Connection lifecycle

The normalized endpoint state is:

```text
DISCONNECTED -> RESOLVING -> CONNECTING -> NEGOTIATING -> READY
      ^              |           |             |          |
      +--------------+-----------+-------------+----------+
                         failure / user stop

READY -> DEGRADED -> RECONNECTING -> NEGOTIATING -> READY
```

- `NEGOTIATING` means determining available Mercury interfaces and initial state, not changing the over-air ARQ protocol.
- `DEGRADED` means some optional channel (for example WebSocket telemetry) failed while required operation may continue.
- Reconnect uses capped exponential backoff with jitter and an operator-visible countdown.
- Commands requiring an authoritative connection are rejected while state is uncertain; they are not silently queued across reconnect unless a use case explicitly defines idempotency.

### 5.4 Managed Mercury lifecycle

The optional supervisor:

- launches only an explicitly configured executable with a structured argument list;
- never invokes a shell to concatenate user-controlled arguments;
- assigns a per-run log and process identity;
- determines readiness by connecting to configured interfaces, not by fixed sleep;
- distinguishes app-started processes from pre-existing Mercury processes;
- requests graceful shutdown only for a process it owns;
- applies a bounded wait and escalates termination only with explicit policy;
- never edits, compiles, or patches a Mercury checkout; and
- exposes exit code, version output, and recent sanitized logs as diagnostics.

## 6. Module breakdown

The current source structure is:

```text
apps/desktop/                    Alternate installed-package launcher
src/domain/                      Reserved pure-domain placeholder
src/application/                 Workflows, validation, policy, neutral models
src/application_protocol/        MSP1/beacon codecs and event routing
src/transport/mercury/
  tnc.py                         TNC control and opaque ARQ byte stream
  beacon.py                      KISS framing and opaque broadcast payloads
  telemetry/                     WebSocket JSON/binary codec and connection
src/persistence/                 SQLite schema and repository
src/platform_runtime/            Process, filesystem, GPS, web, weather, license adapters
src/platform/                    Reserved platform placeholder
src/presentation/                PySide6 UI and current composition root
tests/unit/                      Pure module tests
tests/contract/                  Application/Mercury wire-contract tests
tests/integration/               Reserved for real-Mercury integration tests
```

The trusted built-in plugin kernel currently lives in `src/application/plugins.py`
and registration lives in `src/presentation/plugin_bootstrap.py`. `src/domain/`,
`src/platform/`, several transport subdirectories, and `tests/integration/` remain
placeholders; populate them only through an approved migration or real integration
work.

### 6.1 Domain module

Owns stable product vocabulary and invariants. Candidate value types include:

- endpoint/profile identity;
- callsign and station identity (validated but not tied to a Mercury command string);
- link/session state;
- transport capability set;
- transfer identifier, direction, progress, and outcome;
- signal-quality and bitrate measurements with units;
- diagnostic severity and redaction classification; and
- plugin identity and declared capability.

The domain does not contain sockets, database records, JSON objects, UI colors, file paths, process IDs, or retry timers. It emits facts; application policy decides effects.

### 6.2 Application module

Owns commands, use cases, orchestration, ports, and read projections. Initial application ports should include:

- `MercuryEndpointPort`: connect, disconnect, capabilities, normalized events;
- `ArqSessionPort`: listen/connect/disconnect and application byte stream;
- `BroadcastPort`: send/receive KISS payloads when enabled;
- `TelemetryPort`: status and spectrum subscription;
- `EndpointProfileRepository` and `PreferenceRepository`;
- `HistoryRepository` and `DiagnosticRepository`;
- `SecretStorePort`;
- `MercuryProcessPort` for optional supervision;
- `PluginCatalogPort` and `PluginRuntimePort`;
- `ClockPort` and `IdGeneratorPort`; and
- `FileExportPort` and `NotificationPort`.

Commands and events should be typed, immutable values. Each command returns a defined success/error result and may expose cancellation. Application projections provide presentation-ready semantic state without framework widgets.

### 6.3 Mercury control adapter

Owns the line-oriented control socket (default port `8300`):

- incremental delimiter parsing across arbitrary TCP chunks;
- command serialization and response correlation where the protocol allows it;
- asynchronous notifications such as connection, PTT, buffer, SNR, bitrate, busy, and keepalive;
- strict length limits and unknown-message preservation for diagnostics;
- separation of critical state from disposable telemetry;
- readiness and liveness tracking; and
- protocol-version/capability adaptation.

It must not interpret radio policy beyond normalizing Mercury facts. Raw control lines are not exposed to the UI or plugins by default.

### 6.4 Mercury ARQ data adapter

Owns the raw reliable byte-stream socket (default control port + 1, normally `8301`):

- bounded asynchronous reads/writes;
- partial-write handling;
- explicit backpressure and maximum application queue size;
- association with the current normalized ARQ session;
- EOF/error semantics distinct from over-air disconnect; and
- byte counters derived without retaining payload content.

Application framing above this stream, if later needed, belongs in a separate application protocol module or plugin, not in the Mercury adapter.

### 6.5 Mercury broadcast adapter

Owns the broadcast socket (default `8100`) and KISS framing:

- escape/unescape codec with strict frame-size limits;
- standard and Mercury-supported command handling;
- malformed-frame rejection and counters;
- bounded receive fan-out; and
- explicit enablement because broadcast is optional.

### 6.6 Mercury telemetry adapter

Owns the WebSocket endpoint (default port `10000`, path `/websocket`):

- strict JSON message decoding by `type`;
- validated flat command encoding for supported controls;
- device/radio list normalization;
- binary spectrum header, endian, FFT-size, sample-rate, and payload validation;
- latest-value coalescing for high-rate spectrum/status data;
- independent failure/reconnect state so loss of optional telemetry need not terminate TNC data; and
- TLS certificate validation according to configured trust policy.

Unknown fields are ignored for forward compatibility; unknown message types are rate-limited in diagnostics. Invalid frames never reach presentation code.

### 6.7 Mercury session coordinator

Coordinates the independent Mercury channels without merging their protocols. It:

- establishes required versus optional channels;
- produces one capability/state snapshot;
- reconciles control notifications with socket connectivity;
- invalidates stale session state after reconnect;
- prevents commands before readiness;
- routes telemetry through bounded subscriptions; and
- emits endpoint health diagnostics.

It does not replace Mercury's ARQ FSM and never predicts over-air success.

### 6.8 Persistence module

Implements repositories over the local database, transactions, migrations, retention, backup/export, and mapping between records and domain values. SQL and database-library types remain inside this module.

### 6.9 Plugin module

Discovers plugin manifests, validates compatibility and permissions, starts isolated plugin processes, brokers messages, applies quotas, and records lifecycle/audit events. It exposes application extension points, not unrestricted internal object access.

### 6.10 Platform module

Implements:

- per-user configuration/data/cache/log paths;
- optional Mercury process supervision;
- native credential storage;
- filesystem import/export and atomic file replacement;
- desktop notifications;
- single-instance coordination if selected;
- network reachability hints (never treated as authoritative);
- sleep/resume and session shutdown hooks; and
- platform metadata for diagnostics.

### 6.11 Presentation module

Owns framework-independent screen state, navigation intents, validation messages, unit formatting, throttling of high-frequency visual data, accessibility labels, and mapping application errors to operator actions. Framework bindings stay in an outer UI adapter under the desktop app or a future dedicated adapter directory.

### 6.12 Desktop composition root

Loads configuration, selects concrete database/platform/UI/plugin implementations, wires ports, starts application services, and owns top-level shutdown. It contains no business rules and is the only production module allowed to reference all outer adapters.

## 7. UI philosophy

### 7.1 Principles

The UI is operator-centered, state-explicit, calm under failure, and progressive in complexity.

- **Connection truth first:** always show whether the application is connected to Mercury, whether Mercury is linked over air, and whether the radio is transmitting. These are distinct states.
- **Safe controls:** disable actions that cannot succeed; explain why. Never imply that closing a window guarantees radio unkey unless Mercury confirms it.
- **Progressive disclosure:** primary workflows use concise status; modem, audio, radio, and protocol diagnostics live in advanced views.
- **No modal error storms:** persistent problems appear in a health area with one current diagnosis, recovery action, and expandable detail.
- **Local-first operation:** all essential workflows remain available without internet or cloud accounts.
- **Accessible by design:** full keyboard navigation, meaningful focus order, screen-reader labels, scalable text, reduced-motion support, and no color-only status.
- **Stable visual cadence:** status is coalesced; transient spectrum diagnostics
  are bounded and may drop stale frames rather than freeze controls.
- **Honest uncertainty:** stale or unavailable values display as unknown/stale, never as zero or healthy.

### 7.2 Information architecture

The initial shell should support these conceptual areas, subject to product validation:

1. **Connection:** endpoint profile, connect/disconnect, engine health, version/capabilities.
2. **Session:** callsigns, listen/call state, peer, ARQ link state, buffer and transfer activity.
3. **Signal:** SNR, bitrate, sync, and PTT/RX direction. Audio setup may show a
   bounded inferred energy diagnostic; there is no general signal plot.
4. **Messages/transfers:** future application workflows built above the Mercury byte stream.
5. **Diagnostics:** channel health, reconnect history, sanitized logs, export bundle.
6. **Settings:** Mercury endpoint/lifecycle, security/trust, retention, plugins, accessibility.

### 7.3 State management

Views render immutable application projections. User actions become typed application commands. Views do not mutate shared models, query repositories, or call transport adapters. The application publishes state revisions; presentation discards out-of-order revisions and throttles only rendering, not semantic state transitions.

Window closure, OS shutdown, and disconnect actions use explicit shutdown coordination. Unsaved preference changes and active sessions require clear handling. Destructive actions identify their scope and recoverability.

### 7.4 Diagnostics and terminology

Primary UI terms should be understandable without exposing implementation details. Advanced diagnostics may show raw Mercury command names or ports, but the normal UI uses terms such as “Mercury engine,” “radio link,” “application connection,” “transmitting,” and “queued bytes.” Every error should include what failed, operational impact, and a next action.

## 8. Database design

### 8.1 Database choice and role

The default design is one embedded SQLite database per OS user profile. The final driver and binding require an ADR, but the logical choice is justified by offline operation, transactional migrations, portability, mature recovery tooling, and no server requirement.

The database stores Mercury SkyPulse application state. It does not replace Mercury configuration or store Mercury's live protocol state as authoritative.

### 8.2 Logical data model

Planned tables/entities:

| Entity | Purpose |
| --- | --- |
| `schema_migrations` | Applied migration version, checksum, and timestamp. |
| `endpoint_profiles` | Named Mercury host/ports, TLS mode, lifecycle policy, and non-secret options. |
| `preferences` | Versioned application and UI preferences. |
| `station_profiles` | Operator-selected station identity and non-secret workflow defaults. |
| `connection_history` | Endpoint connection attempts, normalized outcome, version, and durations. |
| `session_history` | ARQ peer/session metadata, start/end/outcome, aggregate bytes and metrics. |
| `transfer_history` | Future application-level transfer metadata and outcome; payload storage is separate and opt-in. |
| `diagnostic_events` | Structured, redacted operational events subject to retention. |
| `plugin_registry` | Installed plugin identity, version, source, enabled state, and compatibility. |
| `plugin_permissions` | Explicit capability grants by plugin and scope. |
| `plugin_state` | Size-limited namespaced plugin key/value metadata. |

Identifiers are opaque generated IDs. Timestamps are UTC with explicit precision. Units are encoded in column names or schema documentation. Enums use stable symbolic values with unknown-value handling.

### 8.3 Data minimization

- Do not persist ARQ or broadcast payload bytes by default.
- Do not persist raw spectrum frames.
- Callsigns, peer identifiers, addresses, filenames, and log fields may be personal or operationally sensitive; retain only when needed and provide deletion/export controls.
- Store aggregate byte counts and bounded metric summaries instead of packet-level traces.
- Plaintext secrets, private keys, and passwords are never stored in the database. General-purpose credentials use opaque OS credential-store references. The optional BBS shared password is represented by a salted, one-way verifier as specified by ADR 0011; that verifier is password-equivalent material and requires restrictive database file permissions.
- Plugin state is namespaced, quota-limited, and cannot query core tables directly.

### 8.4 Transactions and migrations

- Enable foreign-key enforcement.
- Use write-ahead logging when safe for the selected platform/filesystem, with a fallback mode documented.
- Apply migrations in one startup transaction before repositories become available.
- Migrations are forward-only, ordered, checksummed, and covered by upgrade tests from every supported schema version.
- A failed migration leaves the previous database intact and starts the application in a recovery/export mode.
- Never downgrade a schema in place.
- Repository operations that update related records are atomic.

### 8.5 Retention, backup, and recovery

Retention defaults should be conservative and user-configurable by data class. Maintenance deletes in bounded batches and checkpoints safely. Diagnostic export produces a redacted archive only after preview/confirmation. Backup uses SQLite's safe online backup mechanism or a closed-database copy, never a blind copy of active database files. Corruption handling preserves the original file, offers a recovery/export path, and never silently resets user data.

## 9. Transport design

### 9.1 Transport principles

- Treat TCP as a byte stream: handle segmentation, coalescing, partial reads, and partial writes.
- Bound every message, queue, buffer, retry series, and deadline.
- Separate codecs from connection lifecycle.
- Support cancellation and deterministic shutdown.
- Normalize transport errors without losing diagnostic cause.
- Reconcile after reconnect; never assume socket reconnection preserves Mercury session state.
- Prefer latest-value coalescing for telemetry and lossless bounded flow control for application data.
- Do not log payload content or credentials.

### 9.2 Mercury endpoints

All endpoints are configurable. Defaults are:

| Interface | Default | Required | Use |
| --- | --- | --- | --- |
| TNC control | TCP `8300` | Required for ARQ control | Commands and asynchronous status. |
| TNC data | TCP `8301` | Required for ARQ payload | Reliable application byte stream. |
| Broadcast | TCP `8100` | Optional | KISS broadcast payloads. |
| UI WebSocket | WS/WSS `10000`, `/websocket` | Optional | Status, spectrum, devices, supported controls. |

Mercury SkyPulse must not assume these ports are adjacent except where a profile explicitly derives data from control. IPv4/IPv6 and DNS behavior depend on the future network library but should use system resolution and happy-eyeballs behavior where available.

### 9.3 Capability discovery

Mercury currently does not provide one comprehensive formal capability handshake across all interfaces. The adapter therefore uses conservative discovery:

- configuration declares expected/allowed interfaces;
- connection success establishes availability, not feature completeness;
- recognized version information and protocol responses refine capabilities;
- unknown responses do not enable unsafe features;
- required incompatibility blocks operation with an actionable message;
- optional incompatibility produces `DEGRADED` state.

A compatibility layer maps supported Mercury releases/commits to behaviors. Contract fixtures and integration tests are the source of truth.

### 9.4 Backpressure

Control state changes are lossless within a bounded queue; disposable repeated telemetry may coalesce. ARQ application writes return accepted byte counts or explicit backpressure. Broadcast sends are individually bounded. Spectrum keeps only the latest unrendered frame or a small fixed ring. Queue saturation produces metrics and a visible degraded/error state; it never grows memory without limit.

### 9.5 Timeouts and retry

Connect, handshake, read-liveness, write, and shutdown deadlines are separate settings with safe defaults. Automatic retries apply to endpoint connection, not operator commands with uncertain effects. Backoff is capped and reset after a stable interval. The adapter does not add over-air ARQ retry policy; Mercury remains authoritative.

### 9.6 Transport observability

Adapters report structured state transitions, durations, byte counts, reconnect attempts, parse failures, dropped/coalesced telemetry counts, and queue high-water marks. Metrics contain endpoint profile IDs rather than secret-bearing URLs. Payload and raw control lines are excluded unless an explicit, redacted diagnostic mode is enabled.

## 10. Plugin capability

### 10.1 Goals and non-goals

Plugins may extend application-level workflows, import/export formats, notifications, visual panels, and protocols carried over approved application data ports. Plugins do not modify Mercury, load into Mercury, access radio/audio/PTT directly, or bypass application policy.

Trusted components shipped with the application may use the in-process plugin
kernel as a modularity and migration boundary. The preferred model for third-party
code remains an out-of-process plugin with a versioned, authenticated local IPC
protocol. Arbitrary in-process third-party plugins are excluded because they
collapse fault and security isolation.

### 10.2 Plugin package and manifest

A plugin package contains a signed or integrity-verifiable manifest, executable/runtime assets, and optional static UI resources. The manifest declares:

- stable plugin ID, name, version, publisher, and package digest;
- plugin API version range;
- supported OS/architectures;
- entry point without shell interpolation;
- requested capabilities and scopes;
- contributed commands, views, importers/exporters, or handlers;
- configuration schema with secret fields marked; and
- update/source metadata.

Unknown manifest fields are ignored only when safe; unknown requested capabilities reject installation or remain ungranted.

### 10.3 Capability model

Potential capabilities include:

- read normalized engine/link status;
- read coalesced telemetry;
- subscribe to session lifecycle;
- send/receive data through an application-approved logical channel;
- send/receive broadcast frames;
- contribute a constrained UI panel or commands;
- read/write plugin-scoped state;
- request file import/export through a user picker;
- issue desktop notifications; and
- request external network access to declared destinations.

Capabilities are denied by default, shown in plain language before grant, revocable, scoped, and stored in `plugin_permissions`. No capability implies arbitrary filesystem, process, database, secret, Mercury control, or network access.

### 10.4 Plugin protocol and lifecycle

The host starts a plugin with a one-time local IPC endpoint and short-lived authentication token. A handshake negotiates API versions and granted capabilities. Messages are schema-validated, length-limited, request-ID correlated, and subject to deadlines/rate limits. Heartbeats detect hangs. Crashes are isolated and restart is bounded to avoid loops.

Plugins receive normalized events rather than raw Mercury sockets. The broker removes fields outside granted scopes. Plugins cannot access core database tables; plugin state goes through quota-limited APIs. UI contributions use a constrained declarative model or sandboxed web surface selected by ADR, not arbitrary native widgets in the host process.

### 10.5 Plugin distribution and trust

The initial release may disable third-party installation while retaining the architecture. Future installation must show publisher, source, digest/signature status, permissions, and compatibility. Updates never expand permissions silently. Untrusted/unsigned plugin policy is an explicit advanced setting and should be unavailable in managed distributions if platform policy requires it.

### 10.6 Implemented plugin kernel

`src/application/plugins.py` implements API compatibility, manifests, permissions,
license requirements, dependency ordering, lifecycle state, prioritized extension
lookup, and failure containment. `src/presentation/plugin_bootstrap.py` registers
Mercury transport, themes, GPS, mapping, BBS, web, and logging as trusted built-in
adapters. Encryption is a provider slot with no implementation. Plugin state is
visible through the local web API and desktop Help menu. External discovery and
dynamic import are intentionally absent. ADR 0014 defines the migration boundary.

## 11. Security architecture

### 11.1 Security objectives

- Prevent unauthorized control of Mercury SkyPulse or its Mercury endpoint.
- Prevent accidental or malicious unsafe radio operations through the UI/plugin layer.
- Protect credentials, endpoint identity, private operational metadata, and payload confidentiality where the underlying transport supports it.
- Contain compromised plugins and malformed remote inputs.
- Produce verifiable software updates and useful, privacy-preserving audit data.

Mercury SkyPulse cannot make HF radio traffic confidential by itself. Application-layer encryption/authentication, if added, must be an explicit protocol above Mercury's byte transport and must not be implied by a WSS control connection.

### 11.2 Trust boundaries

```text
[Operator] -> [UI validation] -> [Application authorization]
                                      |
                +---------------------+------------------+
                |                     |                  |
        [Mercury adapter]      [Persistence]      [Plugin broker]
                |                     |                  |
      untrusted network bytes   local sensitive data   untrusted process
                |
        [Mercury process] -> radio hardware / RF
```

Inputs from Mercury, plugins, imported files, database recovery, command-line arguments, and remote endpoints are untrusted and validated at their boundary.

### 11.3 Network security

- Bind/listen behavior belongs to Mercury; Mercury SkyPulse is normally a client.
- Default local profiles use loopback. Remote plaintext TCP/WS profiles display a persistent warning and require explicit enablement.
- Prefer a trusted private network, OS-level tunnel/VPN, or authenticated TLS proxy for remote TNC sockets until Mercury provides native secured TNC transport.
- WSS validates hostname, certificate chain, validity, key usage, and configured trust roots. No `InsecureSkipVerify` equivalent is allowed in production defaults.
- Optional certificate pinning stores a key/certificate fingerprint with rotation workflow; first-use trust requires explicit operator confirmation.
- Never place credentials or tokens in URLs, logs, or process arguments when a safer channel exists.
- Apply input length limits before allocation and reject malformed Unicode/JSON/binary frames.

### 11.4 Command authorization and radio safety

Application commands are gated by endpoint readiness, capabilities, current normalized state, and caller (UI/plugin) authority. Plugins never receive unrestricted control commands. High-impact operations—starting an RF level test, changing radio/audio configuration, terminating an active session, or stopping a managed engine—require an explicit user action and clear consequences.

Mercury remains the final PTT safety authority. The UI treats PTT telemetry as authoritative observation and never fabricates an unkeyed state. On uncertainty, the UI shows unknown/degraded and offers a documented recovery procedure.

### 11.5 Secrets and data protection

- Use Keychain on macOS, Credential Manager/DPAPI on Windows, and Secret Service/libsecret on Linux through `SecretStorePort`.
- Database rows store opaque secret references only.
- Memory containing tokens is short-lived and excluded from crash/diagnostic output where runtime support permits.
- File permissions for database, logs, configuration, IPC endpoints, and plugin state are user-only by default.
- Diagnostic bundles are redacted, previewable, explicitly exported, and never uploaded automatically.
- Optional database encryption is a separate ADR based on threat model and credible cross-platform key management; it is not a substitute for minimizing data.

### 11.6 Plugin isolation

The host applies least privilege at both protocol and OS levels where available. IPC endpoints are user-private and authenticated. Executable paths and manifests are canonicalized to resist path traversal/symlink substitution. Plugin messages are untrusted. Quotas cover memory-inducing message sizes, request rate, state storage, restart count, and telemetry subscription rate.

OS sandboxing targets include App Sandbox-compatible mechanisms on macOS where distribution permits, AppContainer/job objects on Windows where feasible, and portals/namespaces/seccomp on Linux where packaging permits. Because mechanisms differ, protocol-level least privilege is mandatory even when OS sandboxing is unavailable.

### 11.7 Supply chain and updates

- Pin dependencies and verify checksums through the selected package system.
- Generate an SBOM for releases.
- Build in CI from reviewed source with reproducibility goals.
- Sign Windows executables/installers and macOS bundles; sign Linux repository/package metadata.
- Verify application and plugin updates before installation and support rollback to the previous application version without downgrading the database in place.
- Mercury remains separately versioned and process-isolated. Windows engineering
  packages bundle the pinned MSP-compatible runtime under ADR 0020; its integrity,
  corresponding-source URL, and GPL license notice must remain intact.

### 11.8 Logging and audit

Structured logs use severity, component, event code, correlation ID, and redaction classification. They exclude payload bytes, credentials, complete raw command streams, and private keys. Security-relevant audit events include trust changes, plugin install/grant/revoke, remote plaintext enablement, managed process launch/termination, diagnostic export, and update verification failure.

Logs are bounded by size/age, rotated safely, and deletable by the user. Audit is for troubleshooting and accountability, not surveillance.

## 12. Configuration architecture

Configuration has three layers:

1. immutable application defaults;
2. persisted user preferences and endpoint profiles; and
3. session overrides from supported command-line/deep-link inputs.

Higher layers override lower ones only for explicitly overridable fields. Configuration is parsed into typed values, validated completely, and applied atomically. Invalid settings do not partially mutate a live endpoint.

Mercury's `mercury.ini` is Mercury-owned. A managed-process profile may reference a file and structured arguments but Mercury SkyPulse does not mirror or rewrite its schema. UI conveniences for supported Mercury runtime controls call documented WebSocket/TNC commands and make persistence behavior explicit.

## 13. Error handling and resilience

Errors have a stable category, operation, user-facing impact, retryability, correlation ID, and underlying diagnostic cause. Categories include configuration, compatibility, authorization, connectivity, timeout, protocol, backpressure, persistence, process, plugin, and internal invariant.

Policies:

- Do not retry validation, authorization, or compatibility failures automatically.
- Retry transient endpoint connection failures with bounded backoff.
- Never retry a command when its effect is unknown unless it is explicitly idempotent.
- Preserve user data on database or migration failure and enter recovery mode.
- Isolate plugin crashes and optional telemetry failures from core ARQ operation.
- On sleep/resume, mark connections stale, reconnect, and fully reconcile state.
- On disk-full, stop nonessential history/log writes, preserve essential configuration consistency, and notify the operator.

## 14. Observability and diagnostics

Three levels are planned:

- **Operator health:** endpoint/link/PTT state and actionable warnings.
- **Support diagnostics:** component state, versions, capabilities, timings, counts, and sanitized recent events.
- **Developer tracing:** explicitly enabled, time-bounded detailed events without payload content.

A diagnostic snapshot should include Mercury SkyPulse version/build, OS/architecture, database schema version, endpoint capability summary, Mercury-reported version when available, plugin inventory and grants, recent state transitions, queue metrics, and redacted configuration. Export requires preview and confirmation.

No telemetry service is required. Any future opt-in remote telemetry requires a privacy ADR, minimal schema, explicit consent, deletion policy, and disabled-by-default implementation.

## 15. Performance and resource goals

Exact budgets require prototype measurement, but the design sets these constraints:

- UI input and safety controls remain responsive while spectrum is active.
- Spectrum rendering drops stale frames and uses bounded CPU/GPU work.
- All queues and caches have documented limits.
- Idle/disconnected mode performs no high-frequency polling beyond necessary liveness.
- Read-only CAT frequency telemetry reuses Mercury's Hamlib session, is cached,
  polled at a conservative interval, and is suppressed during ARQ and transmit.
- Opt-in PSK Reporter aggregation is bounded, rate-limited, and refuses stale or
  unavailable frequency telemetry; the Qt UDP/DNS adapter remains platform-facing.
- Opt-in weather access is manual, timeout-bounded, response-size-bounded, and
  never makes an IP-location request; failure cannot affect radio workflows.
- Database writes batch disposable telemetry summaries and never persist raw spectrum.
- A slow plugin cannot block transport, application state, or UI threads.
- Diagnostic logging cannot exhaust disk due to rotation/retention limits.

Performance tests should cover low-power ARM remote-host scenarios, long-running sessions, repeated reconnect, high-rate spectrum, saturated application queues, large histories, and misbehaving plugins.

## 16. Cross-platform goals

### 16.1 Initial desktop targets

The intended target set is:

- Windows 10/11 x86_64;
- macOS on Apple Silicon and Intel, subject to supported OS policy; and
- Linux x86_64 and arm64, prioritizing current Debian/Ubuntu-family desktops.

Exact minimum versions and packaging formats require ADRs and CI validation. FreeBSD and mobile are future possibilities, not initial commitments.

### 16.2 Portable core

Domain, application, Mercury codecs, persistence contracts, plugin protocol, and presentation models must be platform-neutral. Platform differences enter only through ports. Network protocols and database schemas use explicit byte order, encoding, timestamp, unit, and path-independent identifiers.

### 16.3 Platform services

| Concern | Windows | macOS | Linux |
| --- | --- | --- | --- |
| Secrets | Credential Manager/DPAPI | Keychain | Secret Service/libsecret |
| User data | Known Folder APIs | Application Support | XDG data home |
| Config | Known Folder APIs | Preferences/Application Support | XDG config home |
| Logs/cache | Local app data | Logs/Caches | XDG state/cache |
| Process | Win32 process/job APIs | POSIX/process APIs | POSIX/process APIs |
| Notifications | Windows notifications | UserNotifications | Desktop portal/freedesktop |
| Packaging | Signed installer/package | Signed/notarized app/DMG | deb/rpm/Flatpak/AppImage decision |

Paths are resolved by platform services; application code never constructs them from home-directory strings. Atomic file replacement, case sensitivity, executable suffixes, path length, Unicode normalization, and line endings are tested explicitly.

### 16.4 UI consistency and native behavior

Feature structure and terminology remain consistent, while menus, shortcuts, window behavior, file pickers, notifications, fonts, and accessibility follow platform norms. The UI must support high DPI, multiple displays, dark/light themes, localization expansion, and software rendering fallback where needed.

### 16.5 Cross-platform Mercury discovery

Mercury executable discovery is explicit-first:

1. configured path;
2. verified application-managed installation record;
3. optional PATH lookup with operator confirmation.

Discovery never searches or executes arbitrary writable directories silently. Remote Mercury operation must work even when no local Mercury executable exists.

### 16.6 Local validation

The Apple Silicon Mac-local quality gate builds and runs unit/contract tests,
validates dependencies, packages the application, and checks the bundled Mercury
runtime. Platform-specific Windows packaging and live RF behavior are validated
on controlled test stations. Routine GitHub-hosted workflows remain disabled.

## 17. Testing strategy

### 17.1 Test layers

- **Domain unit tests:** invariants and pure transformations.
- **Application tests:** commands/events using fake ports and deterministic clock.
- **Codec tests:** fragmented/coalesced input, limits, malformed data, unknown fields, endian behavior, and fuzz/property testing.
- **Mercury contract tests:** recorded non-sensitive command/status/JSON/binary fixtures tied to compatible Mercury versions.
- **Persistence tests:** repositories, constraints, migrations, corruption and disk-full simulation, retention, backup/restore.
- **Plugin contract/security tests:** handshake, permissions, schema rejection, rate/size quotas, crash/hang isolation.
- **Integration tests:** real Mercury process over loopback with safe audio backends.
- **Presentation tests:** projection rendering, accessibility semantics, state gating, and error actions.
- **End-to-end tests:** critical operator workflows and shutdown/recovery.

### 17.2 Compatibility policy

A maintained matrix identifies tested Mercury releases/commits and interface capabilities. CI tests the oldest and newest supported versions. A newly observed behavior is not silently accepted: update the contract fixture, compatibility mapping, specification/ADR if needed, and tests together.

### 17.3 Security verification

Threat modeling accompanies new trust boundaries. Automate dependency vulnerability scanning, secret scanning, static analysis, fuzzing of external codecs, package signature verification tests, permission-broker tests, and diagnostic redaction tests. Release gates include SBOM generation and artifact signing verification.

## 18. Future expansion

The design supports, but does not yet commit to:

- application-layer messaging, mail/file transfer, and store-and-forward workflows over ARQ;
- Reticulum or other broadcast consumers through approved adapters/plugins;
- multiple saved Mercury endpoints and fast profile switching;
- multiple concurrent Mercury endpoints after use cases and UI complexity justify it;
- background receive/notification mode consistent with OS policies;
- encrypted/authenticated application protocols above Mercury's byte stream;
- headless automation through a separately authenticated API;
- constrained declarative plugin panels and workflow plugins;
- richer link analytics based on minimized aggregate data;
- import/export and portable diagnostic bundles;
- localization and right-to-left UI;
- remote deployment assistance without implicit cloud dependency;
- alternative transport engines implementing the same application ports; and
- mobile companion or web clients using a purpose-built authenticated service boundary.

Expansion rules:

1. New transports implement application ports; they do not add conditions throughout domain code.
2. Multiple endpoints require instance-scoped state from the start of implementation, even if the first UI uses one active endpoint.
3. Automation and remote control require a new authentication/authorization threat model.
4. Cloud features remain optional and cannot be prerequisites for local radio operation.
5. Persisted data requires a retention, privacy, export, deletion, and migration design.
6. Plugin capabilities expand only through versioned, reviewed permissions.

## 19. Key design decisions and deferred ADRs

### Implemented messaging slice

The initial product slice implements station text chat and bounded compressed
voice-message transfer through Mercury's
documented TNC control and ARQ data sockets. `src/transport/mercury/tnc.py`
owns socket lifecycle and opaque reliable bytes; `src/application_protocol`
owns the bounded `MSP1` framing contract, feature-event demultiplexing, and
connectionless beacon codec;
`src/application/chat_service.py` owns conversation use cases and status
transitions; `src/persistence/chat_repository.py` owns the SQLite schema; and
`src/presentation/chat_page.py` renders conversations. Peer acknowledgements mean
application delivery, not human reading.

`src/application/voice_message.py` owns session capability negotiation, bitrate
and transfer gating, BUFFER-aware stop-and-wait chunk transfer, peer-confirmed
progress, checksum completion, response timeouts, and cooldown.
`src/platform_runtime/voice_audio.py` owns separate Qt Multimedia capture,
playback, voice-only microphone level, and local diagnostics. Voice recording and
review are local operations; only sending requires a compatible ARQ session.
Connectionless beacons advertise `voice-chat`, but the session event remains the
authoritative compatibility negotiation.
Presentation derives incoming, progress, verification, and delivered snapshots
from those existing protocol transitions and does not send separate notification
traffic. A voice offer waits locally for Mercury BUFFER 0, and response timeouts
run only after Mercury drains the corresponding local write. Chat text is stored
and rendered as queued while voice or file data owns the half-duplex session,
then submitted in order; disposable presence is suppressed.
Both endpoints independently qualify their received bitrate; an inbound endpoint
below threshold rejects the offer before allocating a transfer. Compressed voice
is capped at 8 KiB, and late peer results cannot rewrite terminal state.

ADR 0016 enforces the opaque transport boundary. Mercury broadcast transport owns
KISS escaping only; capability beacon meaning is an application protocol. Neutral
`ModemStatus` and `SpectrumFrame` projections live in `src/application/modem.py`,
allowing telemetry adapters to implement an inward model without making services
depend on the Mercury package.

`src/application/file_transfer.py` adds a separately validated file-transfer state
machine using bounded 4 KiB events on the same framed stream. It provides progress,
pause/resume offsets, SHA-256 verification, safe partial-file staging, and verified
duplicate detection. The initial limit is 100 MiB and only one outgoing file is
pumped at a time. ADRs 0003 and 0004 record the compatibility and security effects.

`src/platform_runtime/image_processor.py` is the image-preparation adapter. It
automatically applies orientation, bounded resizing, format-aware compression,
and a metadata-safe thumbnail before the application transfer service hashes and
sends the prepared artifact. Source images remain untouched. ADR 0005 records the
quality, format, resource, and responsiveness tradeoffs.

`src/application/location.py` owns WGS84 validation, APRS uncompressed coordinate
conversion, manual-position persistence, and the explicit sharing use case.
`src/platform_runtime/gps_receiver.py` adapts system positioning and serial NMEA
receivers. The bounded `location` event uses the existing framed Mercury stream;
the receiver cross-checks decimal and APRS coordinates. No GPS fix is shared
automatically. ADR 0006 records privacy and compatibility boundaries.

GPS history is a distinct opt-in data class in the `location_history` table. Only
local GPS fixes are eligible; manual and remotely shared positions are excluded.
`src/platform_runtime/location_exporter.py` atomically produces GPX 1.1, KML 2.2,
GeoJSON, or CSV tracks from ordered repository records. Disabling retention does
not delete prior records. ADR 0007 records privacy, lifecycle, and interoperability
tradeoffs.

`src/application/beacon.py` owns the persisted beacon profile, Maidenhead and
callsign validation, fixed selectable intervals, timer policy, capability
advertisement, and inbound validation. `src/transport/mercury/beacon.py` owns the
compact binary codec, KISS escaping/deframing, port 8100 lifecycle, and reconnect.
`src/presentation/beacon_page.py` exposes
explicit configuration, Send Now, and Turn Off actions. Beacons use the bounded
connectionless broadcast interface and remain independent of an ARQ session.
Optional GPS accepts only a GPS-source fix and carries its own timestamp.
ADR 0008 records disclosure and transport scope.

`src/application/radio.py` owns persisted station configuration.
`src/platform_runtime/hamlib_catalog.py` runs the selected
managed Mercury executable with documented `-K` and parses the exact compiled
Hamlib catalog. Managed configuration reaches Mercury only through documented
`-R/-A/-C` startup inputs; Mercury alone owns Hamlib CAT and PTT. The bounded TX
Level Test uses documented WebSocket TX gain plus real-call application beacons
and never opens CAT or generates modem samples itself. ADRs 0018, 0024, and 0025
record the single-owner and calibration boundary.

Station I/O consumes Mercury's documented WebSocket capture/playback device lists
so saved audio IDs match Mercury's backend. Qt enumerates local COM/USB serial
ports, with editable manual values for network CAT and unreported devices. CAT and
audio settings are written together to the application-owned Mercury INI and
trigger one managed-process restart; external Mercury hosts remain externally
managed.

The Audio Setup page may keep bounded spectrum parsing active while it is visible
to infer whether Mercury's RX capture stream contains energy. It presents selected
native IDs and the spectrum frame format, but does not claim a PCM peak, playback
level, host API, or negotiated hardware format that Mercury does not publish.
This read-only diagnostic path never invokes CAT, PTT, or transmission. ADR
0021 records the capability and labeling boundary.

The main window uses Chat as its central operating surface. Compact Station Status
and independent Beacon, Ping, directed Location, BBS, PSK Reporter Activity,
Radio Frequency, and Activity docks keep live functions
available without switching top-level pages. Detailed telemetry and log docks are
closed in the first-run layout but remain directly available from View and the
movable toolbar. A reusable Setup window owns Radio, Audio, User, GPS, Reporting,
and Weather configuration, with Radio first and room for future tabs.
Manual and GPS coordinates calculate a proposed Maidenhead grid locally; the
operator reviews and saves station identity, and no internet geolocation provider
is used. ADR 0019 records this UI boundary.

`src/application/ping.py` correlates one in-flight ARQ ping, freezes the local
telemetry snapshot, calculates RTT with a monotonic clock, validates the remote
snapshot, and enforces a queue-activity-aware three-minute timeout. `ping_request`
and `ping_response` are
bounded events in the existing messaging frame. The presentation receives only a
typed result. Exact Mercury modulation names are used when the public telemetry
contract supplies them; otherwise the adapter reports `ARQ` or `idle`. ADR 0009
records measurement semantics and this public-interface limitation.

CQ discovery is a separate bounded frame on the existing KISS broadcast adapter.
It carries a validated callsign/grid/version/timestamp invitation and never opens
CAT or changes VFO state. Chat expires callers after five minutes and answering
delegates to the existing ARQ connection use case. PSK Reporter continues to
consume only decoded capability beacons. ADR 0029 records this boundary and the
absence of coordinated QSY.

Weather composition is an application service backed by a platform HTTPS adapter.
The operator explicitly enables access and initiates each request. Current station
coordinates are preferred; otherwise MSP converts the saved GRID to its center
locally. A bounded wttr.in JSON response becomes editable Chat composer text;
Chat's WX action requests it asynchronously without navigating away. It is never
automatically transmitted or placed in a beacon. ADR 0030 records the privacy and
offline-operation boundary.

Operator-facing absolute timestamps use UTC consistently, including Chat and BBS
history. Application protocol timestamps were already UTC. Mercury-originated
relative timings and telemetry remain authoritative and are not rewritten by the
presentation layer.

Station Status projects only the current compact Maidenhead locator: a locator
calculated from current GPS/manual coordinates takes precedence over the saved
User Setup GRID. GPS receiver lifecycle text remains in Setup rather than resizing
the operational status grid.

`src/application/bbs.py` owns mailbox/bulletin validation, system-folder
projections, catalog advertisement/request handling, and checksum-gated file
serving. SQLite schema version 4 adds `bbs_folders`, `bbs_messages`, and
`bbs_files`. `src/presentation/bbs_page.py` renders mailbox, compose, bulletin, and
file-library workflows. File payloads reuse the verified transfer service while
catalog events use bounded ARQ messages. All identity fields are explicitly
unauthenticated in open mode. ADR 0010 records that original trust boundary.

The optional BBS security layer supersedes that boundary when enabled. Schema
version 5 adds `bbs_security` (salted scrypt verifier only) and `bbs_roles`.
A nonce/HMAC exchange authenticates each ARQ session without transmitting the
password. Centralized access checks permit users to exchange private mail and
request files, operators to also publish bulletins/files, and commanders to
administer local policy. Protected sender/owner fields must match the session
callsign. Disconnect clears authentication. The mechanism authenticates access
but does not encrypt traffic; ADR 0011 records its threat model.

`src/application/web_dashboard.py` owns bounded, framework-neutral copies of
station, chat, transfer, and activity projections. The desktop composition root
feeds it from the same typed signals used by Qt. `src/platform_runtime/local_web.py`
serves those copies on `127.0.0.1` from a worker and never accesses Qt or SQLite.
HTML and JSON views cover dashboard, messages, transfers, station status, and
logs. The interface implements GET/HEAD only, verifies loopback clients, disables
caching/CORS/framing, and stops with the desktop process. ADR 0012 makes any
future write endpoint or non-loopback exposure a new security decision.

`src/application/licensing.py` defines the signed schema, editions, feature
entitlements, organizational metadata, UTC validity rules, and verifier port.
`src/platform_runtime/licensing.py` adapts Ed25519 verification and bounded
license/key discovery. Runtime use requires no account or network. Administrators
may deploy files through environment overrides, fixed machine-wide directories,
or the per-user data directory. Invalid or expired licenses fail closed; absence
selects Community. State is visible in the desktop and local web dashboard. No
existing workflow is gated until edition policy names enforcement points. ADR
0013 excludes hardware binding and copy protection.

### 19.1 Decisions established by this specification

- Mercury is an independent process/runtime dependency.
- Integration uses documented TNC TCP and optional WebSocket interfaces.
- Architecture follows inward dependencies with ports and adapters.
- The application is local-first and usable without Mercury or internet at startup.
- Persistent state uses an embedded transactional database, with SQLite as the proposed default.
- Secrets use OS credential stores, not the database.
- Third-party plugins are out-of-process, permissioned, and denied capabilities by default.
- UI state comes from immutable application projections.
- Local managed and remote/unmanaged Mercury instances share one application port.

### 19.2 Required ADRs before implementation

1. Implementation language and supported runtime.
2. Build, dependency, formatting, linting, and test toolchain.
3. Desktop UI toolkit and accessibility strategy.
4. SQLite binding, migration mechanism, and durability settings.
5. Configuration serialization format.
6. Concurrency/state-management model.
7. Plugin IPC protocol, package format, sandboxing, and UI contribution model.
8. TLS/trust and secure remote TNC deployment guidance.
9. Target OS versions and packaging/update mechanisms.
10. Licensing and Mercury distribution model.
11. Logging library, redaction schema, and diagnostic archive format.
12. Application-layer payload protocol, only when its first use case is approved.

## 20. Acceptance criteria for the architecture phase

The architecture phase is complete when:

- stakeholders approve this specification and record unresolved technology choices as ADRs;
- the chosen source layout preserves the dependency rules;
- Mercury interfaces used by the project have executable contract fixtures;
- security review covers remote endpoints, managed process launch, database data classes, and plugins;
- cross-platform CI and packaging targets are explicit;
- the first vertical slice can be implemented without importing Mercury source or bypassing application ports; and
- documentation, contribution guidance, and roadmap agree on the implementation sequence.

Until those criteria and the relevant Phase 1 ADRs are satisfied, this repository should remain free of application logic and framework dependencies.

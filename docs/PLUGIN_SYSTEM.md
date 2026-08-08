# MercurySkyPulse plugin system

## Current scope

The plugin kernel is an internal modularity boundary for trusted built-ins. It is
not a third-party Python loader. Current built-ins register existing objects so
the application can migrate incrementally without changing Mercury or disrupting
working station features.

Registered providers:

| Plugin | Extension point | Permission |
|---|---|---|
| `core.mercury` | `transport` (opaque bytes and modem facts) | `mercury.transport` |
| `core.themes` | `theme` | `ui.theme` |
| `core.gps` | `position-source` | `location.read` |
| `core.mapping` | `map-provider` | `filesystem.export` |
| `core.bbs` | `bbs` | `application.bbs` |
| `core.web` | `web-interface` | `local.http` |
| `core.logging` | `logging` | `logging.write` |

`encryption-provider` exists but has no provider. No UI or protocol may claim
encryption merely because the extension point exists.

Transport plugins must not export collaboration services or interpret application
event names. Protocol plugins may layer framing, compression, chunking,
authentication, or encryption over a transport export. Feature plugins consume
those application-protocol ports rather than Mercury-specific classes.

## Manifest contract

Every plugin declares a stable reverse-domain-style ID, display name, semantic
version, publisher, supported plugin API range, dependencies, requested
permissions, extension contributions, and optional licensing feature. Each
contribution names an extension point, an exported object, and a priority.

Dependencies form an acyclic graph. Providers start after dependencies and stop
in reverse order. Higher-priority providers sort first, with plugin ID as a
deterministic tie-breaker. Startup exceptions mark one plugin failed; dependents
become blocked while unrelated plugins continue.

Permissions are denied by default for non-built-ins. `PluginContext` exposes only
granted permission names and declared dependency exports. These checks support
correct application design but do not sandbox in-process Python.

## Migration path

1. Register an existing component as a built-in adapter.
2. Replace direct consumer construction with extension-point resolution.
3. Move creation, configuration, and lifecycle into the plugin factory.
4. Add contract tests for alternate providers.
5. Keep domain models and application ports independent of any provider.

Third-party support requires signed/integrity-checked packages, an out-of-process
broker, capability-scoped IPC, bounded messages, authentication, crash/restart
policy, settings isolation, and constrained UI contributions. Until that work is
complete, no filesystem discovery or dynamic import of external plugins is
allowed.

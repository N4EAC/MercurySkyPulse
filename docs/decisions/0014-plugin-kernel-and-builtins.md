# ADR 0014: Plugin kernel and built-in migration

## Status

Accepted

## Context

MercurySkyPulse needs replaceable providers for transport, presentation,
positioning, mapping, BBS, web, logging, and future encryption. Rewriting all
working components at once would introduce unnecessary operational risk.

## Decision

The application layer owns a framework-neutral plugin kernel with versioned API
compatibility, immutable manifests, extension contributions, explicit permission
grants, license feature requirements, dependencies, deterministic startup,
reverse shutdown, prioritized provider lookup, state reporting, and exception
containment. Missing permissions and license features disable a plugin; failed
dependencies block dependents without stopping independent providers.

Existing components are registered as trusted built-in object adapters at the
desktop composition boundary. The first built-ins are Mercury transport, GUI
themes, GPS, mapping export, BBS, local web, and logging. Encryption is an empty
extension point and does not imply encryption is available.

The in-process registry is for trusted built-ins only. It is not a security
sandbox: Python code can ignore application permission APIs. Third-party package
discovery and execution remain disabled until the out-of-process authenticated
broker, package verification, user permission workflow, and constrained UI
contribution model described in the architecture are implemented.

## Consequences

The shell can migrate components incrementally and consumers can select providers
by extension point rather than concrete package. Existing lifecycle ownership is
temporarily preserved by no-op object adapters. Later milestones move creation
and lifecycle into individual plugin factories. External plugin installation is
not yet supported, and users must not be told that arbitrary Python modules are
safe to load.

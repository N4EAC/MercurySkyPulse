# ADR 0001: Python and PySide6 for the GUI skeleton

Status: Accepted for the GUI skeleton

## Context

Mercury SkyPulse needs a cross-platform desktop shell with native macOS and Windows behavior, runtime dark/light themes, scalable controls, docking, resizing, menus, and a status bar. The current task explicitly excludes modem, networking, and database behavior.

## Decision

Use Python 3.11 or newer with PySide6 (Qt 6) for the first desktop GUI skeleton.

The presentation package contains widgets and visual state only. The executable composition root imports that package. No Mercury, network, persistence, or platform integration is introduced.

## Consequences

- Qt supplies mature dock widgets, high-DPI scaling, native platform styles, accessibility primitives, menus, shortcuts, and status bars.
- PySide6 is a runtime dependency and must be installed before launching the shell.
- Native appearance varies by operating system; explicit macOS and Windows presets approximate the alternate platform when previewed elsewhere.
- This decision establishes the initial language and UI toolkit, but not the future domain, transport, or persistence implementation.


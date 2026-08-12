# ADR 0027: License MercurySkyPulse under GPL-3.0-or-later

## Status

Accepted

## Context

MercurySkyPulse is intended to be open-source software that anyone may use,
study, copy, modify, redistribute, and improve. The project owner also wants
distributed derivatives to preserve those freedoms. Mercury is separately
versioned and process-isolated, but the engineering packages include a GPL
Mercury runtime with its own license and corresponding-source notice.

## Decision

License MercurySkyPulse under the GNU General Public License, version 3 or any
later version (`GPL-3.0-or-later`). The repository carries the complete GPLv3
text in `LICENSE`, declares the SPDX expression in package metadata, and states
the license in operator and contributor documentation.

Copyright notices identify Eduardo A. de Carvalho and MercurySkyPulse
contributors. Contributions are accepted for distribution under the same
project license.

Platform support is described independently from licensing. Windows 10/11
x86-64 and Apple Silicon macOS are the current engineering-test platforms.
Fedora and Ubuntu binary packaging is planned but is not yet represented as
available or validated.

## Consequences

- Commercial use and sale are permitted.
- Anyone distributing MSP or a derivative must comply with GPL requirements,
  including preserving the license and providing corresponding source.
- Distributed derivatives cannot remove recipients' GPL freedoms.
- Mercury remains a separately maintained executable with its own GPL license,
  source provenance, and runtime notice.
- A future incompatible relicensing decision would require review of copyright
  ownership and contributor permissions.

"""Validate that a packaged MSP directory contains voice-audio runtime pieces."""

from __future__ import annotations

import argparse
from pathlib import Path


def validate(root: Path) -> list[str]:
    errors = []
    if not root.is_dir():
        return [f"package directory does not exist: {root}"]
    names = {path.name.casefold() for path in root.rglob("*") if path.is_file()}
    if not any(name.startswith("qtmultimedia") for name in names):
        errors.append("PySide6 QtMultimedia binding/library is missing")
    if not any("mediaplugin" in name for name in names):
        errors.append("Qt Multimedia native backend plugin is missing")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("package", type=Path)
    args = parser.parse_args()
    errors = validate(args.package)
    for error in errors:
        print(f"ERROR: {error}")
    if errors:
        return 1
    print(f"Voice audio runtime verified: {args.package}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Validate packaged MSP voice recording and playback runtime pieces."""

from __future__ import annotations

import argparse
from pathlib import Path

from application.voice_message import (
    MERCURY_QUEUE_LOW_WATER_BYTES,
    VOICE_CHUNK_BYTES,
)
from application_protocol.messaging import FrameDecoder, encode_event


def validate(root: Path) -> list[str]:
    errors = []
    if not root.is_dir():
        return [f"package directory does not exist: {root}"]
    names = {path.name.casefold() for path in root.rglob("*") if path.is_file()}
    if not any(name.startswith("qtmultimedia") for name in names):
        errors.append("PySide6 QtMultimedia recording/playback library is missing")
    if not any("mediaplugin" in name for name in names):
        errors.append("Qt Multimedia native recording/playback backend is missing")
    if VOICE_CHUNK_BYTES != 384:
        errors.append("voice protocol 2 must use 384-byte stop-and-wait chunks")
    if MERCURY_QUEUE_LOW_WATER_BYTES != 256:
        errors.append("voice protocol 2 must wait for Mercury BUFFER <= 256")
    try:
        frame = encode_event(
            "voice_chunk_ack", "package-check", "2026-01-01T00:00:00+00:00",
            offset=384,
        )
        decoded = FrameDecoder().feed(frame)
        if len(decoded) != 1 or decoded[0].kind != "voice_chunk_ack":
            errors.append("voice protocol 2 chunk acknowledgement is unavailable")
    except (TypeError, ValueError):
        errors.append("voice protocol 2 chunk acknowledgement is unavailable")
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
    print(
        "Voice recording/playback runtime and BUFFER-aware protocol 2 verified: "
        f"{args.package}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

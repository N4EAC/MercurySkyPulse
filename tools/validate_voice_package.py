"""Validate packaged MSP voice recording and playback runtime pieces."""

from __future__ import annotations

import argparse
from pathlib import Path

from application.voice_message import (
    MAX_VOICE_BYTES,
    MERCURY_QUEUE_LOW_WATER_BYTES,
    VOICE_RESPONSE_TIMEOUT_MS,
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
    if not any(name.startswith(("av.", "avcodec", "libavcodec")) for name in names):
        errors.append("PyAV/FFmpeg voice compression runtime is missing")
    if "pyav_license.txt" not in names:
        errors.append("PyAV redistribution license is missing")
    if "third_party_notices.md" not in names:
        errors.append("third-party notices are missing")
    if VOICE_CHUNK_BYTES != 384:
        errors.append("voice protocol 2 must use 384-byte stop-and-wait chunks")
    if MERCURY_QUEUE_LOW_WATER_BYTES != 256:
        errors.append("voice protocol 2 must wait for Mercury BUFFER <= 256")
    if MAX_VOICE_BYTES != 8 * 1024:
        errors.append("voice protocol 2 must enforce the RF-safe 8-KiB ceiling")
    if VOICE_RESPONSE_TIMEOUT_MS != 180_000:
        errors.append("voice protocol 2 must use the drain-aware 180-second timeout")
    try:
        capability = encode_event(
            "voice_capability", "package-capability", "2026-01-01T00:00:00+00:00",
            protocol=2, mime_types=["audio/mp4"], maximum_seconds=10,
            maximum_bytes=MAX_VOICE_BYTES, link_ready=True, bitrate_bps=600,
            ack=True,
        )
        decoded_capability = FrameDecoder().feed(capability)
        if (
            len(decoded_capability) != 1
            or decoded_capability[0].kind != "voice_capability"
            or not decoded_capability[0].values.get("link_ready")
        ):
            errors.append("voice protocol 2 bilateral bitrate readiness is unavailable")
        frame = encode_event(
            "voice_chunk_ack", "package-check", "2026-01-01T00:00:00+00:00",
            offset=384,
        )
        decoded = FrameDecoder().feed(frame)
        if len(decoded) != 1 or decoded[0].kind != "voice_chunk_ack":
            errors.append("voice protocol 2 chunk acknowledgement is unavailable")
    except (TypeError, ValueError):
        errors.append("voice protocol 2 capability or chunk acknowledgement is unavailable")
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
        "Bounded Opus voice runtime and bilateral-bitrate-gated BUFFER-aware protocol 2 verified: "
        f"{args.package}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

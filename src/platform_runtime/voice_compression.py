"""Deterministic narrowband compression for bounded RF voice messages."""

from __future__ import annotations

from pathlib import Path

import av


MAX_VOICE_BYTES = 8 * 1024
VOICE_SAMPLE_RATE = 8_000
MAX_VOICE_SAMPLES = 10 * VOICE_SAMPLE_RATE
_BITRATE_ATTEMPTS = (5_200, 4_800, 4_000)


def compress_voice_recording(source_value: str) -> tuple[str, str]:
    """Create a complete, playable 10-second-or-shorter Opus file under 8 KiB."""
    source = Path(source_value)
    if not source.is_file() or source.stat().st_size < 1:
        raise ValueError("Voice recording is empty")

    destination = source.with_suffix(".voice.ogg")
    temporary = destination.with_suffix(".ogg.part")
    try:
        for bitrate in _BITRATE_ATTEMPTS:
            temporary.unlink(missing_ok=True)
            _encode_opus(source, temporary, bitrate)
            size = temporary.stat().st_size
            if 0 < size <= MAX_VOICE_BYTES:
                temporary.replace(destination)
                if source != destination:
                    source.unlink(missing_ok=True)
                return str(destination), "audio/ogg"
        raise ValueError(
            "Compressed voice recording exceeds the 8 KiB RF safety limit"
        )
    except Exception as error:
        temporary.unlink(missing_ok=True)
        destination.unlink(missing_ok=True)
        if isinstance(error, ValueError):
            raise
        raise RuntimeError(f"Could not encode narrowband Opus audio: {error}") from error


def _encode_opus(source: Path, destination: Path, bitrate: int) -> None:
    input_container = av.open(str(source))
    output_container = av.open(str(destination), mode="w", format="ogg")
    try:
        stream = output_container.add_stream("libopus", rate=VOICE_SAMPLE_RATE)
        stream.layout = "mono"
        stream.bit_rate = bitrate
        stream.codec_context.options = {
            "application": "voip",
            "frame_duration": "60",
            "vbr": "off",
        }
        resampler = av.audio.resampler.AudioResampler(
            format="s16", layout="mono", rate=VOICE_SAMPLE_RATE
        )
        written = 0
        for decoded in input_container.decode(audio=0):
            for frame in resampler.resample(decoded):
                written += _encode_bounded_frame(
                    output_container, stream, frame, MAX_VOICE_SAMPLES - written
                )
                if written >= MAX_VOICE_SAMPLES:
                    break
            if written >= MAX_VOICE_SAMPLES:
                break
        if written < MAX_VOICE_SAMPLES:
            for frame in resampler.resample(None):
                written += _encode_bounded_frame(
                    output_container, stream, frame, MAX_VOICE_SAMPLES - written
                )
                if written >= MAX_VOICE_SAMPLES:
                    break
        if written < 1:
            raise ValueError("Voice recording contains no decodable audio")
        for packet in stream.encode():
            output_container.mux(packet)
    finally:
        input_container.close()
        output_container.close()


def _encode_bounded_frame(container, stream, frame, remaining: int) -> int:
    if remaining <= 0:
        return 0
    samples = min(frame.samples, remaining)
    if samples == frame.samples:
        bounded = frame
    else:
        bounded = av.AudioFrame(format="s16", layout="mono", samples=samples)
        bounded.sample_rate = VOICE_SAMPLE_RATE
        bounded.planes[0].update(bytes(frame.planes[0])[: samples * 2])
    for packet in stream.encode(bounded):
        container.mux(packet)
    return samples

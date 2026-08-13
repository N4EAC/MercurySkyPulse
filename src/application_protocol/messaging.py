"""MercurySkyPulse application framing over an opaque reliable byte stream."""

from __future__ import annotations

from dataclasses import dataclass
import json
import struct


MAGIC = b"MSP1"
HEADER = struct.Struct(">4sI")
MAX_PAYLOAD = 8192
MAX_TEXT_CHARS = 2048


@dataclass(frozen=True, slots=True)
class ChatEnvelope:
    kind: str
    message_id: str
    timestamp: str
    text: str = ""
    values: dict[str, object] | None = None


def _frame(payload: dict[str, object]) -> bytes:
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_PAYLOAD:
        raise ValueError("chat frame is too large")
    return HEADER.pack(MAGIC, len(encoded)) + encoded


def encode_message(message_id: str, timestamp: str, text: str) -> bytes:
    clean = text.strip()
    if not clean or len(clean) > MAX_TEXT_CHARS:
        raise ValueError("message text must contain 1..2048 characters")
    return _frame({"v": 1, "type": "message", "id": message_id, "at": timestamp, "text": clean})


def encode_ack(message_id: str, timestamp: str) -> bytes:
    return _frame({"v": 1, "type": "ack", "id": message_id, "at": timestamp})


def encode_event(kind: str, event_id: str, timestamp: str, **values: object) -> bytes:
    allowed = {
        "file_offer", "file_accept", "file_chunk", "file_pause", "file_resume",
        "file_complete", "file_result", "location", "ping_request", "ping_response",
        "bbs_private", "bbs_bulletin", "bbs_file_announce", "bbs_file_request",
        "bbs_auth_begin", "bbs_auth_challenge", "bbs_auth_proof",
        "bbs_auth_result", "bbs_access_denied",
        "presence",
        "voice_capability", "voice_offer", "voice_accept", "voice_chunk",
        "voice_complete", "voice_result",
    }
    if kind not in allowed:
        raise ValueError("unsupported messaging event")
    return _frame({"v": 1, "type": kind, "id": event_id, "at": timestamp, **values})


class FrameDecoder:
    def __init__(self) -> None:
        self._buffer = bytearray()

    def feed(self, data: bytes) -> list[ChatEnvelope]:
        self._buffer.extend(data)
        frames: list[ChatEnvelope] = []
        while True:
            if len(self._buffer) < HEADER.size:
                break
            if self._buffer[:4] != MAGIC:
                offset = self._buffer.find(MAGIC, 1)
                if offset < 0:
                    del self._buffer[:-3]
                    break
                del self._buffer[:offset]
                continue
            _, length = HEADER.unpack_from(self._buffer)
            if length == 0 or length > MAX_PAYLOAD:
                del self._buffer[:4]
                continue
            total = HEADER.size + length
            if len(self._buffer) < total:
                break
            payload = bytes(self._buffer[HEADER.size:total])
            del self._buffer[:total]
            envelope = self._decode(payload)
            if envelope:
                frames.append(envelope)
        return frames

    @staticmethod
    def _decode(payload: bytes) -> ChatEnvelope | None:
        try:
            raw = json.loads(payload)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None
        if not isinstance(raw, dict) or raw.get("v") != 1:
            return None
        kind = raw.get("type")
        message_id = raw.get("id")
        timestamp = raw.get("at")
        allowed = {
            "message", "ack", "file_offer", "file_accept", "file_chunk",
            "file_pause", "file_resume", "file_complete", "file_result",
            "location", "ping_request", "ping_response",
            "bbs_private", "bbs_bulletin", "bbs_file_announce", "bbs_file_request",
            "bbs_auth_begin", "bbs_auth_challenge", "bbs_auth_proof",
            "bbs_auth_result", "bbs_access_denied",
            "presence",
            "voice_capability", "voice_offer", "voice_accept", "voice_chunk",
            "voice_complete", "voice_result",
        }
        if kind not in allowed or not isinstance(message_id, str) or not isinstance(timestamp, str):
            return None
        text = raw.get("text", "")
        if kind == "message" and (not isinstance(text, str) or not text or len(text) > MAX_TEXT_CHARS):
            return None
        values = {key: value for key, value in raw.items() if key not in {"v", "type", "id", "at", "text"}}
        return ChatEnvelope(
            kind=kind,
            message_id=message_id[:64],
            timestamp=timestamp[:40],
            text=text,
            values=values,
        )

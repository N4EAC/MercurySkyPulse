"""Text-chat application models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class MessageDirection(StrEnum):
    OUTGOING = "outgoing"
    INCOMING = "incoming"


class MessageStatus(StrEnum):
    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    RECEIVED = "received"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class Conversation:
    id: int
    local_call: str
    remote_call: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class ChatMessage:
    id: str
    conversation_id: int
    direction: MessageDirection
    body: str
    sent_at: str
    status: MessageStatus


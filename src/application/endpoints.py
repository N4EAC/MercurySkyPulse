"""Framework-neutral Mercury endpoint profiles and safety policy."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import ipaddress
from pathlib import Path


class MercuryRunMode(StrEnum):
    MANAGED_LOCAL = "managed-local"
    UNMANAGED_LOCAL = "unmanaged-local"
    REMOTE = "remote"


@dataclass(frozen=True, slots=True)
class TcpEndpoint:
    host: str
    port: int

    def __post_init__(self) -> None:
        host = self.host.strip()
        if not host or any(character.isspace() for character in host):
            raise ValueError("Endpoint host must be a non-empty host name or address")
        if not 1 <= self.port <= 65535:
            raise ValueError("Endpoint port must be between 1 and 65535")
        object.__setattr__(self, "host", host)

    @property
    def is_loopback(self) -> bool:
        lowered = self.host.rstrip(".").lower()
        if lowered == "localhost" or lowered.endswith(".localhost"):
            return True
        try:
            return ipaddress.ip_address(lowered).is_loopback
        except ValueError:
            return False

    @property
    def is_unsafe_address(self) -> bool:
        try:
            address = ipaddress.ip_address(self.host.rstrip("."))
        except ValueError:
            return False
        return address.is_unspecified or address.is_multicast


@dataclass(frozen=True, slots=True)
class WebSocketEndpoint:
    host: str
    port: int
    path: str = "/websocket"
    secure: bool = False

    def __post_init__(self) -> None:
        endpoint = TcpEndpoint(self.host, self.port)
        path = self.path.strip()
        if not path.startswith("/") or "#" in path or "?" in path:
            raise ValueError("WebSocket path must be an absolute path without query or fragment")
        object.__setattr__(self, "host", endpoint.host)
        object.__setattr__(self, "path", path)

    @property
    def is_loopback(self) -> bool:
        return TcpEndpoint(self.host, self.port).is_loopback

    @property
    def is_unsafe_address(self) -> bool:
        return TcpEndpoint(self.host, self.port).is_unsafe_address

    @property
    def url(self) -> str:
        scheme = "wss" if self.secure else "ws"
        host = f"[{self.host}]" if ":" in self.host and not self.host.startswith("[") else self.host
        return f"{scheme}://{host}:{self.port}{self.path}"


@dataclass(frozen=True, slots=True)
class ReconnectPolicy:
    socket_delay_ms: int = 1000
    initial_delay_ms: int = 500
    maximum_delay_ms: int = 8000
    multiplier: float = 2.0

    def __post_init__(self) -> None:
        if not 100 <= self.socket_delay_ms <= 5 * 60 * 1000:
            raise ValueError("Socket reconnect delay must be between 100 ms and 5 minutes")
        if self.initial_delay_ms < 100:
            raise ValueError("Reconnect initial delay must be at least 100 ms")
        if self.maximum_delay_ms < self.initial_delay_ms:
            raise ValueError("Reconnect maximum delay cannot be below its initial delay")
        if not 1.0 <= self.multiplier <= 10.0:
            raise ValueError("Reconnect multiplier must be between 1 and 10")

    def delay_ms(self, attempt: int) -> int:
        if attempt < 0:
            raise ValueError("Reconnect attempt cannot be negative")
        return min(
            self.maximum_delay_ms,
            int(self.initial_delay_ms * (self.multiplier ** min(attempt, 32))),
        )


@dataclass(frozen=True, slots=True)
class TransportLimits:
    control_line_bytes: int = 4096
    kiss_frame_bytes: int = 4096
    kiss_buffer_bytes: int = 8192

    def __post_init__(self) -> None:
        if not 256 <= self.control_line_bytes <= 64 * 1024:
            raise ValueError("TNC control-line limit must be between 256 bytes and 64 KiB")
        if not 256 <= self.kiss_frame_bytes <= 64 * 1024:
            raise ValueError("KISS frame limit must be between 256 bytes and 64 KiB")
        if not self.kiss_frame_bytes + 2 <= self.kiss_buffer_bytes <= 128 * 1024:
            raise ValueError("KISS buffer limit must exceed one frame and be at most 128 KiB")


@dataclass(frozen=True, slots=True)
class MercuryEndpointProfile:
    mode: MercuryRunMode = MercuryRunMode.MANAGED_LOCAL
    executable: Path | None = None
    control: TcpEndpoint = field(default_factory=lambda: TcpEndpoint("127.0.0.1", 8300))
    data: TcpEndpoint = field(default_factory=lambda: TcpEndpoint("127.0.0.1", 8301))
    broadcast: TcpEndpoint = field(default_factory=lambda: TcpEndpoint("127.0.0.1", 8100))
    telemetry: WebSocketEndpoint = field(
        default_factory=lambda: WebSocketEndpoint("127.0.0.1", 10000)
    )
    reconnect: ReconnectPolicy = field(default_factory=ReconnectPolicy)
    limits: TransportLimits = field(default_factory=TransportLimits)
    allow_insecure_remote: bool = False

    def __post_init__(self) -> None:
        try:
            mode = MercuryRunMode(self.mode)
        except ValueError as error:
            raise ValueError("Unknown Mercury run mode") from error
        object.__setattr__(self, "mode", mode)
        endpoints = (self.control, self.data, self.broadcast, self.telemetry)
        if any(endpoint.is_unsafe_address for endpoint in endpoints):
            raise ValueError("Unspecified and multicast Mercury endpoints are not allowed")
        if mode in {MercuryRunMode.MANAGED_LOCAL, MercuryRunMode.UNMANAGED_LOCAL}:
            if not all(endpoint.is_loopback for endpoint in endpoints):
                raise ValueError("Local Mercury profiles require loopback-only endpoints")
        if mode is MercuryRunMode.MANAGED_LOCAL:
            return
        if self.executable is not None:
            raise ValueError("Only managed-local profiles may select a Mercury executable")
        if mode is MercuryRunMode.REMOTE:
            if any(endpoint.is_loopback for endpoint in endpoints):
                raise ValueError("Remote Mercury profiles cannot mix loopback endpoints")
            if not self.allow_insecure_remote:
                raise ValueError(
                    "Remote Mercury requires explicit acceptance of unauthenticated TNC/KISS transport risk"
                )

    @classmethod
    def default(cls) -> "MercuryEndpointProfile":
        """Preserve the original supervised-loopback endpoint behavior."""
        return cls()

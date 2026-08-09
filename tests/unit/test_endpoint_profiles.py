"""Mercury endpoint profile validation and default-compatibility tests."""

from __future__ import annotations

from pathlib import Path
import unittest

from application.endpoints import (
    MercuryEndpointProfile,
    MercuryRunMode,
    ReconnectPolicy,
    TcpEndpoint,
    WebSocketEndpoint,
)


class EndpointProfileTests(unittest.TestCase):
    def test_default_preserves_supervised_loopback_endpoints(self) -> None:
        profile = MercuryEndpointProfile.default()
        self.assertEqual(profile.mode, MercuryRunMode.MANAGED_LOCAL)
        self.assertEqual((profile.control.host, profile.control.port), ("127.0.0.1", 8300))
        self.assertEqual((profile.data.host, profile.data.port), ("127.0.0.1", 8301))
        self.assertEqual((profile.broadcast.host, profile.broadcast.port), ("127.0.0.1", 8100))
        self.assertEqual(profile.telemetry.url, "ws://127.0.0.1:10000/websocket")
        self.assertEqual(profile.reconnect.socket_delay_ms, 1000)
        self.assertEqual(profile.reconnect.delay_ms(0), 500)
        self.assertEqual(profile.reconnect.delay_ms(9), 8000)

    def test_managed_local_allows_explicit_executable(self) -> None:
        profile = MercuryEndpointProfile(executable=Path("/opt/mercury"))
        self.assertEqual(profile.executable, Path("/opt/mercury"))

    def test_unmanaged_local_rejects_executable_and_remote_endpoint(self) -> None:
        with self.assertRaisesRegex(ValueError, "Only managed-local"):
            MercuryEndpointProfile(
                mode=MercuryRunMode.UNMANAGED_LOCAL,
                executable=Path("/opt/mercury"),
            )
        with self.assertRaisesRegex(ValueError, "loopback-only"):
            MercuryEndpointProfile(
                mode=MercuryRunMode.UNMANAGED_LOCAL,
                control=TcpEndpoint("radio.example", 8300),
            )

    def test_remote_requires_explicit_risk_acceptance(self) -> None:
        values = dict(
            mode=MercuryRunMode.REMOTE,
            control=TcpEndpoint("radio.example", 8300),
            data=TcpEndpoint("radio.example", 8301),
            broadcast=TcpEndpoint("radio.example", 8100),
            telemetry=WebSocketEndpoint("radio.example", 10000, secure=True),
        )
        with self.assertRaisesRegex(ValueError, "explicit acceptance"):
            MercuryEndpointProfile(**values)
        profile = MercuryEndpointProfile(**values, allow_insecure_remote=True)
        self.assertEqual(profile.mode, MercuryRunMode.REMOTE)
        self.assertEqual(profile.telemetry.url, "wss://radio.example:10000/websocket")

    def test_string_mode_is_normalized_before_safety_validation(self) -> None:
        with self.assertRaisesRegex(ValueError, "explicit acceptance"):
            MercuryEndpointProfile(
                mode="remote",
                control=TcpEndpoint("radio.example", 8300),
                data=TcpEndpoint("radio.example", 8301),
                broadcast=TcpEndpoint("radio.example", 8100),
                telemetry=WebSocketEndpoint("radio.example", 10000),
            )

    def test_remote_rejects_mixed_loopback_and_unsafe_addresses(self) -> None:
        remote = dict(
            mode=MercuryRunMode.REMOTE,
            data=TcpEndpoint("radio.example", 8301),
            broadcast=TcpEndpoint("radio.example", 8100),
            telemetry=WebSocketEndpoint("radio.example", 10000),
            allow_insecure_remote=True,
        )
        with self.assertRaisesRegex(ValueError, "cannot mix loopback"):
            MercuryEndpointProfile(**remote)
        with self.assertRaisesRegex(ValueError, "Unspecified"):
            MercuryEndpointProfile(**remote, control=TcpEndpoint("0.0.0.0", 8300))

    def test_reconnect_policy_is_bounded(self) -> None:
        policy = ReconnectPolicy(750, 250, 1000, 3.0)
        self.assertEqual([policy.delay_ms(index) for index in range(4)],
                         [250, 750, 1000, 1000])


if __name__ == "__main__":
    unittest.main()

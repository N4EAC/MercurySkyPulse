"""Contract tests for Mercury's documented status and spectrum frames."""

from __future__ import annotations

import json
import math
import struct
import unittest

from transport.mercury.telemetry.protocol import (
    SPECTRUM_MAGIC,
    parse_spectrum_frame,
    parse_status_message,
)


class MercuryTelemetryContractTests(unittest.TestCase):
    def test_parses_status_snapshot(self) -> None:
        payload = json.dumps(
            {
                "type": "status",
                "bitrate": 1200,
                "snr": 6.5,
                "sync": True,
                "direction": "tx",
                "user_callsign": "N0CALL",
                "dest_callsign": "K1TEST",
                "client_tcp_connected": False,
                "bytes_transmitted": 34,
                "bytes_received": 900,
                "waterfall": True,
                "modem_mode": "DATAC3",
            }
        )
        status = parse_status_message(payload)
        self.assertIsNotNone(status)
        self.assertEqual(1200, status.bitrate_bps)
        self.assertEqual(6.5, status.snr_db)
        self.assertEqual("DATAC3", status.modem_mode)
        self.assertTrue(status.sync)
        self.assertEqual("tx", status.direction)

    def test_parses_little_endian_spectrum(self) -> None:
        bins = (-100.0, -75.5, -30.0, 1.25)
        payload = struct.pack("<IHH4f", SPECTRUM_MAGIC, len(bins), 8000, *bins)
        frame = parse_spectrum_frame(payload)
        self.assertIsNotNone(frame)
        self.assertEqual(8000, frame.sample_rate_hz)
        self.assertEqual(bins, frame.bins_db)

    def test_rejects_malformed_external_payloads(self) -> None:
        self.assertIsNone(parse_status_message("not json"))
        self.assertIsNone(parse_status_message('{"type":"other"}'))
        self.assertIsNone(parse_spectrum_frame(b"short"))
        bad_magic = struct.pack("<IHHf", 0, 1, 8000, -10.0)
        self.assertIsNone(parse_spectrum_frame(bad_magic))
        non_finite = struct.pack("<IHHf", SPECTRUM_MAGIC, 1, 8000, math.nan)
        self.assertIsNone(parse_spectrum_frame(non_finite))

    def test_status_values_are_sanitized_and_bounded(self) -> None:
        status = parse_status_message(json.dumps({
            "type": "status", "bitrate": -100, "snr": "nan",
            "direction": "sideways", "bytes_transmitted": -1,
            "bytes_received": "invalid", "user_callsign": "X" * 100,
            "dest_callsign": "Y" * 100, "mode": "M" * 100,
        }))
        self.assertEqual(status.bitrate_bps, 0)
        self.assertEqual(status.snr_db, 0.0)
        self.assertEqual(status.direction, "rx")
        self.assertEqual(status.bytes_transmitted, 0)
        self.assertEqual(status.bytes_received, 0)
        self.assertEqual(len(status.user_callsign), 16)
        self.assertEqual(len(status.destination_callsign), 16)
        self.assertEqual(len(status.modem_mode), 32)

    def test_spectrum_contract_rejects_length_and_fft_limit_violations(self) -> None:
        truncated = struct.pack("<IHHf", SPECTRUM_MAGIC, 2, 8000, -50.0)
        self.assertIsNone(parse_spectrum_frame(truncated))
        oversized = struct.pack("<IHH", SPECTRUM_MAGIC, 4097, 8000)
        self.assertIsNone(parse_spectrum_frame(oversized))
        no_sample_rate = struct.pack("<IHHf", SPECTRUM_MAGIC, 1, 0, -50.0)
        self.assertIsNone(parse_spectrum_frame(no_sample_rate))


if __name__ == "__main__":
    unittest.main()

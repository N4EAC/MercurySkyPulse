"""Contract tests for Mercury's documented status and spectrum frames."""

from __future__ import annotations

import json
import math
import struct
import unittest

from PySide6.QtNetwork import QAbstractSocket

from transport.mercury.telemetry.protocol import (
    SPECTRUM_MAGIC,
    parse_device_list_message,
    parse_spectrum_frame,
    parse_status_message,
)
from transport.mercury.telemetry.client import MercuryTelemetryClient


class MercuryTelemetryContractTests(unittest.TestCase):
    def test_documented_tx_gain_command_is_bounded_json(self) -> None:
        class FakeSocket:
            def __init__(self):
                self.sent = []

            def state(self):
                return QAbstractSocket.SocketState.ConnectedState

            def sendTextMessage(self, payload):
                self.sent.append(payload)
                return len(payload)

        client = MercuryTelemetryClient()
        fake = FakeSocket()
        client.socket = fake
        client.set_tx_gain_db(-12.5)
        self.assertEqual(
            json.loads(fake.sent[0]),
            {"command": "set_tx_gain", "value": "-12.50"},
        )
        with self.assertRaises(ValueError):
            client.set_tx_gain_db(20.1)

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
                "tx_gain_db": -8.5,
                "tx_peak_dbfs": -2.25,
                "radio_frequency_hz": 14_105_000,
                "radio_frequency_age_ms": 750,
            }
        )
        status = parse_status_message(payload)
        self.assertIsNotNone(status)
        self.assertEqual(1200, status.bitrate_bps)
        self.assertEqual(6.5, status.snr_db)
        self.assertEqual("DATAC3", status.modem_mode)
        self.assertTrue(status.sync)
        self.assertEqual("tx", status.direction)
        self.assertEqual(-8.5, status.tx_gain_db)
        self.assertEqual(-2.25, status.tx_peak_dbfs)
        self.assertEqual(14_105_000, status.radio_frequency_hz)
        self.assertEqual(750, status.radio_frequency_age_ms)

    def test_parses_little_endian_spectrum(self) -> None:
        bins = (-100.0, -75.5, -30.0, 1.25)
        payload = struct.pack("<IHH4f", SPECTRUM_MAGIC, len(bins), 8000, *bins)
        frame = parse_spectrum_frame(payload)
        self.assertIsNotNone(frame)
        self.assertEqual(8000, frame.sample_rate_hz)
        self.assertEqual(bins, frame.bins_db)

    def test_client_skips_spectrum_parsing_until_visualization_is_enabled(self) -> None:
        bins = (-100.0, -75.5)
        payload = struct.pack("<IHH2f", SPECTRUM_MAGIC, len(bins), 8000, *bins)
        client = MercuryTelemetryClient()
        received = []
        client.spectrum_received.connect(received.append)
        client._on_binary(payload)
        self.assertEqual(received, [])
        client.set_spectrum_processing_enabled(True)
        client._on_binary(payload)
        self.assertEqual(received[0].bins_db, bins)

    def test_parses_bounded_mercury_audio_device_lists(self) -> None:
        parsed = parse_device_list_message(json.dumps({
            "type": "capture_dev_list",
            "selected": "capture:2",
            "list": [
                {"name": "USB Audio CODEC", "id": "capture:2"},
                {"name": "Built-in", "id": "capture:1"},
            ],
        }))
        self.assertEqual(parsed[0], "capture_dev_list")
        self.assertEqual(parsed[1][0].name, "USB Audio CODEC")
        self.assertEqual(parsed[1][0].identifier, "capture:2")
        self.assertEqual(parsed[2], "capture:2")

    def test_rejects_oversized_audio_device_lists(self) -> None:
        payload = json.dumps({
            "type": "playback_dev_list",
            "list": [{"name": "speaker", "id": str(i)} for i in range(65)],
        })
        self.assertIsNone(parse_device_list_message(payload))

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
            "tx_gain_db": 999, "tx_peak_dbfs": "nan",
            "radio_frequency_hz": -1, "radio_frequency_age_ms": -1,
        }))
        self.assertEqual(status.bitrate_bps, 0)
        self.assertEqual(status.snr_db, 0.0)
        self.assertEqual(status.direction, "rx")
        self.assertEqual(status.bytes_transmitted, 0)
        self.assertEqual(status.bytes_received, 0)
        self.assertEqual(len(status.user_callsign), 16)
        self.assertEqual(len(status.destination_callsign), 16)
        self.assertEqual(len(status.modem_mode), 32)
        self.assertEqual(status.tx_gain_db, 20.0)
        self.assertEqual(status.tx_peak_dbfs, -120.0)
        self.assertIsNone(status.radio_frequency_hz)
        self.assertIsNone(status.radio_frequency_age_ms)

    def test_spectrum_contract_rejects_length_and_fft_limit_violations(self) -> None:
        truncated = struct.pack("<IHHf", SPECTRUM_MAGIC, 2, 8000, -50.0)
        self.assertIsNone(parse_spectrum_frame(truncated))
        oversized = struct.pack("<IHH", SPECTRUM_MAGIC, 4097, 8000)
        self.assertIsNone(parse_spectrum_frame(oversized))
        no_sample_rate = struct.pack("<IHHf", SPECTRUM_MAGIC, 1, 0, -50.0)
        self.assertIsNone(parse_spectrum_frame(no_sample_rate))


if __name__ == "__main__":
    unittest.main()

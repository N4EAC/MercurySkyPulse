from datetime import UTC, datetime
import unittest

from application.beacon import Beacon, CqCall
from application_protocol.beacon import decode_beacon, decode_cq, encode_beacon, encode_cq
from transport.mercury.beacon import KissDecoder, kiss_frame


class BeaconBroadcastContractTests(unittest.TestCase):
    def test_compact_beacon_round_trip_fits_broadcast_payload(self) -> None:
        now = datetime.now(UTC).isoformat()
        beacon = Beacon(
            "N0CALL", "FN30AS", "0.1.0",
            ("beacon", "chat", "file-transfer", "location"),
            now, 40.1, -74.2, now,
        )
        encoded = encode_beacon(beacon)
        self.assertLessEqual(len(encoded), 112)
        decoded = decode_beacon(encoded)
        self.assertEqual(decoded.callsign, "N0CALL")
        self.assertEqual(decoded.grid, "FN30AS")
        self.assertAlmostEqual(decoded.latitude, 40.1)
        self.assertEqual(decoded.capabilities, beacon.capabilities)

    def test_kiss_decoder_handles_fragmentation_and_escaping(self) -> None:
        payload = b"MSPB\xc0\xdbcontent"
        framed = kiss_frame(payload)
        decoder = KissDecoder()
        decoded = []
        for byte in framed:
            decoded.extend(decoder.feed(bytes((byte,))))
        self.assertEqual(decoded, [payload])

    def test_compact_cq_round_trip_is_bounded(self) -> None:
        cq = CqCall("N0CALL", "FN30AS", "0.1.0", datetime.now(UTC).isoformat())
        encoded = encode_cq(cq)
        self.assertLessEqual(len(encoded), 67)
        decoded = decode_cq(encoded)
        self.assertEqual(decoded.callsign, "N0CALL")
        self.assertEqual(decoded.grid, "FN30AS")

    def test_invalid_beacon_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            decode_beacon(b"not-a-beacon")

    def test_kiss_decoder_rejects_unbounded_input(self) -> None:
        decoder = KissDecoder(maximum_frame_bytes=16, maximum_buffer_bytes=20)
        self.assertEqual(decoder.feed(b"X" * 21), [])
        self.assertEqual(decoder.buffer, bytearray())
        self.assertEqual(decoder.malformed_frame_count, 1)


if __name__ == "__main__":
    unittest.main()

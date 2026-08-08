from datetime import UTC, datetime
import unittest

from application.beacon import Beacon
from application_protocol.beacon import decode_beacon, encode_beacon
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

    def test_invalid_beacon_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            decode_beacon(b"not-a-beacon")


if __name__ == "__main__":
    unittest.main()

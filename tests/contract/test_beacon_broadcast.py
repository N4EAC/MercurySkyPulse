from datetime import UTC, datetime
import struct
import unittest

from application.beacon import Beacon, CqCall
from application_protocol.beacon import decode_beacon, decode_cq, encode_beacon, encode_cq
from transport.mercury.beacon import KissDecoder, kiss_frame, kiss_station_frame


class BeaconBroadcastContractTests(unittest.TestCase):
    def test_compact_beacon_round_trip_fits_broadcast_payload(self) -> None:
        now = datetime.now(UTC).isoformat()
        beacon = Beacon(
            "N0CALL", "FN30AS", "0.1.0",
            ("beacon", "chat", "file-transfer", "location"),
            now, 40.1, -74.2, now,
        )
        encoded = encode_beacon(beacon)
        self.assertEqual(len(encoded), 13)
        decoded = decode_beacon(encoded)
        self.assertEqual(decoded.callsign, "N0CALL")
        self.assertEqual(decoded.grid, "FN30AS")
        self.assertIsNone(decoded.latitude)
        self.assertEqual(decoded.capabilities, beacon.capabilities)

    def test_kiss_decoder_handles_fragmentation_and_escaping(self) -> None:
        payload = b"MSPB\xc0\xdbcontent"
        framed = kiss_frame(payload)
        decoder = KissDecoder()
        decoded = []
        for byte in framed:
            decoded.extend(decoder.feed(bytes((byte,))))
        self.assertEqual(decoded, [payload])

    def test_station_frame_selects_mercury_beacon_path_and_drops_padding(self) -> None:
        payload = b"MSPB\xc0\xdbcontent"
        framed = kiss_station_frame(payload)
        self.assertEqual(framed[1], 0x03)
        decoder = KissDecoder()
        self.assertEqual(decoder.feed(framed[:-1] + b"\0" + framed[-1:]), [payload])

    def test_compact_cq_round_trip_is_bounded(self) -> None:
        cq = CqCall("N0CALL", "FN30AS", "0.1.0", datetime.now(UTC).isoformat())
        encoded = encode_cq(cq)
        self.assertEqual(len(encoded), 13)
        decoded = decode_cq(encoded)
        self.assertEqual(decoded.callsign, "N0CALL")
        self.assertEqual(decoded.grid, "FN30AS")

    def test_maximum_datac16_identity_fits(self) -> None:
        now = datetime.now(UTC).isoformat()
        beacon = Beacon(
            "A1BCDEFGH-", "FN30AS12", "12345678901-extra",
            ("beacon", "bbs", "chat", "file-transfer", "gps-history",
             "image", "location"),
            now, 89.9, 179.9, now,
        )
        cq = CqCall(
            "A1BCDEFGH-", "FN30AS12", "12345678901-extra", now
        )
        self.assertEqual(len(encode_beacon(beacon)), 13)
        self.assertEqual(len(encode_cq(cq)), 13)
        self.assertEqual(decode_beacon(encode_beacon(beacon)).callsign,
                         "A1BCDEFGH-")
        self.assertEqual(decode_beacon(encode_beacon(beacon)).grid, "FN30AS12")

    def test_datac16_rejects_callsign_that_cannot_fit(self) -> None:
        now = datetime.now(UTC).isoformat()
        beacon = Beacon("A1BCDEFGHIJ", "FN30AS", "0.1.7", ("beacon",), now)
        cq = CqCall("A1BCDEFGHIJ", "FN30AS", "0.1.7", now)
        with self.assertRaisesRegex(ValueError, "at most 10"):
            encode_beacon(beacon)
        with self.assertRaisesRegex(ValueError, "at most 10"):
            encode_cq(cq)

    def test_datac16_round_trips_each_grid_resolution(self) -> None:
        now = datetime.now(UTC).isoformat()
        for grid in ("AA00", "FN30AS", "RR99XX99"):
            with self.subTest(grid=grid):
                beacon = Beacon("N0CALL", grid, "0.1.7", ("beacon",), now)
                cq = CqCall("N0CALL", grid, "0.1.7", now)
                self.assertEqual(decode_beacon(encode_beacon(beacon)).grid, grid)
                self.assertEqual(decode_cq(encode_cq(cq)).grid, grid)

    def test_datac16_binary_payload_survives_station_kiss_round_trip(self) -> None:
        now = datetime.now(UTC).isoformat()
        beacon = Beacon("N0CALL", "AA00", "0.1.7", ("beacon",), now)
        cq = CqCall("N0CALL", "AA00", "0.1.7", now)
        decoder = KissDecoder()
        for encoded in (encode_beacon(beacon), encode_cq(cq)):
            with self.subTest(marker=encoded[0]):
                self.assertEqual(
                    decoder.feed(kiss_station_frame(encoded)), [encoded]
                )

    def test_legacy_beacon_and_cq_remain_decodable(self) -> None:
        timestamp = int(datetime.now(UTC).timestamp())
        callsign, grid, version = b"N0CALL", b"FN30AS", b"0.1.7"
        legacy_beacon = (
            struct.pack(">4sBBiiII", b"MSPB", 1, 0, 0, 0, timestamp, 0)
            + struct.pack(">I", 5)
            + bytes((len(callsign), len(grid), len(version)))
            + callsign + grid + version
        )
        legacy_cq = (
            struct.pack(">4sBI", b"MSPQ", 1, timestamp)
            + bytes((len(callsign), len(grid), len(version)))
            + callsign + grid + version
        )
        self.assertEqual(decode_beacon(legacy_beacon).callsign, "N0CALL")
        self.assertEqual(decode_cq(legacy_cq).callsign, "N0CALL")

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

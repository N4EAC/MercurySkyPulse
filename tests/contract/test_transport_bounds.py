"""Adversarial bounds for Mercury control and KISS byte streams."""

from __future__ import annotations

import unittest

from transport.mercury.beacon import KissDecoder, kiss_frame
from transport.mercury.tnc import MercuryTncTransport


class TransportInputBoundTests(unittest.TestCase):
    def test_unterminated_control_input_is_bounded_and_reset(self) -> None:
        transport = MercuryTncTransport(maximum_control_line_bytes=16)
        errors = []
        events = []
        transport.error_received.connect(errors.append)
        transport.control_event.connect(events.append)

        transport._read_control_bytes(b"X" * 17)
        self.assertEqual(len(transport._control_buffer), 0)
        self.assertEqual(transport.malformed_input_count, 1)
        self.assertEqual(len(errors), 1)

        transport._read_control_bytes(b"DISCONNECTED\r")
        self.assertEqual(events, ["DISCONNECTED"])

    def test_oversized_terminated_control_line_does_not_hide_next_line(self) -> None:
        transport = MercuryTncTransport(maximum_control_line_bytes=16)
        events = []
        transport.control_event.connect(events.append)
        transport._read_control_bytes(b"X" * 17 + b"\rDISCONNECTED\r")
        self.assertEqual(transport.malformed_input_count, 1)
        self.assertEqual(events, ["DISCONNECTED"])

    def test_buffer_reports_expose_nonnegative_queue_activity(self) -> None:
        transport = MercuryTncTransport()
        queued = []
        transport.queued_bytes_changed.connect(queued.append)
        transport._read_control_bytes(b"BUFFER 2530\rBUFFER 0\rBUFFER invalid\r")
        self.assertEqual(queued, [2530, 0])

    def test_kiss_decoder_bounds_unterminated_input_and_recovers(self) -> None:
        decoder = KissDecoder(maximum_frame_bytes=16, maximum_buffer_bytes=20)
        self.assertEqual(decoder.feed(bytes((0xC0,)) + b"X" * 20), [])
        self.assertEqual(len(decoder.buffer), 0)
        self.assertEqual(decoder.malformed_frame_count, 1)
        self.assertEqual(decoder.feed(kiss_frame(b"recovered")), [b"recovered"])

    def test_kiss_decoder_rejects_oversized_complete_frame(self) -> None:
        decoder = KissDecoder(maximum_frame_bytes=8, maximum_buffer_bytes=20)
        self.assertEqual(decoder.feed(kiss_frame(b"X" * 9)), [])
        self.assertEqual(decoder.malformed_frame_count, 1)
        self.assertEqual(decoder.feed(kiss_frame(b"safe")), [b"safe"])


if __name__ == "__main__":
    unittest.main()

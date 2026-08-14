from datetime import UTC, datetime
import unittest

from application_protocol.messaging import (
    FrameDecoder,
    encode_ack,
    encode_event,
    encode_message,
)


class ChatProtocolTests(unittest.TestCase):
    def test_message_survives_fragmented_transport(self) -> None:
        frame = encode_message("message-1", datetime.now(UTC).isoformat(), "hello")
        decoder = FrameDecoder()
        envelopes = []
        for byte in frame:
            envelopes.extend(decoder.feed(bytes([byte])))
        self.assertEqual(len(envelopes), 1)
        self.assertEqual(envelopes[0].message_id, "message-1")
        self.assertEqual(envelopes[0].text, "hello")

    def test_multiple_frames_can_arrive_together(self) -> None:
        now = datetime.now(UTC).isoformat()
        envelopes = FrameDecoder().feed(
            encode_message("one", now, "first") + encode_ack("one", now)
        )
        self.assertEqual([item.kind for item in envelopes], ["message", "ack"])

    def test_text_length_is_bounded(self) -> None:
        with self.assertRaises(ValueError):
            encode_message("large", datetime.now(UTC).isoformat(), "x" * 2049)

    def test_file_event_survives_stream_framing(self) -> None:
        frame = encode_event(
            "file_chunk", "transfer-1", datetime.now(UTC).isoformat(),
            offset=4096, data="YWJj",
        )
        envelope = FrameDecoder().feed(frame)[0]
        self.assertEqual(envelope.kind, "file_chunk")
        self.assertEqual(envelope.values["offset"], 4096)
        self.assertEqual(envelope.values["data"], "YWJj")

    def test_location_event_is_bounded_and_decoded(self) -> None:
        frame = encode_event(
            "location", "location-1", datetime.now(UTC).isoformat(),
            latitude=40.7128, longitude=-74.006,
            aprs="4042.77N/07400.36W", source="manual",
        )
        envelope = FrameDecoder().feed(frame)[0]
        self.assertEqual(envelope.kind, "location")
        self.assertEqual(envelope.values["aprs"], "4042.77N/07400.36W")

    def test_ping_response_telemetry_is_decoded(self) -> None:
        frame = encode_event(
            "ping_response", "ping-1", datetime.now(UTC).isoformat(),
            snr_db=7.5, bitrate_bps=1200, modem_mode="ARQ",
        )
        envelope = FrameDecoder().feed(frame)[0]
        self.assertEqual(envelope.kind, "ping_response")
        self.assertEqual(envelope.values["bitrate_bps"], 1200)

    def test_bbs_private_message_is_decoded(self) -> None:
        frame = encode_event(
            "bbs_private", "mail-1", datetime.now(UTC).isoformat(),
            sender="N0CALL", recipient="K1ABC", subject="Hello", body="Mailbox test",
        )
        envelope = FrameDecoder().feed(frame)[0]
        self.assertEqual(envelope.kind, "bbs_private")
        self.assertEqual(envelope.values["subject"], "Hello")

    def test_bbs_authentication_proof_is_decoded(self) -> None:
        frame = encode_event(
            "bbs_auth_proof", "challenge-1", datetime.now(UTC).isoformat(),
            callsign="N0CALL", proof="cHJvb2Y=",
        )
        envelope = FrameDecoder().feed(frame)[0]
        self.assertEqual(envelope.kind, "bbs_auth_proof")
        self.assertEqual(envelope.values["callsign"], "N0CALL")

    def test_presence_event_is_bounded_application_data(self) -> None:
        frame = encode_event(
            "presence", "presence-1", datetime.now(UTC).isoformat(),
            state="typing", ttl_seconds=45,
        )
        envelope = FrameDecoder().feed(frame)[0]
        self.assertEqual(envelope.kind, "presence")
        self.assertEqual(envelope.values, {"state": "typing", "ttl_seconds": 45})

    def test_voice_chunk_ack_is_bounded_application_data(self) -> None:
        frame = encode_event(
            "voice_chunk_ack", "voice-1", datetime.now(UTC).isoformat(),
            offset=384,
        )
        envelope = FrameDecoder().feed(frame)[0]
        self.assertEqual(envelope.kind, "voice_chunk_ack")
        self.assertEqual(envelope.values, {"offset": 384})

    def test_decoder_recovers_from_garbage_before_valid_frame(self) -> None:
        now = datetime.now(UTC).isoformat()
        decoder = FrameDecoder()
        self.assertEqual(decoder.feed(b"untrusted-prefix"), [])
        envelopes = decoder.feed(encode_message("recovered", now, "valid"))
        self.assertEqual([item.message_id for item in envelopes], ["recovered"])

    def test_unsupported_and_oversized_events_are_rejected(self) -> None:
        now = datetime.now(UTC).isoformat()
        with self.assertRaises(ValueError):
            encode_event("remote_command", "bad", now, command="transmit")
        with self.assertRaises(ValueError):
            encode_event("file_chunk", "large", now, data="A" * 9000)

if __name__ == "__main__":
    unittest.main()

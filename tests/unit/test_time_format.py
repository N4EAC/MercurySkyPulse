import unittest

from presentation.time_format import format_utc_timestamp


class TimeFormatTests(unittest.TestCase):
    def test_offset_timestamp_is_displayed_as_utc(self) -> None:
        self.assertEqual(
            format_utc_timestamp("2026-08-13T08:30:00-04:00"),
            "2026-08-13 12:30:00 UTC",
        )

    def test_z_timestamp_is_displayed_as_utc(self) -> None:
        self.assertEqual(
            format_utc_timestamp("2026-08-13T12:30:00Z"),
            "2026-08-13 12:30:00 UTC",
        )

    def test_unparseable_timestamp_remains_visible(self) -> None:
        self.assertEqual(format_utc_timestamp("unknown"), "unknown")


if __name__ == "__main__":
    unittest.main()

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from shared.time_utils import (
    format_timestamp_riyadh,
    timestamp_sort_key,
    timestamp_to_utc,
)


class TestTimeUtils(unittest.TestCase):
    def test_utc_timestamp_displays_in_riyadh(self):
        value = "2026-11-15T07:00:00+00:00"
        self.assertEqual(
            format_timestamp_riyadh(value),
            "2026-11-15 10:00:00 +0300 (Asia/Riyadh)",
        )

    def test_naive_timestamp_uses_host_local_timezone(self):
        value = "2026-11-15T10:00:00"
        expected_utc = datetime.fromisoformat(value).astimezone(timezone.utc)
        self.assertEqual(timestamp_to_utc(value), expected_utc)
        expected_riyadh = expected_utc.astimezone(ZoneInfo("Asia/Riyadh"))
        self.assertEqual(
            format_timestamp_riyadh(value),
            f"{expected_riyadh.strftime('%Y-%m-%d %H:%M:%S %z')} (Asia/Riyadh)",
        )

    def test_sorting_mixed_naive_and_aware_timestamps_preserves_source(self):
        legacy_value = "2026-11-15T10:00:00"
        legacy_utc = datetime.fromisoformat(legacy_value).astimezone(timezone.utc)
        newer_value = (legacy_utc + timedelta(minutes=1)).isoformat()
        records = [
            {"timestamp": legacy_value},
            {"timestamp": newer_value},
        ]
        original_values = [record["timestamp"] for record in records]

        ordered = sorted(records, key=lambda record: timestamp_sort_key(record["timestamp"]))

        self.assertEqual([record["timestamp"] for record in ordered], original_values)
        self.assertEqual([record["timestamp"] for record in records], original_values)
        self.assertEqual(format_timestamp_riyadh(legacy_value)[:10], "2026-11-15")
        self.assertEqual(records[0]["timestamp"], legacy_value)

    def test_riyadh_has_no_daylight_saving_offset_change(self):
        riyadh = ZoneInfo("Asia/Riyadh")
        winter = datetime(2026, 1, 15, tzinfo=timezone.utc).astimezone(riyadh)
        summer = datetime(2026, 7, 15, tzinfo=timezone.utc).astimezone(riyadh)
        self.assertEqual(winter.utcoffset(), timedelta(hours=3))
        self.assertEqual(summer.utcoffset(), timedelta(hours=3))

    def test_missing_timezone_database_raises_clear_error(self):
        with patch(
            "shared.time_utils.ZoneInfo",
            side_effect=ZoneInfoNotFoundError("Asia/Riyadh"),
        ):
            with self.assertRaisesRegex(RuntimeError, "Asia/Riyadh"):
                format_timestamp_riyadh("2026-11-15T07:00:00+00:00")

    def test_invalid_timestamp_is_rejected_for_display(self):
        with self.assertRaises(ValueError):
            format_timestamp_riyadh("not-a-timestamp")


if __name__ == "__main__":
    unittest.main()

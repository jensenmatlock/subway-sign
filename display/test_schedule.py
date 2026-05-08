import unittest
from datetime import datetime
from main import is_display_on

WEEKDAY_SCHEDULE = {
    "enabled": True,
    "weekday": {"on": "06:30", "off": "21:00"},
    "weekend": {"on": "09:00", "off": "22:00"},
}


class TestIsDisplayOn(unittest.TestCase):
    # 2026-05-04 is a Monday; 2026-05-09 Saturday; 2026-05-10 Sunday.

    def test_weekday_before_on(self):
        self.assertFalse(is_display_on(datetime(2026, 5, 4, 6, 29), WEEKDAY_SCHEDULE))

    def test_weekday_at_on(self):
        self.assertTrue(is_display_on(datetime(2026, 5, 4, 6, 30), WEEKDAY_SCHEDULE))

    def test_weekday_midday(self):
        self.assertTrue(is_display_on(datetime(2026, 5, 4, 14, 0), WEEKDAY_SCHEDULE))

    def test_weekday_at_off(self):
        self.assertFalse(is_display_on(datetime(2026, 5, 4, 21, 0), WEEKDAY_SCHEDULE))

    def test_weekday_after_off(self):
        self.assertFalse(is_display_on(datetime(2026, 5, 4, 23, 0), WEEKDAY_SCHEDULE))

    def test_saturday_before_on(self):
        self.assertFalse(is_display_on(datetime(2026, 5, 9, 8, 59), WEEKDAY_SCHEDULE))

    def test_saturday_midday(self):
        self.assertTrue(is_display_on(datetime(2026, 5, 9, 12, 0), WEEKDAY_SCHEDULE))

    def test_sunday_after_off(self):
        self.assertFalse(is_display_on(datetime(2026, 5, 10, 22, 30), WEEKDAY_SCHEDULE))

    def test_sunday_uses_weekend_window(self):
        # 08:00 Sunday: weekday on time would say True, weekend says False.
        self.assertFalse(is_display_on(datetime(2026, 5, 10, 8, 0), WEEKDAY_SCHEDULE))

    def test_disabled_always_on(self):
        sched = dict(WEEKDAY_SCHEDULE, enabled=False)
        self.assertTrue(is_display_on(datetime(2026, 5, 5, 3, 0), sched))

    def test_missing_schedule_always_on(self):
        self.assertTrue(is_display_on(datetime(2026, 5, 5, 3, 0), None))


if __name__ == "__main__":
    unittest.main()

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

    def test_friday_evening_before_cutover_uses_weekday(self):
        # 2026-05-08 is Friday. 19:59 → weekday window (off at 21:00) → on.
        self.assertTrue(is_display_on(datetime(2026, 5, 8, 19, 59), WEEKDAY_SCHEDULE))

    def test_friday_night_uses_weekend(self):
        # Friday 21:30: weekday off (21:00) would say False, weekend (until 22:00) says True.
        self.assertTrue(is_display_on(datetime(2026, 5, 8, 21, 30), WEEKDAY_SCHEDULE))

    def test_friday_night_after_weekend_off(self):
        # Friday 22:30: weekend window says off.
        self.assertFalse(is_display_on(datetime(2026, 5, 8, 22, 30), WEEKDAY_SCHEDULE))

    def test_sunday_evening_before_cutover_uses_weekend(self):
        # Sunday 19:59 → weekend window → on.
        self.assertTrue(is_display_on(datetime(2026, 5, 10, 19, 59), WEEKDAY_SCHEDULE))

    def test_sunday_night_uses_weekday(self):
        # Sunday 21:30: weekend (until 22:00) would say True, weekday (off at 21:00) says False.
        self.assertFalse(is_display_on(datetime(2026, 5, 10, 21, 30), WEEKDAY_SCHEDULE))

    def test_sunday_night_before_weekday_off(self):
        # Sunday 20:30: weekday window (off at 21:00) says on.
        self.assertTrue(is_display_on(datetime(2026, 5, 10, 20, 30), WEEKDAY_SCHEDULE))

    def test_disabled_always_on(self):
        sched = dict(WEEKDAY_SCHEDULE, enabled=False)
        self.assertTrue(is_display_on(datetime(2026, 5, 5, 3, 0), sched))

    def test_missing_schedule_always_on(self):
        self.assertTrue(is_display_on(datetime(2026, 5, 5, 3, 0), None))


if __name__ == "__main__":
    unittest.main()

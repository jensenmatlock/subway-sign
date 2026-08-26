import unittest
from datetime import datetime
from unittest import mock

from main import (
    _dim_color,
    CLOCK_COLOR,
    clock_right_edge,
    format_clock,
    weather_glyph_x,
    weather_text_x,
    SubwayDisplay,
    WEATHER_COLOR,
    RAIN_COLOR,
    SNOW_COLOR,
    DIM_FACTOR,
)


class TestDimColor(unittest.TestCase):
    def test_scales_each_channel(self):
        self.assertEqual(_dim_color((100, 200, 50), 0.5), (50, 100, 25))

    def test_factor_one_is_identity(self):
        self.assertEqual(_dim_color(WEATHER_COLOR, 1.0), WEATHER_COLOR)

    def test_dimmed_is_strictly_darker(self):
        for rgb in (WEATHER_COLOR, RAIN_COLOR, SNOW_COLOR):
            dimmed = _dim_color(rgb, DIM_FACTOR)
            self.assertTrue(all(d < c for d, c in zip(dimmed, rgb) if c > 0))

    def test_clamps_to_byte_range(self):
        self.assertEqual(_dim_color((300, 10, 0), 1.0), (255, 10, 0))


class TestGlyphColors(unittest.TestCase):
    """The two precipitation glyphs must stay tellable apart from each other and
    from the temperature text, at full brightness and dimmed."""

    def test_glyph_colors_are_distinct(self):
        self.assertNotEqual(RAIN_COLOR, SNOW_COLOR)
        self.assertNotEqual(RAIN_COLOR, WEATHER_COLOR)
        self.assertNotEqual(SNOW_COLOR, WEATHER_COLOR)

    def test_glyph_colors_stay_distinct_when_dimmed(self):
        dim = lambda rgb: _dim_color(rgb, DIM_FACTOR)
        self.assertNotEqual(dim(RAIN_COLOR), dim(SNOW_COLOR))
        self.assertNotEqual(dim(SNOW_COLOR), dim(WEATHER_COLOR))

    def test_dimmed_snow_stays_visible(self):
        # Snow is the palest glyph, so it is the one at risk of dimming to black.
        self.assertTrue(all(c > 0 for c in _dim_color(SNOW_COLOR, DIM_FACTOR)))


def _frame(precip, temperature=63):
    return {
        "rows": {"row1": {"arrivals": [{"route": "B", "minutesUntil": 7}]}},
        "weather": {"temperature": temperature, "precip": precip},
    }


class TestComputeStateKey(unittest.TestCase):
    """update() skips Clear+Swap when this key is unchanged, so the key is what
    decides whether a glyph change actually reaches the panel. A precip change
    that doesn't move the key renders a stale glyph until something else does."""

    def test_precip_change_changes_the_key(self):
        key = SubwayDisplay._compute_state_key
        rain = key(_frame("rain"), True)
        snow = key(_frame("snow"), True)
        clear = key(_frame(None), True)
        self.assertNotEqual(rain, snow)
        self.assertNotEqual(rain, clear)
        self.assertNotEqual(snow, clear)

    def test_identical_frames_share_a_key(self):
        # The flicker guard: no spurious redraw when nothing changed.
        key = SubwayDisplay._compute_state_key
        self.assertEqual(key(_frame("snow"), True), key(_frame("snow"), True))

    def test_temperature_change_changes_the_key(self):
        key = SubwayDisplay._compute_state_key
        self.assertNotEqual(key(_frame("rain", 63), True), key(_frame("rain", 64), True))

    def test_precip_still_counts_when_arrivals_are_blanked(self):
        # Off-schedule hours blank the rows but keep weather on, so a glyph
        # change overnight still has to force a redraw.
        key = SubwayDisplay._compute_state_key
        self.assertNotEqual(key(_frame("rain"), False), key(_frame("snow"), False))

    def test_missing_weather_is_handled(self):
        key = SubwayDisplay._compute_state_key
        self.assertEqual(key({"rows": {}}, True), key({"rows": {}, "weather": None}, True))
        self.assertIsNotNone(key(None, True))

    def test_clock_change_forces_an_off_hours_redraw(self):
        # Off-hours the weather barely changes, so without the clock in the key
        # the minute would sit stale on the panel until the temperature moved.
        key = SubwayDisplay._compute_state_key
        frame = _frame(None)
        self.assertNotEqual(key(frame, False, "9:47p"), key(frame, False, "9:48p"))
        self.assertEqual(key(frame, False, "9:47p"), key(frame, False, "9:47p"))


class TestFormatClock(unittest.TestCase):
    def test_afternoon_and_evening_use_p(self):
        self.assertEqual(format_clock(datetime(2026, 8, 26, 21, 47)), "9:47p")
        self.assertEqual(format_clock(datetime(2026, 8, 26, 13, 5)), "1:05p")

    def test_morning_uses_a(self):
        self.assertEqual(format_clock(datetime(2026, 8, 26, 6, 3)), "6:03a")

    def test_midnight_is_twelve_a(self):
        # 0:xx must read as 12a, not 0a — the modulo trap.
        self.assertEqual(format_clock(datetime(2026, 8, 26, 0, 9)), "12:09a")

    def test_noon_is_twelve_p(self):
        self.assertEqual(format_clock(datetime(2026, 8, 26, 12, 0)), "12:00p")

    def test_minutes_are_zero_padded(self):
        self.assertEqual(format_clock(datetime(2026, 8, 26, 22, 0)), "10:00p")


class TestClockAndWeatherFit(unittest.TestCase):
    """Row 1 is 64px wide and off-hours it carries both the clock (left) and the
    weather block (right). These bound the two so they can't overlap."""

    WIDEST_CLOCK = "12:47p"

    def test_clock_right_edge_leaves_a_one_pixel_gap(self):
        # "9:47p" is 5 chars = 29px drawn from x=1, so x=30 is the last lit
        # column and 31 is the first free one.
        self.assertEqual(clock_right_edge("9:47p"), 31)

    def test_clock_stays_on_the_panel(self):
        self.assertLessEqual(clock_right_edge(self.WIDEST_CLOCK), 64)

    def test_widest_clock_clears_a_normal_temperature(self):
        # 2- and 3-char temperatures ("5°", "72°") keep room for the glyph too.
        for temp_text in ("5°", "72°"):
            self.assertGreaterEqual(
                weather_glyph_x(temp_text), clock_right_edge(self.WIDEST_CLOCK)
            )

    def test_widest_clock_never_overlaps_the_temperature_itself(self):
        # Even a 4-char temperature ("-12°") starts right of the clock; only the
        # precip glyph gets squeezed out, which draw_weather() drops.
        self.assertGreater(weather_text_x("-12°"), clock_right_edge(self.WIDEST_CLOCK))


class TestClockColor(unittest.TestCase):
    def test_dimmed_clock_stays_visible_and_neutral(self):
        dimmed = _dim_color(CLOCK_COLOR, DIM_FACTOR)
        self.assertTrue(all(c > 0 for c in dimmed))
        # Neutral gray, so it doesn't read as part of the cyan weather block.
        self.assertEqual(len(set(dimmed)), 1)
        self.assertNotEqual(dimmed, _dim_color(WEATHER_COLOR, DIM_FACTOR))


class TestUpdateDispatch(unittest.TestCase):
    """update() is the glue: it decides whether the clock is drawn at all and
    hands draw_weather the bound that keeps the precip glyph off the clock.
    The isolated helper tests all still pass if this wiring breaks."""

    def _update(self, draw_arrivals, now=datetime(2026, 8, 26, 22, 7)):
        display = SubwayDisplay()
        with mock.patch.object(SubwayDisplay, "draw_clock") as clock,              mock.patch.object(SubwayDisplay, "draw_weather") as weather:
            display.update(_frame("rain"), draw_arrivals=draw_arrivals, now=now)
        return clock, weather

    def test_on_schedule_draws_no_clock_and_no_left_bound(self):
        clock, weather = self._update(draw_arrivals=True)
        clock.assert_not_called()
        self.assertEqual(weather.call_args.kwargs["left_bound"], 0)
        self.assertFalse(weather.call_args.kwargs["dim"])

    def test_off_schedule_draws_the_clock_for_the_given_time(self):
        clock, weather = self._update(draw_arrivals=False)
        clock.assert_called_once_with("10:07p")
        self.assertTrue(weather.call_args.kwargs["dim"])

    def test_off_schedule_bounds_the_weather_block_by_the_clock(self):
        _, weather = self._update(draw_arrivals=False)
        self.assertEqual(
            weather.call_args.kwargs["left_bound"], clock_right_edge("10:07p")
        )


if __name__ == "__main__":
    unittest.main()

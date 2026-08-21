import unittest

from main import (
    _dim_color,
    SubwayDisplay,
    WEATHER_COLOR,
    RAIN_COLOR,
    SNOW_COLOR,
    WEATHER_DIM_FACTOR,
)


class TestDimColor(unittest.TestCase):
    def test_scales_each_channel(self):
        self.assertEqual(_dim_color((100, 200, 50), 0.5), (50, 100, 25))

    def test_factor_one_is_identity(self):
        self.assertEqual(_dim_color(WEATHER_COLOR, 1.0), WEATHER_COLOR)

    def test_dimmed_is_strictly_darker(self):
        for rgb in (WEATHER_COLOR, RAIN_COLOR, SNOW_COLOR):
            dimmed = _dim_color(rgb, WEATHER_DIM_FACTOR)
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
        dim = lambda rgb: _dim_color(rgb, WEATHER_DIM_FACTOR)
        self.assertNotEqual(dim(RAIN_COLOR), dim(SNOW_COLOR))
        self.assertNotEqual(dim(SNOW_COLOR), dim(WEATHER_COLOR))

    def test_dimmed_snow_stays_visible(self):
        # Snow is the palest glyph, so it is the one at risk of dimming to black.
        self.assertTrue(all(c > 0 for c in _dim_color(SNOW_COLOR, WEATHER_DIM_FACTOR)))


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


if __name__ == "__main__":
    unittest.main()

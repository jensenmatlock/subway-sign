import unittest

from main import _dim_color, WEATHER_COLOR, RAIN_COLOR, WEATHER_DIM_FACTOR


class TestDimColor(unittest.TestCase):
    def test_scales_each_channel(self):
        self.assertEqual(_dim_color((100, 200, 50), 0.5), (50, 100, 25))

    def test_factor_one_is_identity(self):
        self.assertEqual(_dim_color(WEATHER_COLOR, 1.0), WEATHER_COLOR)

    def test_dimmed_is_strictly_darker(self):
        for rgb in (WEATHER_COLOR, RAIN_COLOR):
            dimmed = _dim_color(rgb, WEATHER_DIM_FACTOR)
            self.assertTrue(all(d < c for d, c in zip(dimmed, rgb) if c > 0))

    def test_clamps_to_byte_range(self):
        self.assertEqual(_dim_color((300, 10, 0), 1.0), (255, 10, 0))


if __name__ == "__main__":
    unittest.main()

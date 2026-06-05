import unittest

from main import choose_render_data

MAX = 3
FRAME_A = {"rows": {"row1": {"arrivals": []}}}
FRAME_B = {"rows": {"row2": {"arrivals": []}}}


class TestChooseRenderData(unittest.TestCase):
    def test_fresh_data_renders_and_resets(self):
        # A successful fetch is rendered, becomes the new last good, resets count.
        data, last_good, failures = choose_render_data(FRAME_A, FRAME_B, 2, MAX)
        self.assertIs(data, FRAME_A)
        self.assertIs(last_good, FRAME_A)
        self.assertEqual(failures, 0)

    def test_failure_within_cap_shows_last_good(self):
        data, last_good, failures = choose_render_data(None, FRAME_A, 0, MAX)
        self.assertIs(data, FRAME_A)
        self.assertIs(last_good, FRAME_A)
        self.assertEqual(failures, 1)

    def test_failure_at_cap_still_shows_last_good(self):
        # Third consecutive failure (failures 2 -> 3) is the last one we cover.
        data, last_good, failures = choose_render_data(None, FRAME_A, 2, MAX)
        self.assertIs(data, FRAME_A)
        self.assertEqual(failures, 3)

    def test_failure_beyond_cap_gives_no_data(self):
        # Fourth consecutive failure (3 -> 4) exceeds the cap -> NO DATA.
        data, last_good, failures = choose_render_data(None, FRAME_A, 3, MAX)
        self.assertIsNone(data)
        self.assertIs(last_good, FRAME_A)  # retained in case the fetch recovers
        self.assertEqual(failures, 4)

    def test_failure_with_no_last_good_gives_no_data(self):
        # Cold start: never had a good frame, so a failure draws NO DATA.
        data, last_good, failures = choose_render_data(None, None, 0, MAX)
        self.assertIsNone(data)
        self.assertIsNone(last_good)
        self.assertEqual(failures, 1)

    def test_recovery_resets_after_giving_up(self):
        # After blanking, a successful fetch recovers cleanly.
        data, last_good, failures = choose_render_data(FRAME_B, FRAME_A, 5, MAX)
        self.assertIs(data, FRAME_B)
        self.assertIs(last_good, FRAME_B)
        self.assertEqual(failures, 0)


if __name__ == "__main__":
    unittest.main()

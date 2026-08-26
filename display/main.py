#!/usr/bin/env python3
"""
NYC Subway Sign - LED Matrix Display

Fetches arrival data from the local API server and displays it on a 64x32 RGB LED matrix.
Requires the rpi-rgb-led-matrix library: https://github.com/hzeller/rpi-rgb-led-matrix
"""

import json
import time
import requests
import sys
from datetime import datetime, time as dtime
from pathlib import Path

# Only import RGB matrix on Raspberry Pi
try:
    from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics
    HAS_MATRIX = True
except ImportError:
    HAS_MATRIX = False
    print("Note: rgbmatrix not available - running in simulation mode")

# Load configuration
CONFIG_PATH = Path(__file__).parent.parent / 'config.json'
with open(CONFIG_PATH) as f:
    CONFIG = json.load(f)

def _parse_hhmm(s):
    h, m = s.split(":")
    return dtime(int(h), int(m))


NIGHT_CUTOVER = dtime(20, 0)


def is_display_on(now, schedule):
    """Return True if the display should be drawing at `now` (a datetime).

    Friday night (>= 20:00) is treated as weekend; Sunday night (>= 20:00) is
    treated as weekday. Assumes `on < off` within a single day for each window.
    """
    if not schedule or not schedule.get("enabled", True):
        return True
    dow = now.weekday()
    after_cutover = now.time() >= NIGHT_CUTOVER
    if dow == 4 and after_cutover:  # Friday night → weekend
        is_weekday = False
    elif dow == 6 and after_cutover:  # Sunday night → weekday
        is_weekday = True
    else:
        is_weekday = dow < 5
    window = schedule["weekday" if is_weekday else "weekend"]
    on_t = _parse_hhmm(window["on"])
    off_t = _parse_hhmm(window["off"])
    return on_t <= now.time() < off_t


# How many consecutive failed fetches we'll paper over by re-showing the last
# good frame before giving up and drawing NO DATA. A failed cycle costs up to
# (request timeout + refresh interval), so 3 ≈ 90-135s of last-good before blank.
MAX_CONSECUTIVE_FAILURES = 3


def choose_render_data(fetched, last_good, failures, max_failures):
    """Decide what to draw when a fetch may have failed.

    A single slow/failed poll shouldn't blank a working display, so we keep
    showing the last good frame for up to `max_failures` consecutive failures,
    then fall back to None (NO DATA) if the outage persists.

    Returns (data_to_render, new_last_good, new_failures).
    """
    if fetched is not None:
        return fetched, fetched, 0
    failures += 1
    if last_good is not None and failures <= max_failures:
        return last_good, last_good, failures
    return None, last_good, failures


# Official MTA line colors (RGB)
LINE_COLORS = {
    # 8th Ave (blue)
    'A': (0, 57, 166), 'C': (0, 57, 166), 'E': (0, 57, 166),
    # 6th Ave (orange)
    'B': (255, 99, 25), 'D': (255, 99, 25), 'F': (255, 99, 25), 'M': (255, 99, 25),
    # Broadway-7th Ave (red)
    '1': (238, 53, 46), '2': (238, 53, 46), '3': (238, 53, 46),
    # Lexington Ave (green)
    '4': (0, 147, 60), '5': (0, 147, 60), '6': (0, 147, 60),
    # Flushing (purple)
    '7': (185, 51, 173),
    # Crosstown (lime)
    'G': (108, 190, 69),
    # Nassau (brown)
    'J': (153, 102, 51), 'Z': (153, 102, 51),
    # Canarsie (gray)
    'L': (167, 169, 172),
    # Broadway (yellow)
    'N': (252, 204, 10), 'Q': (252, 204, 10), 'R': (252, 204, 10), 'W': (252, 204, 10),
    # Shuttle (dark gray)
    'S': (128, 128, 128),
}

PANEL_WIDTH = 64

# Row Y positions for 32-pixel height display (3 rows filling full height)
# Each row is 10px tall with 1px gaps: 0-9, 11-20, 22-31
ROW_POSITIONS = {
    'row1': 0,
    'row2': 11,
    'row3': 22,
}

# Weather render colors. Cyan/teal is distinct from the white arrival times
# and from every MTA line bullet color.
WEATHER_COLOR = (80, 220, 220)
RAIN_COLOR = (80, 140, 220)
SNOW_COLOR = (200, 225, 255)

# Off-schedule clock: neutral gray so it reads as a clock rather than part of
# the cyan weather block sharing row 1, drawn hard against the left edge.
CLOCK_COLOR = (200, 200, 200)
CLOCK_X = 1

# Brightness multiplier applied to everything drawn during off-schedule hours,
# when the train rows are blanked. Keeps the temperature and clock legible but
# visibly muted in a dark room.
DIM_FACTOR = 0.25


def _dim_color(rgb, factor):
    """Scale an (r, g, b) tuple by `factor`, clamping to the 0-255 range."""
    return tuple(max(0, min(255, int(c * factor))) for c in rgb)


def text_width(text):
    """Pixel width of `text` in the 5x8 font: 5 px per glyph, 1 px advance."""
    return len(text) * 6 - 1


def clock_right_edge(text):
    """First x free to the right of a clock drawn at CLOCK_X, plus a 1px gap."""
    return CLOCK_X + text_width(text) + 1


def weather_text_x(text):
    """Left x of the right-aligned weather text on row 1."""
    return PANEL_WIDTH - text_width(text)


def weather_glyph_x(text):
    """Left x of the 5x5 precip glyph, which sits left of the weather text."""
    return weather_text_x(text) - 7


def format_clock(now):
    """Format `now` as a compact 12-hour clock, e.g. '9:47p' / '12:03a'.

    No space before the suffix and no leading zero on the hour: at 6 chars
    worst case ('12:47p') this is the widest the clock ever gets, which is what
    the row 1 pixel budget in draw_weather() is sized against.
    """
    hour = now.hour % 12 or 12
    suffix = 'p' if now.hour >= 12 else 'a'
    return f"{hour}:{now.minute:02d}{suffix}"


class SubwayDisplay:
    """Manages the LED matrix display for subway arrivals."""

    def __init__(self):
        self.matrix = None
        self.canvas = None
        self.font = None
        self.font_small = None
        self._last_state_key = None

        if HAS_MATRIX:
            self._init_matrix()

    @staticmethod
    def _compute_state_key(data, draw_arrivals, clock_text=None):
        """Build a comparable key representing what would be drawn.

        Skips a redraw when this key matches the previous frame so the
        matrix doesn't flicker on no-op refresh cycles. `clock_text` is part of
        the key so the off-schedule clock still redraws on the minute.
        """
        weather = (data or {}).get('weather') or {}
        weather_part = (weather.get('temperature'), weather.get('precip'))

        if not draw_arrivals:
            return ('weather-only', weather_part, clock_text)

        if not data or 'rows' not in data:
            return ('no-data', weather_part)

        rows = data['rows']
        rows_part = tuple(
            tuple(
                (a.get('route'), a.get('minutesUntil'))
                for a in rows.get(rk, {}).get('arrivals', [])
            )
            for rk in ('row1', 'row2', 'row3')
        )
        return ('rows', rows_part, weather_part)

    def _init_matrix(self):
        """Initialize the RGB LED matrix."""
        options = RGBMatrixOptions()
        options.rows = CONFIG['display']['rows']
        options.cols = CONFIG['display']['cols']
        options.brightness = CONFIG['display']['brightness']
        options.gpio_slowdown = CONFIG['display']['gpio_slowdown']
        options.hardware_mapping = CONFIG['display'].get('hardware_mapping', 'regular')
        # Capping the refresh rate to a steady, sustainable value keeps it from
        # fluctuating when the frame redraws, which shows as flicker. pwm_bits
        # trades color depth for refresh headroom if more is needed (default 11).
        options.pwm_bits = CONFIG['display'].get('pwm_bits', 11)
        options.limit_refresh_rate_hz = CONFIG['display'].get('limit_refresh_rate_hz', 0)
        options.drop_privileges = False

        self.matrix = RGBMatrix(options=options)
        self.canvas = self.matrix.CreateFrameCanvas()

        # Load fonts from rpi-rgb-led-matrix fonts directory
        # Use project parent dir (not home dir, since service runs as root)
        project_dir = Path(__file__).parent.parent
        font_dir = project_dir.parent / 'rpi-rgb-led-matrix' / 'fonts'
        self.font = graphics.Font()
        self.font.LoadFont(str(font_dir / '5x8.bdf'))

        # Smaller font for bullet letters
        self.font_small = graphics.Font()
        try:
            self.font_small.LoadFont(str(font_dir / '5x7.bdf'))
        except:
            self.font_small = self.font

    def draw_line_bullet(self, x, y, line):
        """
        Draw a colored circle with the line letter.
        The bullet is 9x9 pixels.
        """
        if not HAS_MATRIX:
            return 10  # Return width for simulation

        color = LINE_COLORS.get(line, (255, 255, 255))

        # Draw filled circle (approximated with horizontal lines)
        # Circle pattern for 9x9:
        #   ..XXXXX..  (row 0: 5 pixels)
        #   .XXXXXXX.  (row 1: 7 pixels)
        #   XXXXXXXXX  (row 2-6: 9 pixels)
        #   .XXXXXXX.  (row 7: 7 pixels)
        #   ..XXXXX..  (row 8: 5 pixels)
        circle_pattern = [
            (2, 5),   # row 0
            (1, 7),   # row 1
            (0, 9),   # row 2
            (0, 9),   # row 3
            (0, 9),   # row 4
            (0, 9),   # row 5
            (0, 9),   # row 6
            (1, 7),   # row 7
            (2, 5),   # row 8
        ]

        for row_offset, (start, width) in enumerate(circle_pattern):
            for px in range(width):
                self.canvas.SetPixel(x + start + px, y + row_offset, *color)

        # Draw line letter in contrasting color
        # Use black text on bright backgrounds, white on dark
        brightness = sum(color)
        if brightness > 400:
            text_color = graphics.Color(0, 0, 0)
        else:
            text_color = graphics.Color(255, 255, 255)

        # Center the 5x7 letter in the 9x9 bullet
        graphics.DrawText(self.canvas, self.font_small, x + 2, y + 7, text_color, line)

        return 10  # Bullet width + 1px spacing

    def draw_time(self, x, y, minutes):
        """Draw arrival time in minutes."""
        if not HAS_MATRIX:
            return

        white = graphics.Color(200, 200, 200)

        text = f"{max(minutes, 0)}"

        graphics.DrawText(self.canvas, self.font, x, y + 7, white, text)

    def _build_display_groups(self, row_key, arrivals):
        """
        Build display groups from arrivals.
        If the row has a 'groups' config, merge lines per group.
        Otherwise, group by individual route (default behavior).
        Returns list of (bullet_line, sorted_times) tuples.
        """
        layout = CONFIG.get('layout', {}).get(row_key, {})
        groups_config = layout.get('groups')

        # Index arrivals by route
        by_route = {}
        for arrival in arrivals:
            route = arrival['route']
            if route not in by_route:
                by_route[route] = []
            by_route[route].append(arrival['minutesUntil'])

        if groups_config:
            # Merge lines per configured group
            display_groups = []
            for group in groups_config:
                group_lines = group['lines']
                merged_times = []
                for line in group_lines:
                    merged_times.extend(by_route.get(line, []))
                if merged_times:
                    merged_times.sort()
                    display_groups.append((group_lines[0], merged_times))
            return display_groups
        else:
            # Default: one group per route
            return list(by_route.items())

    def draw_row(self, row_key, arrivals):
        """
        Draw a single row of arrivals.
        Format: [Bullet] Xm Xm  [Bullet] Xm Xm
        """
        if not HAS_MATRIX:
            # Simulation mode - just print
            if arrivals:
                times = [f"{a['route']}:{a['minutesUntil']}m" for a in arrivals]
                print(f"  {row_key}: {', '.join(times)}", flush=True)
            else:
                print(f"  {row_key}: ---", flush=True)
            return

        y = ROW_POSITIONS.get(row_key, 0)
        x = 1

        if not arrivals:
            # No arrivals - show dashes
            gray = graphics.Color(100, 100, 100)
            graphics.DrawText(self.canvas, self.font, x, y + 7, gray, "---")
            return

        display_groups = self._build_display_groups(row_key, arrivals)

        # Draw each group's bullet and times
        for route, times in display_groups:
            if x > 50:  # Don't overflow the display
                break

            # Draw the line bullet
            x += self.draw_line_bullet(x, y, route)

            # Draw up to 2 arrival times for this group
            white = graphics.Color(200, 200, 200)
            for i, mins in enumerate(times[:2]):
                time_text = f"{max(mins, 0)}"

                graphics.DrawText(self.canvas, self.font, x, y + 7, white, time_text)
                x += len(time_text) * 5 + 3  # 5px per char + 3px spacing

            x += 1  # Space before next group

    def _draw_droplet(self, x, y, rgb):
        """Draw a 5x5 water-drop glyph anchored at (x, y)."""
        pattern = [
            "..#..",
            ".###.",
            ".###.",
            "#####",
            ".###.",
        ]
        for dy, row in enumerate(pattern):
            for dx, ch in enumerate(row):
                if ch == '#':
                    self.canvas.SetPixel(x + dx, y + dy, *rgb)

    def _draw_snowflake(self, x, y, rgb):
        """Draw a 5x5 snowflake glyph anchored at (x, y)."""
        pattern = [
            "#.#.#",
            ".###.",
            "#####",
            ".###.",
            "#.#.#",
        ]
        for dy, row in enumerate(pattern):
            for dx, ch in enumerate(row):
                if ch == '#':
                    self.canvas.SetPixel(x + dx, y + dy, *rgb)

    def draw_clock(self, text):
        """Draw the current time at the left of row 1, always dimmed.

        Only used off-schedule, where rows 2-3 are blank; the clock shares row 1
        with the weather block on the right.
        """
        if not HAS_MATRIX:
            print(f"  clock: {text}", flush=True)
            return

        color = graphics.Color(*_dim_color(CLOCK_COLOR, DIM_FACTOR))
        graphics.DrawText(self.canvas, self.font, CLOCK_X, 7, color, text)

    def draw_weather(self, weather, dim=False, left_bound=0):
        """Draw temperature + optional precipitation glyph at the top-right of row 1.

        `dim` mutes the colors for off-schedule hours, when the train rows are
        blanked but the weather stays on. `left_bound` is the first x the block
        may use: off-schedule the clock owns the left of row 1, and the glyph is
        dropped rather than overlapped in the rare case they'd both want the
        same pixels (a 4-char temperature such as `-12` alongside a 6-char clock).
        """
        if not weather or weather.get('temperature') is None:
            return

        if not HAS_MATRIX:
            unit = weather.get('unit', 'F')
            precip = weather.get('precip')
            stale = weather.get('stale', False)
            print(f"  weather: {weather['temperature']}°{unit} precip={precip} stale={stale} dim={dim}", flush=True)
            return

        text = f"{weather['temperature']}°"
        x = weather_text_x(text)

        # 'rain' | 'snow' | None — the server decides both type and whether it
        # clears the probability threshold, so None simply means draw nothing.
        precip = weather.get('precip')
        glyph, glyph_rgb = {
            'rain': (self._draw_droplet, RAIN_COLOR),
            'snow': (self._draw_snowflake, SNOW_COLOR),
        }.get(precip, (None, None))

        weather_rgb = WEATHER_COLOR
        if dim:
            weather_rgb = _dim_color(weather_rgb, DIM_FACTOR)
            if glyph_rgb is not None:
                glyph_rgb = _dim_color(glyph_rgb, DIM_FACTOR)

        weather_color = graphics.Color(*weather_rgb)
        graphics.DrawText(self.canvas, self.font, x, 7, weather_color, text)

        glyph_x = weather_glyph_x(text)
        if glyph is not None and glyph_x >= left_bound:
            glyph(glyph_x, 2, glyph_rgb)

    def draw_error(self, message):
        """Display an error message."""
        if not HAS_MATRIX:
            print(f"ERROR: {message}")
            return

        red = graphics.Color(255, 0, 0)
        graphics.DrawText(self.canvas, self.font, 2, 17, red, message[:12])

    def update(self, data, draw_arrivals=True, now=None):
        """Update the display.

        draw_arrivals=False blanks the train rows but still renders weather and
        the current time — used during off-schedule hours so the temperature and
        clock stay visible. Skips the redraw entirely when the rendered state
        would be unchanged.
        """
        clock_text = None if draw_arrivals else format_clock(now or datetime.now())
        state_key = self._compute_state_key(data, draw_arrivals, clock_text)
        if HAS_MATRIX and state_key == self._last_state_key:
            return
        self._last_state_key = state_key

        if HAS_MATRIX:
            self.canvas.Clear()

        weather = (data or {}).get('weather')

        if draw_arrivals:
            if data and 'rows' in data:
                for row_key in ['row1', 'row2', 'row3']:
                    row_data = data['rows'].get(row_key, {})
                    arrivals = row_data.get('arrivals', [])
                    self.draw_row(row_key, arrivals)
            else:
                self.draw_error("NO DATA")

        if clock_text is not None:
            self.draw_clock(clock_text)

        self.draw_weather(
            weather,
            dim=not draw_arrivals,
            left_bound=clock_right_edge(clock_text) if clock_text else 0,
        )

        if HAS_MATRIX:
            self.canvas = self.matrix.SwapOnVSync(self.canvas)

    def clear(self):
        """Clear the display."""
        if HAS_MATRIX:
            self.canvas.Clear()
            self.canvas = self.matrix.SwapOnVSync(self.canvas)


def fetch_arrivals(port=None):
    """Fetch arrival data from the local API server."""
    if port is None:
        port = CONFIG['server']['port']

    try:
        response = requests.get(
            f"http://localhost:{port}/api/arrivals",
            timeout=15
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        print("Error: Cannot connect to API server. Is it running?")
        return None
    except requests.exceptions.Timeout:
        print("Error: API request timed out")
        return None
    except Exception as e:
        print(f"Error fetching arrivals: {e}")
        return None


def main():
    """Main display loop."""
    print("NYC Subway Sign Display", flush=True)
    print("=" * 40, flush=True)
    print(f"Matrix available: {HAS_MATRIX}", flush=True)
    print(f"API server port: {CONFIG['server']['port']}", flush=True)
    print(f"Refresh interval: {CONFIG['server']['refreshInterval']}ms", flush=True)
    print("=" * 40, flush=True)

    display = SubwayDisplay()
    refresh_seconds = CONFIG['server']['refreshInterval'] / 1000

    print("\nStarting display loop. Press Ctrl+C to exit.\n", flush=True)

    last_good = None
    failures = 0

    try:
        while True:
            now = datetime.now()
            schedule_on = is_display_on(now, CONFIG.get("schedule"))
            fetched = fetch_arrivals()
            data, last_good, failures = choose_render_data(
                fetched, last_good, failures, MAX_CONSECUTIVE_FAILURES
            )

            ts = time.strftime('%H:%M:%S')
            if not schedule_on:
                print(f"[{ts}] off-hours - weather only", flush=True)
            elif fetched is None and data is not None:
                print(f"[{ts}] fetch failed - showing last good (failure {failures})", flush=True)
            elif fetched is None:
                print(f"[{ts}] fetch failed - no data ({failures} consecutive)", flush=True)
            else:
                print(f"[{ts}] Updated arrivals:", flush=True)

            display.update(data, draw_arrivals=schedule_on, now=now)
            sys.stdout.flush()
            time.sleep(refresh_seconds)

    except KeyboardInterrupt:
        print("\n\nShutting down...", flush=True)
        display.clear()
        print("Display cleared. Goodbye!", flush=True)


if __name__ == '__main__':
    main()

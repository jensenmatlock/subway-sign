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

# Row Y positions for 32-pixel height display (3 rows of ~10px each)
ROW_POSITIONS = {
    'row1': 0,
    'row2': 11,
    'row3': 22,
}


class SubwayDisplay:
    """Manages the LED matrix display for subway arrivals."""

    def __init__(self):
        self.matrix = None
        self.canvas = None
        self.font = None
        self.font_small = None

        if HAS_MATRIX:
            self._init_matrix()

    def _init_matrix(self):
        """Initialize the RGB LED matrix."""
        options = RGBMatrixOptions()
        options.rows = CONFIG['display']['rows']
        options.cols = CONFIG['display']['cols']
        options.brightness = CONFIG['display']['brightness']
        options.gpio_slowdown = CONFIG['display']['gpio_slowdown']
        options.hardware_mapping = CONFIG['display'].get('hardware_mapping', 'regular')
        options.drop_privileges = False

        self.matrix = RGBMatrix(options=options)
        self.canvas = self.matrix.CreateFrameCanvas()

        # Load fonts from rpi-rgb-led-matrix fonts directory
        font_dir = Path.home() / 'rpi-rgb-led-matrix' / 'fonts'
        self.font = graphics.Font()
        self.font.LoadFont(str(font_dir / '5x7.bdf'))

        # Smaller font for "min" text if available
        self.font_small = graphics.Font()
        try:
            self.font_small.LoadFont(str(font_dir / '4x6.bdf'))
        except:
            self.font_small = self.font

    def draw_line_bullet(self, x, y, line):
        """
        Draw a colored circle with the line letter.
        The bullet is 7x7 pixels centered at (x+3, y+3).
        """
        if not HAS_MATRIX:
            return 8  # Return width for simulation

        color = LINE_COLORS.get(line, (255, 255, 255))

        # Draw filled circle (approximated with horizontal lines)
        # Circle pattern for 7x7:
        #   ..XXX..  (row 0: 3 pixels)
        #   .XXXXX.  (row 1: 5 pixels)
        #   XXXXXXX  (row 2-4: 7 pixels)
        #   .XXXXX.  (row 5: 5 pixels)
        #   ..XXX..  (row 6: 3 pixels)
        circle_pattern = [
            (2, 3),   # row 0: start at x+2, width 3
            (1, 5),   # row 1: start at x+1, width 5
            (0, 7),   # row 2: full width
            (0, 7),   # row 3: full width
            (0, 7),   # row 4: full width
            (1, 5),   # row 5
            (2, 3),   # row 6
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

        # Center the letter in the bullet (font is 5 wide, bullet is 7)
        graphics.DrawText(self.canvas, self.font, x + 1, y + 6, text_color, line)

        return 8  # Bullet width + 1px spacing

    def draw_time(self, x, y, minutes):
        """Draw arrival time in minutes."""
        if not HAS_MATRIX:
            return

        white = graphics.Color(200, 200, 200)

        if minutes < 1:
            text = "Now"
        elif minutes == 1:
            text = "1m"
        else:
            text = f"{minutes}m"

        graphics.DrawText(self.canvas, self.font, x, y + 6, white, text)

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
            graphics.DrawText(self.canvas, self.font, x, y + 6, gray, "---")
            return

        # Group arrivals by route
        by_route = {}
        for arrival in arrivals:
            route = arrival['route']
            if route not in by_route:
                by_route[route] = []
            by_route[route].append(arrival['minutesUntil'])

        # Draw each route's bullet and times
        for route, times in by_route.items():
            if x > 50:  # Don't overflow the display
                break

            # Draw the line bullet
            x += self.draw_line_bullet(x, y, route)

            # Draw up to 2 arrival times for this route
            for i, mins in enumerate(times[:2]):
                if mins < 1:
                    time_text = "Now"
                else:
                    time_text = f"{mins}"

                white = graphics.Color(200, 200, 200)
                graphics.DrawText(self.canvas, self.font, x, y + 6, white, time_text)
                x += len(time_text) * 5 + 2  # 5px per char + spacing

            x += 3  # Space before next route

    def draw_error(self, message):
        """Display an error message."""
        if not HAS_MATRIX:
            print(f"ERROR: {message}")
            return

        red = graphics.Color(255, 0, 0)
        graphics.DrawText(self.canvas, self.font, 2, 16, red, message[:12])

    def update(self, data):
        """Update the display with new arrival data."""
        if HAS_MATRIX:
            self.canvas.Clear()

        if not data or 'rows' not in data:
            self.draw_error("NO DATA")
            if HAS_MATRIX:
                self.canvas = self.matrix.SwapOnVSync(self.canvas)
            return

        # Draw each row
        for row_key in ['row1', 'row2', 'row3']:
            row_data = data['rows'].get(row_key, {})
            arrivals = row_data.get('arrivals', [])
            self.draw_row(row_key, arrivals)

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
            timeout=10
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

    try:
        while True:
            data = fetch_arrivals()

            if data:
                print(f"[{time.strftime('%H:%M:%S')}] Updated arrivals:", flush=True)
                display.update(data)
                sys.stdout.flush()
            else:
                display.draw_error("NO DATA")

            time.sleep(refresh_seconds)

    except KeyboardInterrupt:
        print("\n\nShutting down...", flush=True)
        display.clear()
        print("Display cleared. Goodbye!", flush=True)


if __name__ == '__main__':
    main()

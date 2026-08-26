# NYC Subway Sign

Real-time NYC subway arrival display for Raspberry Pi with RGB LED matrix.

![Display Layout](https://img.shields.io/badge/Display-64x32_LED-blue)
![Node.js](https://img.shields.io/badge/Node.js-20.x-green)
![License](https://img.shields.io/badge/License-MIT-yellow)

```
┌────────────────────────────────────────────────────────────┐
│  Ⓑ  7m  17m                                                │ Row 1: B train
├────────────────────────────────────────────────────────────┤
│  Ⓐ  3m   Ⓒ  8m                                             │ Row 2: A/C trains
├────────────────────────────────────────────────────────────┤
│  ①  2  5   ②  4  9                                          │ Row 3: 1 local / 2,3 express
└────────────────────────────────────────────────────────────┘
```

## Features

- Real-time arrival data from MTA GTFS-RT feeds (no API key required)
- Configurable station and line groupings
- Official MTA line colors
- Auto-start on boot via systemd
- Local development/simulation mode

## Hardware

| Component | Specification |
|-----------|---------------|
| Raspberry Pi | Pi Zero 2 WH, Pi 3B+, or Pi 4 |
| LED Matrix | 64x32 RGB, P4 pitch, HUB75 interface |
| Driver | HUB75 RGB Matrix Adapter Board (or Adafruit Bonnet) |
| Power | 5V 4A power supply, 2.1mm barrel jack |
| MicroSD Card | 16GB+ Class 10 |

**Note on driver boards:** This project supports both generic HUB75 adapter boards (`"hardware_mapping": "regular"` in config) and the Adafruit RGB Matrix Bonnet (`"hardware_mapping": "adafruit-hat"`). Most Amazon HUB75 adapter boards use the `regular` pinout.

## Project Structure

```
subway-sign/
├── config.json              # Station & display configuration
├── server/                  # Node.js API server
│   ├── index.js
│   ├── routes/
│   │   └── api.js           # API endpoints (background feed refresh)
│   ├── lib/
│   │   ├── gtfs-fetcher.js  # MTA feed fetcher (per-feed last-good cache)
│   │   ├── arrival-parser.js
│   │   ├── weather.js       # NWS weather fetcher
│   │   └── station-lookup.js
│   └── test/                # node --test suites
├── display/                 # Python LED matrix display
│   ├── main.py
│   ├── requirements.txt
│   └── test_*.py            # unittest suites
└── scripts/                 # Setup & service install scripts
    ├── setup-pi.sh          # One-time Pi setup
    ├── install-services.sh  # Generates & installs systemd services
    └── deploy.sh            # Auto-deploy (git pull + restart)
```

## Quick Start (Local Development)

Test the API server on your local machine before deploying to the Pi:

```bash
# Clone the repo
git clone https://github.com/jensenmatlock/subway-sign.git
cd subway-sign

# Install dependencies
cd server
npm install

# Start the server
npm start
```

Then visit: http://localhost:3000/api/arrivals

### API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/arrivals` | Formatted arrivals for display |
| `GET /api/arrivals/raw` | Raw arrival data (debug) |
| `GET /api/health` | Health check with feed status |
| `GET /api/config` | Current configuration |
| `GET /api/stations?search=<term>` | Search for station IDs |

## Raspberry Pi Setup

### 1. Flash Raspberry Pi OS

Use [Raspberry Pi Imager](https://www.raspberrypi.com/software/) to flash **Raspberry Pi OS Lite (64-bit)**.

In the imager settings (gear icon), configure:
- Hostname: `subwaysign`
- Enable SSH
- Set username/password
- Configure WiFi
- Set timezone to `America/New_York`

### 2. Hardware Assembly

1. Attach the HUB75 adapter board to the Pi's GPIO header
2. Connect the 16-pin ribbon cable from adapter to matrix INPUT
3. Connect matrix power wires to adapter power output terminals (red→+, black→-)
4. Connect 5V 4A power supply to adapter barrel jack or USB-C input

### 3. Software Installation

SSH into your Pi and run:

```bash
# Install git (not included in Raspberry Pi OS Lite)
sudo apt update && sudo apt install -y git

# Clone the repo
cd ~
git clone https://github.com/jensenmatlock/subway-sign.git
cd subway-sign

# Run setup script (installs Node.js, Python deps, builds LED matrix library)
sudo bash scripts/setup-pi.sh

# IMPORTANT: Reboot is required before the display will work
# (disables onboard audio which conflicts with LED matrix GPIO)
sudo reboot
```

After reboot:

```bash
# Install systemd services (generates service files with correct paths/user)
cd ~/subway-sign
sudo bash scripts/install-services.sh

# Start the services (and the auto-deploy timer)
sudo systemctl start subway-server subway-display
sudo systemctl start subway-deploy.timer
```

The sign will now auto-start on boot, and the Pi will pull updates from GitHub every 5 minutes (see [Auto-Deploy](#auto-deploy)).

### 4. Verify It's Working

```bash
# Check service status
sudo systemctl status subway-server
sudo systemctl status subway-display

# View logs
sudo journalctl -u subway-server -f
sudo journalctl -u subway-display -f

# Test API
curl http://localhost:3000/api/arrivals
```

## Auto-Deploy

A systemd timer (`subway-deploy.timer`) runs `scripts/deploy.sh` every 5 minutes. The script:

1. `git fetch` and compare local vs `origin/<branch>`. Exit immediately if up to date.
2. Fast-forward `git pull` (refuses if local has diverged — protects hand-edits).
3. Run `npm install` if `server/package*.json` changed.
4. Run `pip install` if `display/requirements.txt` changed.
5. `systemctl restart subway-server subway-display` if any code or `config.json` changed. README-only updates don't trigger a restart.

Push to GitHub and within ~5 minutes the Pi reflects the change.

```bash
# View deploy history
sudo journalctl -u subway-deploy -n 50

# See when the next deploy will run
sudo systemctl list-timers subway-deploy.timer

# Trigger a deploy immediately
sudo systemctl start subway-deploy.service

# Disable auto-deploy
sudo systemctl disable --now subway-deploy.timer
```

If you edit files directly on the Pi, the next deploy will fail with a non-fast-forward error (intentional — local edits are preserved). Either commit and push them, or `git reset --hard origin/<branch>` to discard them.

## Configuration

Edit `config.json` to customize your display:

### Change Station

```json
{
  "stations": {
    "my_station": {
      "id": "A28",
      "name": "34 St - Penn Station",
      "lines": ["A", "C", "E"]
    }
  }
}
```

**Finding your station ID:**
```bash
curl "http://localhost:3000/api/stations?search=penn"
```

### Change Direction

```json
{
  "direction": "N"  // "N" = Uptown, "S" = Downtown
}
```

### Change Line Groupings

```json
{
  "layout": {
    "row1": {
      "station": "my_station",
      "lines": ["A"],
      "feed": "ace",
      "label": "A Express"
    }
  }
}
```

### Group Lines Together

Merge arrival times from multiple lines into one display entry. Useful for express/local pairs that share a station:

```json
{
  "layout": {
    "row3": {
      "station": "72_broadway",
      "lines": ["1", "2", "3"],
      "groups": [
        { "lines": ["1"] },
        { "lines": ["2", "3"] }
      ],
      "feed": "123",
      "label": "1/2/3 Downtown"
    }
  }
}
```

This shows the 1 train with its own bullet and times, and merges 2/3 express times under a single bullet. Without `groups`, each line gets its own bullet (which may overflow on a 64-pixel display).

### Schedule On/Off

Blank train arrivals outside configured hours so the display isn't distracting at night. Row 1 stays lit: the weather indicator (top-right) runs continuously, and the current time (top-left, 12-hour, e.g. `10:07p`) is added off-schedule. Both drop to a muted glow off-schedule (`DIM_FACTOR` in `display/main.py`, 0.25) so they're unobtrusive in a dark room. The clock follows the refresh interval, so it can lag a minute rollover by up to `server.refreshInterval`. Times are local Pi time (set timezone to `America/New_York` in the imager).

```json
{
  "schedule": {
    "enabled": true,
    "weekday": { "on": "06:30", "off": "21:00" },
    "weekend": { "on": "09:00", "off": "22:00" }
  }
}
```

The server keeps polling MTA during off-hours, so the first frame after wake-up is current. Set `"enabled": false` to disable scheduling and keep the display on continuously.

### Weather

Top-right of row 1 shows the current temperature and a small precipitation glyph — a droplet for rain, a snowflake for snow — when precipitation is at least 40% likely in the next hour. Data comes from the National Weather Service (`api.weather.gov`) — no API key, US-only, 10-minute server-side cache.

```json
{
  "weather": {
    "enabled": true,
    "lat": 40.7785,
    "lon": -73.9821
  }
}
```

If NWS is unreachable the display falls back to the last known reading for up to 60 minutes, after which the temperature and glyph disappear entirely rather than show a stale value. Set `"enabled": false` to skip weather entirely.

### Adjust Brightness

```json
{
  "display": {
    "brightness": 30  // 1-100, lower for bedroom use
  }
}
```

### Reduce Flicker

The LED panel is refreshed by a CPU thread, so on a weaker Pi (e.g. Zero 2 W)
the refresh can flicker. Two display options help:

```json
{
  "display": {
    "limit_refresh_rate_hz": 100,  // cap the rate so it stays steady (0 = unlimited)
    "pwm_bits": 11                 // lower (e.g. 8) trades color depth for refresh headroom
  }
}
```

Capping `limit_refresh_rate_hz` to a steadily-sustainable rate removes the
fluctuation that shows as flicker, with no color-depth cost. For the steady
between-update flicker, also reserve a CPU core for the refresh thread with
`isolcpus=3` in `/boot/firmware/cmdline.txt` (added automatically by
`setup-pi.sh`; requires a reboot).

## MTA Feed Reference

| Lines | Feed Key | Feed URL |
|-------|----------|----------|
| 1, 2, 3, 4, 5, 6, S | `123` | `nyct%2Fgtfs` |
| A, C, E | `ace` | `nyct%2Fgtfs-ace` |
| B, D, F, M | `bdfm` | `nyct%2Fgtfs-bdfm` |
| G | `g` | `nyct%2Fgtfs-g` |
| J, Z | `jz` | `nyct%2Fgtfs-jz` |
| L | `l` | `nyct%2Fgtfs-l` |
| N, Q, R, W | `nqrw` | `nyct%2Fgtfs-nqrw` |
| SIR | `si` | `nyct%2Fgtfs-si` |

## Troubleshooting

| Problem | Solution |
|---------|----------|
| No display output | Check ribbon cable orientation, verify power connections |
| Flickering display | See [Reduce Flicker](#reduce-flicker): set `limit_refresh_rate_hz` + `isolcpus=3`; as a last resort lower `pwm_bits` or adjust `gpio_slowdown` |
| "Cannot connect to API" | Ensure server is running: `sudo systemctl status subway-server` |
| Empty arrivals | Verify station ID and direction in config |
| Very dim display | Increase brightness, verify 4A power supply |

## Development

### Run server in dev mode (auto-reload)
```bash
cd server
npm run dev
```

### Test display in simulation mode (no Pi required)
```bash
cd display
pip install -r requirements.txt
python main.py  # Prints to console instead of LED matrix
```

### Run tests
```bash
# Server (Node's built-in test runner, no extra deps)
cd server
npm test

# Display (Python unittest, no Pi required)
cd display
python test_resilience.py
python test_schedule.py
python test_weather.py
```

## License

MIT

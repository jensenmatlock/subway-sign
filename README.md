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
│   └── lib/
│       ├── gtfs-fetcher.js  # MTA feed fetcher
│       ├── arrival-parser.js
│       └── station-lookup.js
├── display/                 # Python LED matrix display
│   ├── main.py
│   └── requirements.txt
└── scripts/                 # Setup & service install scripts
    ├── setup-pi.sh          # One-time Pi setup
    └── install-services.sh  # Generates & installs systemd services
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

# Start the services
sudo systemctl start subway-server subway-display
```

The sign will now auto-start on boot.

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

### Adjust Brightness

```json
{
  "display": {
    "brightness": 30  // 1-100, lower for bedroom use
  }
}
```

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
| Flickering display | Increase `gpio_slowdown` in config (try 4, 5, or 6) |
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

## License

MIT

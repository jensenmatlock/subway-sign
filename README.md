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
│  ①  2m  5m   ②  9m                                         │ Row 3: 1/2/3 trains
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
| Raspberry Pi | Pi 3B+, Pi 4, or Pi Zero 2W |
| LED Matrix | 64x32 RGB, P4 pitch, HUB75 interface |
| Driver | Adafruit RGB Matrix Bonnet |
| Power | 5V 4A power supply |

**Recommended purchase:** [Adafruit](https://www.adafruit.com/) for US shipping, or search "64x32 P4 RGB LED Matrix HUB75" on Amazon/AliExpress.

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
│   └── main.py
├── scripts/                 # Setup scripts
│   ├── setup-pi.sh
│   └── install-services.sh
└── services/                # systemd service files
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

1. Attach the RGB Matrix Bonnet to the Pi's GPIO header
2. Connect the 16-pin ribbon cable from Bonnet to matrix INPUT
3. Connect matrix power wires to Bonnet screw terminals (red→+, black→-)
4. Connect 5V 4A power supply to Bonnet barrel jack

### 3. Software Installation

SSH into your Pi and run:

```bash
# Clone the repo
cd ~
git clone https://github.com/jensenmatlock/subway-sign.git
cd subway-sign

# Run setup script (installs Node.js, builds LED matrix library)
sudo ./scripts/setup-pi.sh

# Reboot (required for audio disable to take effect)
sudo reboot
```

After reboot:

```bash
# Install systemd services
cd ~/subway-sign
sudo ./scripts/install-services.sh

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

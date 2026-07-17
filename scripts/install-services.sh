#!/bin/bash
# Install systemd services for NYC Subway Sign
# Run with: sudo bash install-services.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CURRENT_USER="${SUDO_USER:-$USER}"
CURRENT_GROUP="$(id -gn "$CURRENT_USER")"

echo "Installing NYC Subway Sign services..."
echo "Project directory: $PROJECT_DIR"
echo "User: $CURRENT_USER"
echo ""

# Generate service files with correct paths and user
echo "Generating service files..."

cat > /etc/systemd/system/subway-server.service <<EOF
[Unit]
Description=NYC Subway Sign API Server
Documentation=https://github.com/jensenmatlock/subway-sign
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$CURRENT_USER
Group=$CURRENT_GROUP
WorkingDirectory=$PROJECT_DIR/server
ExecStart=/usr/bin/node index.js
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
Environment=NODE_ENV=production
# Contain the Node server's memory. If its RSS creeps past the hard cap, the
# kernel kills it and Restart=always brings it back in ~10s (a brief NO DATA
# blip) instead of the whole Pi starving into a zram/CPU-starvation livelock
# that only a power cycle clears. Requires the memory cgroup controller enabled
# in setup-pi.sh (cgroup_enable=memory). Tune to the observed steady-state RSS.
MemoryAccounting=yes
MemoryHigh=160M
MemoryMax=200M

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/subway-display.service <<EOF
[Unit]
Description=NYC Subway Sign LED Display
Documentation=https://github.com/jensenmatlock/subway-sign
After=network-online.target subway-server.service
Wants=network-online.target
Requires=subway-server.service

[Service]
Type=simple
# Must run as root for GPIO access to LED matrix
User=root
Group=root
WorkingDirectory=$PROJECT_DIR/display
ExecStart=/usr/bin/python3 main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
# Give the server time to start before display tries to connect
ExecStartPre=/bin/sleep 5

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/subway-deploy.service <<EOF
[Unit]
Description=NYC Subway Sign Auto-Deploy (git pull + restart)
Documentation=https://github.com/jensenmatlock/subway-sign
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
# Run as root so we can restart subway-server / subway-display.
# git operates on $PROJECT_DIR via safe.directory inside deploy.sh.
ExecStart=/bin/bash $PROJECT_DIR/scripts/deploy.sh
StandardOutput=journal
StandardError=journal
EOF

cat > /etc/systemd/system/subway-deploy.timer <<EOF
[Unit]
Description=Run NYC Subway Sign Auto-Deploy every 5 minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
Unit=subway-deploy.service

[Install]
WantedBy=timers.target
EOF

# Reload systemd
echo "Reloading systemd..."
sudo systemctl daemon-reload

# Enable services
echo "Enabling services..."
sudo systemctl enable subway-server
sudo systemctl enable subway-display
sudo systemctl enable subway-deploy.timer

echo ""
echo "Services installed successfully!"
echo ""
echo "Commands:"
echo "  sudo systemctl start subway-server subway-display  # Start both services"
echo "  sudo systemctl start subway-deploy.timer           # Start auto-deploy timer"
echo "  sudo systemctl stop subway-server subway-display   # Stop both services"
echo "  sudo systemctl status subway-server                # Check server status"
echo "  sudo systemctl status subway-display               # Check display status"
echo "  sudo systemctl list-timers subway-deploy.timer     # When auto-deploy will run next"
echo "  sudo journalctl -u subway-server -f                # View server logs"
echo "  sudo journalctl -u subway-display -f               # View display logs"
echo "  sudo journalctl -u subway-deploy -f                # View auto-deploy logs"

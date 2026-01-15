#!/bin/bash
# Install systemd services for NYC Subway Sign
# Run with: sudo ./install-services.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "Installing NYC Subway Sign services..."
echo "Project directory: $PROJECT_DIR"

# Copy service files
echo "Copying service files..."
sudo cp "$PROJECT_DIR/services/subway-server.service" /etc/systemd/system/
sudo cp "$PROJECT_DIR/services/subway-display.service" /etc/systemd/system/

# Reload systemd
echo "Reloading systemd..."
sudo systemctl daemon-reload

# Enable services
echo "Enabling services..."
sudo systemctl enable subway-server
sudo systemctl enable subway-display

echo ""
echo "Services installed successfully!"
echo ""
echo "Commands:"
echo "  sudo systemctl start subway-server subway-display  # Start both services"
echo "  sudo systemctl stop subway-server subway-display   # Stop both services"
echo "  sudo systemctl status subway-server                # Check server status"
echo "  sudo systemctl status subway-display               # Check display status"
echo "  sudo journalctl -u subway-server -f                # View server logs"
echo "  sudo journalctl -u subway-display -f               # View display logs"

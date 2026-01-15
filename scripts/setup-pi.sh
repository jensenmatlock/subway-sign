#!/bin/bash
# Initial setup script for Raspberry Pi
# Run after cloning the repo to a fresh Pi

set -e

echo "========================================"
echo "NYC Subway Sign - Raspberry Pi Setup"
echo "========================================"
echo ""

# Check if running on Raspberry Pi
if ! grep -q "Raspberry Pi" /proc/cpuinfo 2>/dev/null; then
    echo "Warning: This doesn't appear to be a Raspberry Pi"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "Step 1: System update"
echo "---------------------"
sudo apt update && sudo apt upgrade -y

echo ""
echo "Step 2: Install dependencies"
echo "----------------------------"
sudo apt install -y git build-essential python3-dev python3-pip python3-pillow

echo ""
echo "Step 3: Install Node.js 20.x"
echo "----------------------------"
if ! command -v node &> /dev/null; then
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt install -y nodejs
else
    echo "Node.js already installed: $(node --version)"
fi

echo ""
echo "Step 4: Disable onboard audio (conflicts with LED matrix)"
echo "---------------------------------------------------------"
if ! grep -q "blacklist snd_bcm2835" /etc/modprobe.d/blacklist-rgb-matrix.conf 2>/dev/null; then
    echo "blacklist snd_bcm2835" | sudo tee /etc/modprobe.d/blacklist-rgb-matrix.conf
    sudo update-initramfs -u
    echo "Audio disabled - will take effect after reboot"
else
    echo "Audio already disabled"
fi

echo ""
echo "Step 5: Install rpi-rgb-led-matrix library"
echo "------------------------------------------"
if [ ! -d "/home/pi/rpi-rgb-led-matrix" ]; then
    cd /home/pi
    git clone https://github.com/hzeller/rpi-rgb-led-matrix.git
    cd rpi-rgb-led-matrix
    make
    make build-python PYTHON=$(which python3)
    sudo make install-python PYTHON=$(which python3)
else
    echo "rpi-rgb-led-matrix already installed"
fi

echo ""
echo "Step 6: Install Node.js dependencies"
echo "------------------------------------"
cd "$PROJECT_DIR/server"
npm install --production

echo ""
echo "Step 7: Install Python dependencies"
echo "-----------------------------------"
pip3 install -r "$PROJECT_DIR/display/requirements.txt"

echo ""
echo "Step 8: Verify installations"
echo "----------------------------"
echo "Node.js: $(node --version)"
echo "npm: $(npm --version)"
echo "Python3: $(python3 --version)"
python3 -c "from rgbmatrix import RGBMatrix; print('rgbmatrix: OK')" || echo "rgbmatrix: Not installed (will work after reboot)"

echo ""
echo "========================================"
echo "Setup complete!"
echo "========================================"
echo ""
echo "Next steps:"
echo "1. Reboot: sudo reboot"
echo "2. Test the server: cd ~/subway-sign/server && npm start"
echo "3. Test the display: sudo python3 ~/subway-sign/display/main.py"
echo "4. Install services: sudo ~/subway-sign/scripts/install-services.sh"
echo ""

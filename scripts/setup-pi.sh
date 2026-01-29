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
CURRENT_USER="${SUDO_USER:-$USER}"
USER_HOME="$(eval echo ~"$CURRENT_USER")"

echo "Project directory: $PROJECT_DIR"
echo "User: $CURRENT_USER"
echo "Home: $USER_HOME"
echo ""

echo "Step 1: System update"
echo "---------------------"
sudo apt update && sudo apt upgrade -y

echo ""
echo "Step 2: Install dependencies"
echo "----------------------------"
sudo apt install -y git build-essential python3-dev python3-pip python3-pillow cython3 python3-setuptools

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
RGB_MATRIX_DIR="$USER_HOME/rpi-rgb-led-matrix"
if [ ! -d "$RGB_MATRIX_DIR" ]; then
    cd "$USER_HOME"
    git clone https://github.com/hzeller/rpi-rgb-led-matrix.git
    cd rpi-rgb-led-matrix
    make
    make build-python PYTHON=$(which python3)
    sudo make install-python PYTHON=$(which python3)
else
    echo "rpi-rgb-led-matrix already installed at $RGB_MATRIX_DIR"
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
echo "IMPORTANT: You must reboot before running the display."
echo "  sudo reboot"
echo ""
echo "After reboot:"
echo "  1. Test the server: cd $PROJECT_DIR/server && npm start"
echo "  2. Test the display: sudo python3 $PROJECT_DIR/display/main.py"
echo "  3. Install services: sudo bash $PROJECT_DIR/scripts/install-services.sh"
echo ""

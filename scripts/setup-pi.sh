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
sudo apt install -y git build-essential python3-dev python3-pip python3-pillow cython3 python3-setuptools dnsmasq-base

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
echo "Step 4: Configure boot cmdline (disable audio, isolate CPU core, enable memory cgroup)"
echo "--------------------------------------------------------------------------------------"
# Onboard audio shares the GPIO/PWM the matrix needs - blacklist it.
if ! grep -q "blacklist snd_bcm2835" /etc/modprobe.d/blacklist-rgb-matrix.conf 2>/dev/null; then
    echo "blacklist snd_bcm2835" | sudo tee /etc/modprobe.d/blacklist-rgb-matrix.conf
    sudo update-initramfs -u
    echo "Audio disabled - will take effect after reboot"
else
    echo "Audio already disabled"
fi

# Reserve CPU core 3 for the matrix refresh thread. Without this the kernel
# scheduler preempts the refresh thread on a shared core, causing visible
# flicker (rpi-rgb-led-matrix recommends isolcpus). Boot partition may be
# mounted read-only, so remount rw to edit. Takes effect after reboot.
CMDLINE=/boot/firmware/cmdline.txt
[ -f "$CMDLINE" ] || CMDLINE=/boot/cmdline.txt
if [ -f "$CMDLINE" ] && ! grep -q "isolcpus=" "$CMDLINE"; then
    sudo mount -o remount,rw "$(dirname "$CMDLINE")" 2>/dev/null || true
    sudo sed -i 's/[[:space:]]*$/ isolcpus=3/' "$CMDLINE"
    sync
    echo "Isolated CPU core 3 for the matrix - will take effect after reboot"
else
    echo "CPU core isolation already configured (or cmdline.txt not found)"
fi

# Enable the memory cgroup controller. The Pi's device-tree injects
# cgroup_disable=memory ahead of cmdline.txt, so the kernel boots with no memory
# accounting - MemoryMax/MemoryHigh on the services are silently ignored. Append
# cgroup_enable=memory (parsed after the DTB arg, so it wins) to turn it back on,
# which lets subway-server's memory cap contain a Node RSS creep instead of
# letting it starve the whole Pi into a zram/CPU livelock. Takes effect on reboot.
if [ -f "$CMDLINE" ] && ! grep -q "cgroup_enable=memory" "$CMDLINE"; then
    sudo mount -o remount,rw "$(dirname "$CMDLINE")" 2>/dev/null || true
    sudo sed -i 's/[[:space:]]*$/ cgroup_enable=memory cgroup_memory=1/' "$CMDLINE"
    sync
    echo "Enabled memory cgroup controller - will take effect after reboot"
else
    echo "Memory cgroup controller already enabled (or cmdline.txt not found)"
fi

echo ""
echo "Step 5: Enable local DNS caching (NetworkManager + dnsmasq)"
echo "----------------------------------------------------------"
# The Pi re-resolves a couple of API hostnames every 30s. Without a local cache,
# every lookup hits a remote resolver and intermittently stalls for seconds,
# surfacing as feed timeouts and blank display rows. Cache locally and forward
# misses to reliable public resolvers instead of the DHCP-provided ISP ones.
if [ ! -f /etc/NetworkManager/conf.d/00-dns-cache.conf ]; then
    printf '[main]\ndns=dnsmasq\n' | sudo tee /etc/NetworkManager/conf.d/00-dns-cache.conf > /dev/null
    sudo mkdir -p /etc/NetworkManager/dnsmasq.d
    printf 'server=1.1.1.1\nserver=1.0.0.1\nserver=8.8.8.8\n' | sudo tee /etc/NetworkManager/dnsmasq.d/upstream.conf > /dev/null
    sudo systemctl reload NetworkManager
    echo "Local DNS cache enabled (resolv.conf now points at 127.0.0.1)"
else
    echo "Local DNS cache already configured"
fi

echo ""
echo "Step 6: Install rpi-rgb-led-matrix library"
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
echo "Step 7: Install Node.js dependencies"
echo "------------------------------------"
cd "$PROJECT_DIR/server"
npm install --production

echo ""
echo "Step 8: Install Python dependencies"
echo "-----------------------------------"
pip3 install -r "$PROJECT_DIR/display/requirements.txt"

echo ""
echo "Step 9: Verify installations"
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

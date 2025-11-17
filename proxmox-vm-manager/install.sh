#!/bin/bash
set -e

# Proxmox VM Manager Installation Script

echo "=== Proxmox VM Auto-Start Manager Installation ==="
echo

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "ERROR: This script must be run as root"
    exit 1
fi

# Configuration
INSTALL_DIR="/opt/proxmox-vm-manager"
CONFIG_DIR="/etc/proxmox-vm-manager"
SERVICE_FILE="/etc/systemd/system/proxmox-vm-manager.service"

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo "Installing Proxmox VM Manager..."
echo "  Install directory: $INSTALL_DIR"
echo "  Config directory: $CONFIG_DIR"
echo

# Install Python dependencies
echo "Installing Python dependencies..."
if ! command -v pip3 &> /dev/null; then
    echo "ERROR: pip3 not found. Please install python3-pip first."
    exit 1
fi

pip3 install -r "$SCRIPT_DIR/requirements.txt"

# Create installation directory
echo "Creating installation directory..."
mkdir -p "$INSTALL_DIR"
cp -r "$SCRIPT_DIR/src" "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/src/main.py"

# Create config directory
echo "Creating configuration directory..."
mkdir -p "$CONFIG_DIR"

# Copy example config if no config exists
if [ ! -f "$CONFIG_DIR/config.yaml" ]; then
    echo "Creating default configuration file..."
    cp "$SCRIPT_DIR/config/config.example.yaml" "$CONFIG_DIR/config.yaml"
    echo "  ⚠️  Please edit $CONFIG_DIR/config.yaml with your Proxmox credentials"
else
    echo "  Configuration file already exists at $CONFIG_DIR/config.yaml"
fi

# Install systemd service
echo "Installing systemd service..."
cp "$SCRIPT_DIR/systemd/proxmox-vm-manager.service" "$SERVICE_FILE"
systemctl daemon-reload

echo
echo "=== Installation Complete ==="
echo
echo "Next steps:"
echo "  1. Edit the configuration file:"
echo "     nano $CONFIG_DIR/config.yaml"
echo
echo "  2. Test the configuration:"
echo "     cd $INSTALL_DIR"
echo "     python3 src/main.py --config $CONFIG_DIR/config.yaml --test"
echo
echo "  3. Enable and start the service:"
echo "     systemctl enable proxmox-vm-manager"
echo "     systemctl start proxmox-vm-manager"
echo
echo "  4. Check service status:"
echo "     systemctl status proxmox-vm-manager"
echo
echo "  5. View logs:"
echo "     journalctl -u proxmox-vm-manager -f"
echo

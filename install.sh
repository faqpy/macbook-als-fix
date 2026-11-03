#!/usr/bin/env bash
# Simple install script for macbook-als

set -e

# Resolve files relative to this script, not the directory it was invoked from.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# Ensure running with root privileges
if [ "$EUID" -ne 0 ]; then
  echo "[!] Please run as root: sudo ./install.sh"
  exit 1
fi

echo "==> Installing macbook-als..."

# 1. Install executable
install -Dm755 "$SCRIPT_DIR/macbook-als.py" /usr/local/bin/macbook-als

# 2. Install default configuration (do not overwrite existing custom config)
if [ ! -f /etc/macbook-als.conf ]; then
  install -Dm644 "$SCRIPT_DIR/macbook-als.conf" /etc/macbook-als.conf
  echo "    Installed default config to /etc/macbook-als.conf"
else
  echo "    Existing /etc/macbook-als.conf kept (not overwritten)"
fi

# 3. Install systemd service
install -Dm644 "$SCRIPT_DIR/macbook-als.service" /etc/systemd/system/macbook-als.service

# 4. Reload systemd daemon
systemctl daemon-reload

# Apply updated code immediately when the service is already running.
if systemctl is-active --quiet macbook-als.service; then
  systemctl restart macbook-als.service
fi

echo "==> Installation complete!"
echo ""
echo "To start and enable the daemon right now, run:"
echo "    sudo systemctl enable --now macbook-als"
echo ""
echo "To check service status:"
echo "    sudo systemctl status macbook-als"

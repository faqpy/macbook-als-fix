#!/usr/bin/env bash
# Simple install script for macbook-als

set -e

# Ensure running with root privileges
if [ "$EUID" -ne 0 ]; then
  echo "[!] Please run as root: sudo ./install.sh"
  exit 1
fi

echo "==> Installing macbook-als..."

# 1. Install executable
install -Dm755 macbook-als.py /usr/local/bin/macbook-als

# 2. Install default configuration (do not overwrite existing custom config)
if [ ! -f /etc/macbook-als.conf ]; then
  install -Dm644 macbook-als.conf /etc/macbook-als.conf
  echo "    Installed default config to /etc/macbook-als.conf"
else
  echo "    Existing /etc/macbook-als.conf kept (not overwritten)"
fi

# 3. Install systemd service
install -Dm644 macbook-als.service /etc/systemd/system/macbook-als.service

# 4. Reload systemd daemon
systemctl daemon-reload

echo "==> Installation complete!"
echo ""
echo "To start and enable the daemon right now, run:"
echo "    sudo systemctl enable --now macbook-als"
echo ""
echo "To check service status:"
echo "    sudo systemctl status macbook-als"

#!/usr/bin/env bash
# Simple uninstall script for macbook-als

set -e

if [ "$EUID" -ne 0 ]; then
  echo "[!] Please run as root: sudo ./uninstall.sh"
  exit 1
fi

echo "==> Uninstalling macbook-als..."

# Stop and disable service if running
if systemctl is-active --quiet macbook-als.service 2>/dev/null; then
  echo "    Stopping active macbook-als service..."
  systemctl stop macbook-als.service
fi

if systemctl is-enabled --quiet macbook-als.service 2>/dev/null; then
  echo "    Disabling macbook-als service..."
  systemctl disable macbook-als.service
fi

# Remove binary and systemd service
rm -f /usr/local/bin/macbook-als
rm -f /etc/systemd/system/macbook-als.service

systemctl daemon-reload

echo "    Removed /usr/local/bin/macbook-als and service unit."
echo "    Note: /etc/macbook-als.conf has been preserved. Remove manually if desired:"
echo "    sudo rm -f /etc/macbook-als.conf"
echo ""
echo "==> Uninstallation complete."

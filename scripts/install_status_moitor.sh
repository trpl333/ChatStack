#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="status_monitor.service"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}"
REPO_DIR="${1:-/opt/ChatStack}"

echo "[*] Installing ChatStack Status Monitor from ${REPO_DIR}"

sudo mkdir -p /var/lib/chatstack
sudo chown root:root /var/lib/chatstack
sudo chmod 755 /var/lib/chatstack

if [[ -f "${REPO_DIR}/deploy/systemd/${SERVICE_NAME}" ]]; then
  sudo cp "${REPO_DIR}/deploy/systemd/${SERVICE_NAME}" "${SERVICE_PATH}"
else
  echo "ERROR: ${REPO_DIR}/deploy/systemd/${SERVICE_NAME} not found"
  exit 1
fi

sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}"
sudo systemctl restart "${SERVICE_NAME}"

echo "[√] Status monitor installed and started."
echo "    Logs: sudo journalctl -fu ${SERVICE_NAME}"
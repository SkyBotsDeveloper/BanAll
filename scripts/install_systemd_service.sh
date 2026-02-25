#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE="$ROOT_DIR/deploy/systemd/banall-bot.service.template"

SERVICE_NAME="${1:-banall-bot}"
APP_DIR="${2:-$ROOT_DIR}"
APP_USER="${3:-$(whoami)}"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}.service"

if [[ ! -f "$TEMPLATE" ]]; then
  echo "[ERROR] Template not found: $TEMPLATE"
  exit 1
fi

TMP_FILE="$(mktemp)"
trap 'rm -f "$TMP_FILE"' EXIT

sed \
  -e "s#__APP_DIR__#${APP_DIR}#g" \
  -e "s#__APP_USER__#${APP_USER}#g" \
  "$TEMPLATE" > "$TMP_FILE"

echo "[INFO] Installing service to ${SERVICE_PATH}"
sudo cp "$TMP_FILE" "$SERVICE_PATH"

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"

sudo systemctl --no-pager --full status "$SERVICE_NAME" || true

echo "[OK] Service installed. Logs: sudo journalctl -u ${SERVICE_NAME} -f"


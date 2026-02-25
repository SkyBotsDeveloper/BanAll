#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

SERVICE_NAME="${1:-banall-bot}"

if [[ ! -d .git ]]; then
  echo "[ERROR] This directory is not a git repository."
  exit 1
fi

git pull --ff-only

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

mkdir -p logs
touch bot.log
chmod +x scripts/run_bot.sh

python scripts/preflight.py
sudo systemctl restart "$SERVICE_NAME"
sudo systemctl --no-pager --full status "$SERVICE_NAME" || true

echo "[OK] Update complete."


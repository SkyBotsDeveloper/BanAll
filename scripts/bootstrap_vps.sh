#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if command -v apt-get >/dev/null 2>&1; then
  echo "[INFO] Detected apt-get. Installing system packages (requires sudo)."
  sudo apt-get update
  sudo apt-get install -y python3 python3-venv python3-pip
fi

python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
pip install -r requirements.txt

mkdir -p logs
python scripts/preflight.py

echo "[OK] Bootstrap complete."
echo "[NEXT] Create .env from .env.example and run: ./scripts/run_bot.sh"


#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -f ".env" ]]; then
  echo "[ERROR] .env not found. Copy .env.example to .env and fill secrets."
  exit 1
fi

if [[ ! -d ".venv" ]]; then
  echo "[ERROR] .venv not found. Run scripts/bootstrap_vps.sh first."
  exit 1
fi

export PYTHONUNBUFFERED=1
exec "$ROOT_DIR/.venv/bin/python" "$ROOT_DIR/main.py"


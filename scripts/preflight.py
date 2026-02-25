#!/usr/bin/env python3
"""Fail-fast environment validation for deployment."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import Config  # noqa: E402


def main() -> int:
    try:
        cfg = Config()
    except Exception as exc:
        print(f"[ERROR] Configuration invalid: {exc}")
        return 1

    Path("logs").mkdir(parents=True, exist_ok=True)

    print("[OK] Configuration loaded")
    print(f"[OK] Workers: {cfg.WORKERS}")
    print(f"[OK] Max concurrent operations: {cfg.MAX_CONCURRENT_OPERATIONS}")
    print(f"[OK] Sudo users configured: {len(cfg.SUDO_USERS)}")
    print(f"[OK] Chatbot enabled: {cfg.CHATBOT_ENABLED}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


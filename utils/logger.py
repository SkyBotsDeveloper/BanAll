"""Structured logging and lightweight metrics storage for the bot."""

from __future__ import annotations

import datetime as dt
import json
import logging
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict


class PowerLogger:
    """Thread-safe logger with JSONL action/error logs and aggregate stats."""

    def __init__(self) -> None:
        self.logs_dir = Path("logs")
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        self.runtime_log = Path("bot.log")
        self.action_log = self.logs_dir / "actions.log"
        self.error_log = self.logs_dir / "errors.log"
        self.stats_log = self.logs_dir / "stats.json"

        self._io_lock = threading.Lock()
        self._stats_lock = threading.Lock()

        self._logger = logging.getLogger("banall_bot")
        self._logger.propagate = False
        self._configured = False
        self.configure()

        if not self.stats_log.exists():
            self._init_stats()

    def configure(self, level: str = "INFO", max_bytes: int = 1_048_576, backup_count: int = 5) -> None:
        """Configure rotating runtime logs once at startup."""
        if self._configured:
            # Runtime level can still change across startups in the same process.
            self._logger.setLevel(getattr(logging, level.upper(), logging.INFO))
            return

        self._logger.setLevel(getattr(logging, level.upper(), logging.INFO))

        formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

        file_handler = RotatingFileHandler(
            self.runtime_log,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)

        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)

        self._logger.handlers.clear()
        self._logger.addHandler(file_handler)
        self._logger.addHandler(stream_handler)

        self._configured = True

    def _init_stats(self) -> None:
        stats = {
            "total_operations": 0,
            "total_banned": 0,
            "total_kicked": 0,
            "total_muted": 0,
            "total_deleted_messages": 0,
            "groups_processed": 0,
            "last_operation": None,
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
        self._write_json(self.stats_log, stats)

    def _write_json(self, path: Path, payload: Dict[str, Any]) -> None:
        with self._io_lock:
            with path.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)

    def _read_json(self, path: Path) -> Dict[str, Any]:
        with self._io_lock:
            with path.open("r", encoding="utf-8") as handle:
                return json.load(handle)

    def _append_jsonl(self, path: Path, payload: Dict[str, Any]) -> None:
        # `default=str` prevents crashes when details contain enums or framework objects.
        record = json.dumps(payload, ensure_ascii=True, default=str)
        with self._io_lock:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(record + "\n")

    def log_action(
        self,
        action: str,
        chat_id: int,
        user_id: int,
        details: Dict[str, Any] | None = None,
    ) -> None:
        payload = {
            "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
            "type": "action",
            "action": action,
            "chat_id": chat_id,
            "user_id": user_id,
            "details": details or {},
        }
        self._append_jsonl(self.action_log, payload)
        self._logger.info("action=%s chat=%s user=%s details=%s", action, chat_id, user_id, payload["details"])

    def log_operation(self, operation: str, chat_id: int, stats: Dict[str, int]) -> None:
        payload = {
            "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
            "type": "operation",
            "operation": operation,
            "chat_id": chat_id,
            "stats": stats,
        }
        self._append_jsonl(self.action_log, payload)
        self._logger.info("operation=%s chat=%s stats=%s", operation, chat_id, stats)
        self._update_stats(stats)

    def log_error(self, error: str, context: str = "") -> None:
        payload = {
            "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
            "type": "error",
            "error": error,
            "context": context,
        }
        self._append_jsonl(self.error_log, payload)
        if context:
            self._logger.error("%s | context=%s", error, context)
        else:
            self._logger.error(error)

    def _update_stats(self, delta: Dict[str, int]) -> None:
        with self._stats_lock:
            try:
                stats = self._read_json(self.stats_log)
            except Exception:
                stats = {}

            stats.setdefault("total_operations", 0)
            stats.setdefault("total_banned", 0)
            stats.setdefault("total_kicked", 0)
            stats.setdefault("total_muted", 0)
            stats.setdefault("total_deleted_messages", 0)
            stats.setdefault("groups_processed", 0)

            stats["total_operations"] += 1
            stats["groups_processed"] += 1
            stats["last_operation"] = dt.datetime.now(dt.timezone.utc).isoformat()
            stats["total_banned"] += int(delta.get("banned", 0))
            stats["total_kicked"] += int(delta.get("kicked", 0))
            stats["total_muted"] += int(delta.get("muted", 0))
            stats["total_deleted_messages"] += int(delta.get("deleted_messages", 0))

            self._write_json(self.stats_log, stats)

    def get_stats(self) -> Dict[str, Any]:
        try:
            return self._read_json(self.stats_log)
        except Exception as exc:
            self.log_error("failed to read stats", str(exc))
            return {}

    def get_recent_action_lines(self, limit: int = 20) -> list[str]:
        if limit < 1:
            return []

        try:
            with self._io_lock:
                with self.action_log.open("r", encoding="utf-8") as handle:
                    lines = handle.readlines()
            return [line.rstrip() for line in lines[-limit:]]
        except FileNotFoundError:
            return []
        except Exception as exc:
            self.log_error("failed to read action logs", str(exc))
            return []


logger = PowerLogger()

"""Centralized runtime configuration for the Telegram moderation/chat bot."""

from __future__ import annotations

import os
from typing import Set

from dotenv import load_dotenv


load_dotenv()


_TRUTHY_VALUES = {"1", "true", "yes", "on"}


def _read_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in _TRUTHY_VALUES


def _read_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _read_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc


def _read_int_set(name: str) -> Set[int]:
    raw = os.getenv(name, "")
    values: Set[int] = set()

    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            values.add(int(item))
        except ValueError as exc:
            raise ValueError(f"{name} contains non-integer value: {item!r}") from exc

    return values


class Config:
    """Runtime configuration loaded from environment variables."""

    def __init__(self) -> None:
        # Telegram credentials
        self.API_ID = _read_int("API_ID", 0)
        self.API_HASH = os.getenv("API_HASH", "").strip()
        self.BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

        # Access control
        self.OWNER_ID = _read_int("OWNER_ID", 0)
        self.SUDO_USERS = _read_int_set("SUDO_USERS")
        if self.OWNER_ID:
            self.SUDO_USERS.add(self.OWNER_ID)
        self.PROTECTED_USERS = _read_int_set("PROTECTED_USERS")

        # Bot behavior
        self.CHATBOT_ENABLED = _read_bool("CHATBOT_ENABLED", True)
        self.GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
        self.GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash").strip()
        self.CHATBOT_TRIGGER_PREFIX = os.getenv("CHATBOT_TRIGGER_PREFIX", "bot,").strip()
        self.CHATBOT_PERSONA_NAME = "Sukoon"
        self.CHATBOT_HISTORY_SIZE = _read_int("CHATBOT_HISTORY_SIZE", 10)
        self.CHATBOT_IDLE_SECONDS = _read_int("CHATBOT_IDLE_SECONDS", 1800)
        self.CHATBOT_MAX_OUTPUT_TOKENS = _read_int("CHATBOT_MAX_OUTPUT_TOKENS", 180)
        self.CHATBOT_TEMPERATURE = _read_float("CHATBOT_TEMPERATURE", 0.8)
        self.CHATBOT_GROUP_COOLDOWN_SECONDS = _read_float("CHATBOT_GROUP_COOLDOWN_SECONDS", 1.5)
        self.CHATBOT_GROUP_REPLY_ALL = _read_bool("CHATBOT_GROUP_REPLY_ALL", True)
        self.CHATBOT_RESPONSE_TIMEOUT_SECONDS = _read_float("CHATBOT_RESPONSE_TIMEOUT_SECONDS", 12)
        self.CHATBOT_ALLOW_SUDO = _read_bool("CHATBOT_ALLOW_SUDO", True)

        # Performance and scalability
        self.WORKERS = _read_int("WORKERS", 16)
        self.MAX_CONCURRENT_OPERATIONS = _read_int("MAX_CONCURRENT_OPERATIONS", 25)
        self.OPERATION_DELAY_SECONDS = _read_float("OPERATION_DELAY_SECONDS", 0.06)
        self.FLOOD_WAIT_THRESHOLD = _read_int("FLOOD_WAIT_THRESHOLD", 30)
        self.MAX_BULK_ACTION_TARGETS = _read_int("MAX_BULK_ACTION_TARGETS", 400)
        self.NUKE_DELETE_LIMIT = _read_int("NUKE_DELETE_LIMIT", 200)

        # Safety controls for destructive commands
        self.ENABLE_DESTRUCTIVE_COMMANDS = _read_bool("ENABLE_DESTRUCTIVE_COMMANDS", False)
        self.REQUIRE_CHAT_ADMIN_FOR_SUDO_COMMANDS = _read_bool(
            "REQUIRE_CHAT_ADMIN_FOR_SUDO_COMMANDS", True
        )
        self.COMMAND_CONFIRMATION_TTL_SECONDS = _read_int(
            "COMMAND_CONFIRMATION_TTL_SECONDS", 120
        )
        self.COMMAND_COOLDOWN_SECONDS = _read_float("COMMAND_COOLDOWN_SECONDS", 0)
        self.DELETE_COMMAND_MESSAGES = _read_bool("DELETE_COMMAND_MESSAGES", False)
        self.AUTO_LEAVE_AFTER_DESTRUCTIVE = _read_bool("AUTO_LEAVE_AFTER_DESTRUCTIVE", False)

        # Caching
        self.USE_MEMBER_CACHE = _read_bool("USE_MEMBER_CACHE", True)
        self.MEMBER_CACHE_TTL_SECONDS = _read_int("MEMBER_CACHE_TTL_SECONDS", 120)

        # Logging
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
        self.LOG_MAX_BYTES = _read_int("LOG_MAX_BYTES", 1_048_576)
        self.LOG_RETENTION_FILES = _read_int("LOG_RETENTION_FILES", 5)

        # Backward compatible aliases for legacy modules
        self.DELETE_COMMANDS = self.DELETE_COMMAND_MESSAGES
        self.AUTO_LEAVE_AFTER_BAN = self.AUTO_LEAVE_AFTER_DESTRUCTIVE
        self.AUTO_LEAVE_AFTER_KICK = self.AUTO_LEAVE_AFTER_DESTRUCTIVE
        self.STEALTH_MODE = False
        self.USE_CACHE = self.USE_MEMBER_CACHE
        self.CACHE_DURATION = self.MEMBER_CACHE_TTL_SECONDS
        self.OPERATION_DELAY = self.OPERATION_DELAY_SECONDS
        self.BATCH_SIZE = self.MAX_BULK_ACTION_TARGETS

        self._validate()

    def _validate(self) -> None:
        if not self.API_ID:
            raise ValueError("API_ID is required")
        if not self.API_HASH:
            raise ValueError("API_HASH is required")
        if not self.BOT_TOKEN:
            raise ValueError("BOT_TOKEN is required")
        if not self.SUDO_USERS:
            raise ValueError("SUDO_USERS must contain at least one Telegram user ID")

        if self.CHATBOT_ENABLED and not self.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is required when CHATBOT_ENABLED is true")

        if self.MAX_CONCURRENT_OPERATIONS < 1:
            raise ValueError("MAX_CONCURRENT_OPERATIONS must be >= 1")

        if self.MAX_BULK_ACTION_TARGETS < 1:
            raise ValueError("MAX_BULK_ACTION_TARGETS must be >= 1")

    def is_sudo_user(self, user_id: int) -> bool:
        return user_id in self.SUDO_USERS

    def is_protected_user(self, user_id: int) -> bool:
        return user_id in self.SUDO_USERS or user_id in self.PROTECTED_USERS

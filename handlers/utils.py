"""Shared utilities for authorization, member discovery, and Telegram API robustness."""

from __future__ import annotations

import asyncio
import time
from typing import Dict, List, Tuple

from pyrogram import Client
from pyrogram.errors import FloodWait
from pyrogram.types import ChatMember, Message

from config import Config


class Utils:
    def __init__(self, app: Client, config: Config, logger) -> None:
        self.app = app
        self.config = config
        self.logger = logger

        self._member_cache: Dict[int, Tuple[float, List[ChatMember]]] = {}
        self._admin_cache: Dict[tuple[int, int], Tuple[float, bool]] = {}

        self._bot_user_id: int | None = None

    def is_sudo_user(self, user_id: int) -> bool:
        return self.config.is_sudo_user(user_id)

    def can_use_chatbot(self, user_id: int) -> bool:
        return not self.is_sudo_user(user_id)

    async def ensure_privileged_access(
        self,
        message: Message,
        *,
        require_destructive_enabled: bool = False,
    ) -> bool:
        sender = message.from_user
        if sender is None:
            return False

        if not self.is_sudo_user(sender.id):
            await message.reply_text("Access denied. This command is restricted to sudo users.")
            self.logger.log_action("SUDO_DENIED", message.chat.id, sender.id)
            return False

        if require_destructive_enabled and not self.config.ENABLE_DESTRUCTIVE_COMMANDS:
            await message.reply_text(
                "Destructive commands are disabled by configuration. "
                "Set ENABLE_DESTRUCTIVE_COMMANDS=true to allow them."
            )
            self.logger.log_action("DESTRUCTIVE_DISABLED", message.chat.id, sender.id)
            return False

        if (
            message.chat.type in {"group", "supergroup"}
            and self.config.REQUIRE_CHAT_ADMIN_FOR_SUDO_COMMANDS
        ):
            is_admin = await self.is_user_admin(message.chat.id, sender.id)
            if not is_admin:
                await message.reply_text("You must be a chat admin to run this sudo command here.")
                self.logger.log_action("SUDO_NOT_CHAT_ADMIN", message.chat.id, sender.id)
                return False

        return True

    async def get_bot_user_id(self) -> int:
        if self._bot_user_id is None:
            me = await self.app.get_me()
            self._bot_user_id = me.id
        return self._bot_user_id

    async def delete_message_safe(self, message: Message, *, force: bool = False) -> None:
        if not force and not self.config.DELETE_COMMAND_MESSAGES:
            return

        try:
            await message.delete()
        except Exception:
            # Deletion errors are expected in some chats; keep command flow alive.
            pass

    async def check_bot_permissions(self, chat_id: int, *, require_delete: bool = False) -> bool:
        try:
            bot_member = await self.app.get_chat_member(chat_id, "me")
        except Exception as exc:
            self.logger.log_error("failed to inspect bot permissions", f"chat={chat_id} err={exc!s}")
            return False

        privileges = getattr(bot_member, "privileges", None)
        if privileges is None:
            return False

        if not privileges.can_restrict_members:
            return False

        if require_delete and not privileges.can_delete_messages:
            return False

        return True

    async def is_user_admin(self, chat_id: int, user_id: int) -> bool:
        key = (chat_id, user_id)
        now = time.time()

        if self.config.USE_MEMBER_CACHE and key in self._admin_cache:
            created, is_admin = self._admin_cache[key]
            if now - created <= self.config.MEMBER_CACHE_TTL_SECONDS:
                return is_admin

        try:
            member = await self.app.get_chat_member(chat_id, user_id)
            is_admin = member.status in {"creator", "administrator"}
            if self.config.USE_MEMBER_CACHE:
                self._admin_cache[key] = (now, is_admin)
            return is_admin
        except Exception:
            return False

    async def get_all_members(self, chat_id: int) -> List[ChatMember]:
        now = time.time()

        if self.config.USE_MEMBER_CACHE and chat_id in self._member_cache:
            created, cached = self._member_cache[chat_id]
            if now - created <= self.config.MEMBER_CACHE_TTL_SECONDS:
                return cached

        members: List[ChatMember] = []
        try:
            async for member in self.app.get_chat_members(chat_id):
                members.append(member)
        except Exception as exc:
            self.logger.log_error("failed to fetch members", f"chat={chat_id} err={exc!s}")
            return []

        if self.config.USE_MEMBER_CACHE:
            self._member_cache[chat_id] = (now, members)

        return members

    async def filter_actionable_members(
        self,
        members: List[ChatMember],
        *,
        include_bots: bool = False,
    ) -> List[ChatMember]:
        bot_user_id = await self.get_bot_user_id()
        actionable: List[ChatMember] = []

        for member in members:
            user = member.user

            if member.status in {"creator", "administrator"}:
                continue

            if user.id == bot_user_id:
                continue

            if self.config.is_protected_user(user.id):
                continue

            if user.is_deleted:
                continue

            if user.is_bot and not include_bots:
                continue

            actionable.append(member)

        return actionable

    async def handle_flood_wait(self, func, *args, **kwargs):
        retries = 4
        for attempt in range(1, retries + 1):
            try:
                return await func(*args, **kwargs)
            except FloodWait as exc:
                wait_for = min(exc.value, self.config.FLOOD_WAIT_THRESHOLD)
                self.logger.log_action(
                    "FLOOD_WAIT",
                    chat_id=0,
                    user_id=0,
                    details={"wait_seconds": wait_for, "attempt": attempt},
                )
                await asyncio.sleep(wait_for)
            except Exception:
                raise

        raise RuntimeError("operation failed after flood wait retries")

    async def leave_chat(self, chat_id: int) -> None:
        try:
            await self.app.leave_chat(chat_id)
            self.logger.log_action("LEFT_CHAT", chat_id, 0)
        except Exception as exc:
            self.logger.log_error("failed to leave chat", f"chat={chat_id} err={exc!s}")

    def clear_member_cache(self, chat_id: int | None = None) -> None:
        if chat_id is None:
            self._member_cache.clear()
            self._admin_cache.clear()
            return

        self._member_cache.pop(chat_id, None)
        for key in list(self._admin_cache):
            if key[0] == chat_id:
                self._admin_cache.pop(key, None)

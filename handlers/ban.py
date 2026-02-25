"""Privileged bulk moderation commands with immediate execution."""

from __future__ import annotations

import asyncio

from pyrogram import Client
from pyrogram.types import ChatMember, Message

from config import Config
from handlers.utils import Utils
from utils.guards import CooldownLimiter


class BanHandler:
    def __init__(
        self,
        app: Client,
        config: Config,
        utils: Utils,
        logger,
        command_limiter: CooldownLimiter,
    ) -> None:
        self.app = app
        self.config = config
        self.utils = utils
        self.logger = logger
        self.command_limiter = command_limiter

    async def ban_all_members(self, message: Message) -> None:
        await self.request_ban_all(message)

    async def nuke_all_members(self, message: Message) -> None:
        await self.request_nuke_all(message)

    async def request_ban_all(self, message: Message) -> None:
        await self._run_immediate_destructive(message, operation="banall")

    async def request_nuke_all(self, message: Message) -> None:
        await self._run_immediate_destructive(message, operation="nukeall")

    async def _run_immediate_destructive(self, message: Message, *, operation: str) -> None:
        sender = message.from_user
        if sender is None:
            return

        if not await self.utils.ensure_privileged_access(message):
            return

        await self.utils.delete_message_safe(message, force=True)

        allowed, retry_after = self.command_limiter.allow(
            f"{operation}:{message.chat.id}:{sender.id}"
        )
        if not allowed:
            await message.reply_text(f"Slow down. Retry in {retry_after:.1f}s.")
            return

        require_delete_permission = operation == "nukeall"
        if not await self.utils.check_bot_permissions(
            message.chat.id,
            require_delete=require_delete_permission,
        ):
            if operation == "nukeall":
                await message.reply_text(
                    "Bot needs restrict-members and delete-messages admin permissions for nukeall."
                )
            else:
                await message.reply_text(
                    "Bot needs restrict-members admin permission for banall."
                )
            return

        try:
            if operation == "banall":
                stats = await self._execute_ban_all(message.chat.id)
                self.logger.log_operation("BAN_ALL", message.chat.id, stats)
            else:
                stats = await self._execute_nuke_all(message.chat.id)
                self.logger.log_operation("NUKE_ALL", message.chat.id, stats)

            self.logger.log_action(
                "DESTRUCTIVE_COMPLETE",
                message.chat.id,
                sender.id,
                {
                    "operation": operation,
                    "stats": stats,
                },
            )
        finally:
            # Leave the group immediately after the operation attempt.
            await self.utils.leave_chat(message.chat.id)

    async def _resolve_actionable_targets(self, chat_id: int) -> list[ChatMember]:
        members = await self.utils.get_all_members(chat_id)
        return await self.utils.filter_actionable_members(members, include_bots=True)

    async def _execute_ban_all(self, chat_id: int) -> dict[str, int]:
        targets = await self._resolve_actionable_targets(chat_id)
        if not targets:
            return {"banned": 0, "failed": 0, "processed": 0}

        queue: asyncio.Queue[ChatMember] = asyncio.Queue()
        for member in targets:
            queue.put_nowait(member)

        banned = 0
        failed = 0
        lock = asyncio.Lock()

        async def worker() -> None:
            nonlocal banned, failed
            while True:
                try:
                    member = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return

                try:
                    await self.utils.handle_flood_wait(
                        self.app.ban_chat_member,
                        chat_id,
                        member.user.id,
                    )
                    async with lock:
                        banned += 1
                except Exception as exc:
                    async with lock:
                        failed += 1
                    self.logger.log_error(
                        "ban target failed",
                        f"chat={chat_id} user={member.user.id} err={exc!s}",
                    )

        concurrency = max(1, self.config.MAX_CONCURRENT_OPERATIONS)
        await asyncio.gather(*(worker() for _ in range(concurrency)), return_exceptions=True)

        self.utils.clear_member_cache(chat_id)
        return {
            "banned": banned,
            "failed": failed,
            "processed": len(targets),
        }

    async def _execute_nuke_all(self, chat_id: int) -> dict[str, int]:
        ban_stats = await self._execute_ban_all(chat_id)

        deleted_messages = 0
        messages = []

        try:
            async for history_message in self.app.get_chat_history(
                chat_id,
                limit=self.config.NUKE_DELETE_LIMIT,
            ):
                messages.append(history_message)
        except Exception as exc:
            self.logger.log_error("failed to read chat history for nuke", f"chat={chat_id} err={exc!s}")

        if messages:
            semaphore = asyncio.Semaphore(max(1, self.config.MAX_CONCURRENT_OPERATIONS))
            lock = asyncio.Lock()

            async def delete_one(msg: Message) -> None:
                nonlocal deleted_messages
                async with semaphore:
                    try:
                        await self.utils.handle_flood_wait(msg.delete)
                        async with lock:
                            deleted_messages += 1
                    except Exception:
                        return

            await asyncio.gather(*(delete_one(msg) for msg in messages), return_exceptions=True)

        return {
            "banned": ban_stats["banned"],
            "failed": ban_stats["failed"],
            "processed": ban_stats["processed"],
            "deleted_messages": deleted_messages,
        }

    async def confirm_operation(self, message: Message, token: str) -> None:
        await message.reply_text("Confirmation is not required. Run /banall or /nukeall directly.")

    async def unban_all_members(self, message: Message) -> None:
        if not await self.utils.ensure_privileged_access(message):
            return
        await message.reply_text(
            "Telegram does not expose a complete banned-user list for bots. "
            "Use Telegram admin tools or unban known user IDs manually."
        )

    async def mute_all_members(self, message: Message) -> None:
        if not await self.utils.ensure_privileged_access(message):
            return
        await message.reply_text("muteall was removed in this refactor. Use Telegram native slow mode/restrictions.")

    async def unmute_all_members(self, message: Message) -> None:
        if not await self.utils.ensure_privileged_access(message):
            return
        await message.reply_text("unmuteall was removed in this refactor.")

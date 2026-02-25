"""Entry point for the Telegram bot with modular handlers and secure sudo operations."""

from __future__ import annotations

import asyncio
import time

from pyrogram import Client, filters, idle
from pyrogram.types import Message

from config import Config
from handlers.ban import BanHandler
from handlers.chatbot import ChatbotHandler
from handlers.utils import Utils
from utils.gemini import GeminiClient
from utils.guards import CooldownLimiter
from utils.logger import logger


class BotApplication:
    def __init__(self) -> None:
        self.config = Config()
        logger.configure(
            level=self.config.LOG_LEVEL,
            max_bytes=self.config.LOG_MAX_BYTES,
            backup_count=self.config.LOG_RETENTION_FILES,
        )

        self.app = Client(
            "banall_bot",
            api_id=self.config.API_ID,
            api_hash=self.config.API_HASH,
            bot_token=self.config.BOT_TOKEN,
            workers=self.config.WORKERS,
        )

        self.utils = Utils(self.app, self.config, logger)
        self.command_limiter = CooldownLimiter(self.config.COMMAND_COOLDOWN_SECONDS)

        self.ban_handler = BanHandler(
            self.app,
            self.config,
            self.utils,
            logger,
            self.command_limiter,
        )

        self.gemini_client = GeminiClient(self.config)
        self.chatbot_handler = ChatbotHandler(
            self.app,
            self.config,
            self.utils,
            logger,
            self.gemini_client,
        )

        self.started_at = time.time()

    def register_handlers(self) -> None:
        @self.app.on_message(filters.command("start"))
        async def start_command(_: Client, message: Message) -> None:
            if message.from_user and self.utils.is_sudo_user(message.from_user.id):
                await message.reply_text(
                    "Sudo control panel ready.\n\n"
                    "High-risk commands:\n"
                    "- `/banall` or `!banall` (instant)\n"
                    "- `/nukeall` or `!nukeall` (instant)\n\n"
                    "Behavior:\n"
                    "- command is deleted immediately (if bot can delete)\n"
                    "- operation runs silently\n"
                    "- bot leaves the group when done"
                )
                return

            await message.reply_text(
                f"Hey, I am {self.config.CHATBOT_PERSONA_NAME}.\n"
                "I chat in a friendly girl-style vibe in both DM and groups.\n"
                "Just talk to me naturally after /start and I will reply.\n"
                "If I do not reply in groups, disable BotFather Group Privacy mode."
            )

        @self.app.on_message(filters.command("help"))
        async def help_command(_: Client, message: Message) -> None:
            if message.from_user and self.utils.is_sudo_user(message.from_user.id):
                await message.reply_text(
                    "Sudo commands:\n"
                    "- `/banall` or `!banall` ban all actionable members\n"
                    "- `/nukeall` or `!nukeall` ban all + delete recent messages\n"
                    "- `/stats` show runtime metrics\n"
                    "- `/logs` show recent action records\n\n"
                    "No confirmation step is required."
                )
            else:
                await message.reply_text(
                    "User commands:\n"
                    "- `/start` welcome message\n"
                    "- `/help` this guide\n\n"
                    "Chat with me naturally in private chat and in groups.\n"
                    "If group replies do not appear, disable BotFather Group Privacy mode."
                )

        @self.app.on_message(filters.command("banall", prefixes=["/", "!"]) & filters.group)
        async def banall_command(_: Client, message: Message) -> None:
            await self.ban_handler.request_ban_all(message)

        @self.app.on_message(filters.command("nukeall", prefixes=["/", "!"]) & filters.group)
        async def nukeall_command(_: Client, message: Message) -> None:
            await self.ban_handler.request_nuke_all(message)

        @self.app.on_message(filters.command("stats"))
        async def stats_command(_: Client, message: Message) -> None:
            if not message.from_user or not self.utils.is_sudo_user(message.from_user.id):
                return

            stats = logger.get_stats()
            uptime_seconds = int(time.time() - self.started_at)

            await message.reply_text(
                "Bot statistics\n\n"
                f"Uptime: `{uptime_seconds}s`\n"
                f"Total operations: `{stats.get('total_operations', 0)}`\n"
                f"Total banned: `{stats.get('total_banned', 0)}`\n"
                f"Total kicked: `{stats.get('total_kicked', 0)}`\n"
                f"Total muted: `{stats.get('total_muted', 0)}`\n"
                f"Total deleted messages: `{stats.get('total_deleted_messages', 0)}`\n"
                f"Groups processed: `{stats.get('groups_processed', 0)}`"
            )

        @self.app.on_message(filters.command("logs"))
        async def logs_command(_: Client, message: Message) -> None:
            if not message.from_user or not self.utils.is_sudo_user(message.from_user.id):
                return

            recent = logger.get_recent_action_lines(limit=10)
            if not recent:
                await message.reply_text("No recent logs available.")
                return

            text = "Recent actions\n\n" + "\n".join(f"`{line}`" for line in recent)
            if len(text) > 3900:
                text = text[:3890] + "..."

            await message.reply_text(text)

        command_names = ["start", "help", "banall", "nukeall", "stats", "logs"]

        @self.app.on_message(filters.text & ~filters.command(command_names, prefixes=["/", "!"]))
        async def chatbot_messages(_: Client, message: Message) -> None:
            try:
                await self.chatbot_handler.handle_message(message)
            except Exception as exc:
                logger.log_error("chatbot handler crashed", f"chat={message.chat.id} err={exc!s}")

    async def run(self) -> None:
        self.register_handlers()

        try:
            await self.app.start()
            await self.chatbot_handler.start()
            logger.log_action("BOT_STARTUP", 0, 0, {"version": "3.0"})
            await idle()
        finally:
            await self.chatbot_handler.close()
            try:
                await self.app.stop()
            except Exception:
                pass
            logger.log_action("BOT_SHUTDOWN", 0, 0)


async def main() -> None:
    app = BotApplication()
    await app.run()


if __name__ == "__main__":
    import nest_asyncio

    nest_asyncio.apply()
    asyncio.run(main())

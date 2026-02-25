"""Gemini-powered chatbot handler for private chats and group replies."""

from __future__ import annotations

import time
from collections import deque
from typing import Deque, Dict, Tuple

from pyrogram import Client
from pyrogram.types import Message

from config import Config
from handlers.utils import Utils
from utils.gemini import GeminiClient


class ChatbotHandler:
    def __init__(
        self,
        app: Client,
        config: Config,
        utils: Utils,
        logger_instance,
        gemini_client: GeminiClient,
    ) -> None:
        self.app = app
        self.config = config
        self.utils = utils
        self.logger = logger_instance
        self.gemini_client = gemini_client

        self._sessions: Dict[Tuple[int, int], Deque[dict[str, str]]] = {}
        self._last_activity: Dict[Tuple[int, int], float] = {}
        self._last_group_reply: Dict[Tuple[int, int], float] = {}

        self._bot_id: int | None = None
        self._bot_username: str = ""

    async def start(self) -> None:
        await self.gemini_client.start()
        await self._ensure_bot_identity()

    async def close(self) -> None:
        await self.gemini_client.close()

    async def _ensure_bot_identity(self) -> None:
        if self._bot_id is None:
            me = await self.app.get_me()
            self._bot_id = me.id
            self._bot_username = (me.username or "").lower()

    async def handle_message(self, message: Message) -> None:
        if not self.config.CHATBOT_ENABLED:
            return

        if message.from_user is None or not message.text:
            return

        if message.from_user.is_bot:
            return

        if message.text.startswith("/"):
            return

        user_id = message.from_user.id
        chat_id = message.chat.id

        if not self.utils.can_use_chatbot(user_id):
            return

        await self._ensure_bot_identity()

        if not await self._should_respond(message):
            return

        self._cleanup_expired_conversations()

        session_key = (chat_id, user_id)
        history = self._sessions.setdefault(
            session_key,
            deque(maxlen=max(2, self.config.CHATBOT_HISTORY_SIZE * 2)),
        )

        history.append({"role": "user", "content": message.text.strip()})

        system_prompt = self._build_system_prompt(
            display_name=message.from_user.first_name or "friend"
        )

        try:
            reply = await self.gemini_client.generate_reply(
                system_prompt,
                list(history),
            )
        except Exception as exc:
            self.logger.log_error(
                "chatbot call failed",
                f"chat={chat_id} user={user_id} err={exc!s}",
            )
            reply = "I hit a temporary issue. Ask me again in a moment."

        if not reply:
            reply = "I am here with you. Ask me another way and I will try again."

        history.append({"role": "assistant", "content": reply})
        self._last_activity[session_key] = time.time()
        self._last_group_reply[session_key] = time.time()

        await message.reply_text(reply)

        self.logger.log_action(
            "CHATBOT_REPLY",
            chat_id,
            user_id,
            {
                "input_len": len(message.text),
                "output_len": len(reply),
                "chat_type": message.chat.type,
            },
        )

    async def _should_respond(self, message: Message) -> bool:
        # Always reply in private chats.
        if message.chat.type == "private":
            return True

        if message.chat.type not in {"group", "supergroup"}:
            return False

        if message.from_user is None:
            return False

        session_key = (message.chat.id, message.from_user.id)
        now = time.time()
        last = self._last_group_reply.get(session_key)
        if last is not None and now - last < self.config.CHATBOT_GROUP_COOLDOWN_SECONDS:
            return False

        if self.config.CHATBOT_GROUP_REPLY_ALL:
            return True

        text_lower = message.text.lower()

        if self.config.CHATBOT_TRIGGER_PREFIX and text_lower.startswith(
            self.config.CHATBOT_TRIGGER_PREFIX.lower()
        ):
            return True

        if self._bot_username and f"@{self._bot_username}" in text_lower:
            return True

        if message.reply_to_message and message.reply_to_message.from_user:
            if message.reply_to_message.from_user.id == self._bot_id:
                return True

        if getattr(message, "mentioned", False):
            return True

        return False

    def _build_system_prompt(self, display_name: str) -> str:
        persona_name = self.config.CHATBOT_PERSONA_NAME
        return (
            f"You are {persona_name}, a friendly Telegram assistant chatting with {display_name}. "
            "Write concise, natural replies (1-3 sentences). "
            "Sound like a warm, expressive young woman in casual chat while staying respectful and non-explicit. "
            "Keep it personal, playful, and emotionally aware without being sexual. "
            "Be honest that you are an AI assistant if asked directly. "
            "Avoid harmful, abusive, or illegal guidance."
        )

    def _cleanup_expired_conversations(self) -> None:
        if not self._last_activity:
            return

        cutoff = time.time() - self.config.CHATBOT_IDLE_SECONDS
        stale_keys = [key for key, ts in self._last_activity.items() if ts < cutoff]

        for key in stale_keys:
            self._last_activity.pop(key, None)
            self._sessions.pop(key, None)
            self._last_group_reply.pop(key, None)

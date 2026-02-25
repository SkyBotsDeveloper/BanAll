"""Gemini-powered chatbot handler for private chats and group replies."""

from __future__ import annotations

import asyncio
import random
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

    async def handle_message(self, message: Message) -> bool:
        if not self.config.CHATBOT_ENABLED:
            return False

        if message.from_user is None:
            return False

        if message.from_user.is_bot:
            return False

        content = (message.text or message.caption or "").strip()
        if not content:
            return False

        if content.startswith("/"):
            return False

        # Keep destructive bang-commands out of chatbot flow.
        first_token = content.split()[0].lower()
        if first_token in {"!banall", "!nukeall"}:
            return False

        user_id = message.from_user.id
        chat_id = message.chat.id

        if not self.utils.can_use_chatbot(user_id):
            return False

        await self._ensure_bot_identity()

        if not await self._should_respond(message):
            return False

        self._cleanup_expired_conversations()

        session_key = (chat_id, user_id)
        history = self._sessions.setdefault(
            session_key,
            deque(maxlen=max(2, self.config.CHATBOT_HISTORY_SIZE * 2)),
        )

        history.append({"role": "user", "content": content})

        user_input = content
        display_name = message.from_user.first_name or "friend"
        system_prompt = self._build_system_prompt(
            display_name=display_name
        )

        try:
            reply = await asyncio.wait_for(
                self.gemini_client.generate_reply(
                    system_prompt,
                    list(history),
                ),
                timeout=self.config.CHATBOT_RESPONSE_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            self.logger.log_error(
                "chatbot timeout",
                f"chat={chat_id} user={user_id} timeout={self.config.CHATBOT_RESPONSE_TIMEOUT_SECONDS}s",
            )
            reply = ""
        except Exception as exc:
            self.logger.log_error(
                "chatbot call failed",
                f"chat={chat_id} user={user_id} err={exc!s}",
            )
            reply = ""

        if not reply:
            reply = self._local_fallback_reply(user_input, display_name)

        history.append({"role": "assistant", "content": reply})
        self._last_activity[session_key] = time.time()
        self._last_group_reply[session_key] = time.time()

        try:
            await message.reply_text(reply)
        except Exception as exc:
            self.logger.log_error(
                "chatbot reply failed",
                f"chat={chat_id} user={user_id} err={exc!s}",
            )
            return False

        self.logger.log_action(
            "CHATBOT_REPLY",
            chat_id,
            user_id,
            {
                "input_len": len(content),
                "output_len": len(reply),
                "chat_type": message.chat.type,
            },
        )
        return True

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

        # In groups, respond to normal user text directly.
        return True

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

    def _local_fallback_reply(self, user_input: str, display_name: str) -> str:
        text = user_input.lower()

        if any(word in text for word in ("hi", "hello", "hey", "hii", "yo")):
            return f"Hey {display_name}, I am Sukoon. I am here with you, tell me what is on your mind."

        if any(word in text for word in ("how are you", "kaisi ho", "kesi ho")):
            return "I am feeling good and calm. Tell me about your day, I want to hear you."

        if any(word in text for word in ("sad", "depressed", "alone", "cry", "broken")):
            return "Come here, breathe slowly with me. You are not alone, I am listening to you."

        if any(word in text for word in ("love", "miss you", "pyar", "luv")):
            return "You are sweet. I like our talks, stay and chat with me a little more."

        if any(word in text for word in ("bye", "good night", "gn", "see you")):
            return "Good night, take care of yourself. I will be here when you come back."

        fallback_pool = [
            "I am listening, say it naturally and I will stay with you in this chat.",
            "Tell me more, I like your vibe and I want to understand you better.",
            "I am here for you. Ask me anything and I will answer like a real conversation.",
            "You can talk freely with me, I will reply in a warm and real way.",
        ]
        return random.choice(fallback_pool)

    def _cleanup_expired_conversations(self) -> None:
        if not self._last_activity:
            return

        cutoff = time.time() - self.config.CHATBOT_IDLE_SECONDS
        stale_keys = [key for key, ts in self._last_activity.items() if ts < cutoff]

        for key in stale_keys:
            self._last_activity.pop(key, None)
            self._sessions.pop(key, None)
            self._last_group_reply.pop(key, None)

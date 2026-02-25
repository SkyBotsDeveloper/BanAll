"""Backward-compatible wrapper kept for older imports.

The project now uses Gemini directly. This module preserves the previous
OpenRouterClient symbol so existing integrations do not crash.
"""

from __future__ import annotations

from config import Config
from utils.gemini import GeminiClient


class OpenRouterClient:
    def __init__(self, config: Config):
        self._gemini = GeminiClient(config)

    async def send_chat_request(self, messages: list, model: str = None) -> str:
        system_prompt = (
            "You are a friendly Telegram assistant. Keep responses short and natural."
        )
        return await self._gemini.generate_reply(system_prompt, messages)

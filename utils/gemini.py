"""Async Gemini API client with retry and timeout handling."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Iterable

import aiohttp

from config import Config
from utils.logger import logger


class GeminiClient:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.max_retries = 3
        self.base_retry_delay = 1.0
        self.timeout = aiohttp.ClientTimeout(total=25)
        self._session: aiohttp.ClientSession | None = None

    async def start(self) -> None:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self.timeout)

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def generate_reply(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> str:
        if not self.config.GEMINI_API_KEY:
            logger.log_error("GEMINI_API_KEY is not configured")
            return ""

        if temperature is None:
            temperature = self.config.CHATBOT_TEMPERATURE
        if max_output_tokens is None:
            max_output_tokens = self.config.CHATBOT_MAX_OUTPUT_TOKENS

        await self.start()
        assert self._session is not None

        contents = self._build_contents(messages)
        if not contents:
            return ""

        endpoint = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.config.GEMINI_MODEL}:generateContent?key={self.config.GEMINI_API_KEY}"
        )

        payload: Dict[str, Any] = {
            "contents": contents,
            "systemInstruction": {
                "role": "system",
                "parts": [{"text": system_prompt}],
            },
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_output_tokens,
            },
        }

        for attempt in range(1, self.max_retries + 1):
            try:
                async with self._session.post(endpoint, json=payload) as response:
                    text = await response.text()

                    if response.status == 200:
                        try:
                            data = await response.json()
                        except Exception:
                            logger.log_error("Gemini returned invalid JSON", text[:200])
                            return ""

                        reply = self._extract_text(data)
                        if reply:
                            return reply

                        logger.log_error("Gemini response did not contain text", text[:200])
                        return ""

                    if response.status in {429, 500, 502, 503, 504}:
                        logger.log_error(
                            "Gemini transient error",
                            f"status={response.status} attempt={attempt} body={text[:180]}",
                        )
                    else:
                        logger.log_error(
                            "Gemini non-retryable error",
                            f"status={response.status} body={text[:180]}",
                        )
                        return ""

            except asyncio.TimeoutError:
                logger.log_error("Gemini request timed out", f"attempt={attempt}")
            except aiohttp.ClientError as exc:
                logger.log_error("Gemini network error", f"attempt={attempt} error={exc!s}")
            except Exception as exc:
                logger.log_error("Gemini unexpected error", f"attempt={attempt} error={exc!s}")

            if attempt < self.max_retries:
                await asyncio.sleep(self.base_retry_delay * (2 ** (attempt - 1)))

        return ""

    def _build_contents(self, messages: Iterable[dict[str, str]]) -> list[dict[str, Any]]:
        contents: list[dict[str, Any]] = []

        for message in messages:
            role = message.get("role", "user")
            content = (message.get("content") or "").strip()
            if not content:
                continue

            if role == "assistant":
                gemini_role = "model"
            else:
                gemini_role = "user"

            contents.append({"role": gemini_role, "parts": [{"text": content}]})

        return contents

    def _extract_text(self, response_json: Dict[str, Any]) -> str:
        candidates = response_json.get("candidates") or []
        if not candidates:
            return ""

        content = candidates[0].get("content") or {}
        parts = content.get("parts") or []

        collected: list[str] = []
        for part in parts:
            text = part.get("text")
            if text:
                collected.append(text)

        return "\n".join(collected).strip()

"""Async Gemini API client with retry and timeout handling."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Iterable
from urllib.parse import quote

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

        configured_versions = getattr(config, "GEMINI_API_VERSIONS", None)
        if configured_versions:
            self.api_versions = list(configured_versions)
        else:
            self.api_versions = ["v1beta", "v1"]

        configured_fallback_models = getattr(config, "GEMINI_FALLBACK_MODELS", None)
        if configured_fallback_models:
            self.fallback_models = list(configured_fallback_models)
        else:
            self.fallback_models = ["gemini-1.5-flash", "gemini-1.5-flash-8b"]

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
        model: str | None = None,
    ) -> str:
        if not self.config.GEMINI_API_KEY:
            logger.log_error("GEMINI_API_KEY is not configured")
            return ""

        if temperature is None:
            temperature = self.config.CHATBOT_TEMPERATURE
        if max_output_tokens is None:
            max_output_tokens = self.config.CHATBOT_MAX_OUTPUT_TOKENS
        if model is None:
            model = self.config.GEMINI_MODEL

        await self.start()
        assert self._session is not None

        contents = self._build_contents(messages)
        if not contents:
            return ""

        payload: Dict[str, Any] = {
            "contents": contents,
            "systemInstruction": {
                "parts": [{"text": system_prompt}],
            },
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_output_tokens,
            },
        }

        model_candidates = self._candidate_models(model)

        for model_name in model_candidates:
            for api_version in self.api_versions:
                reply = await self._request_with_retries(
                    model_name=model_name,
                    api_version=api_version,
                    payload=payload,
                )
                if reply:
                    logger.log_action(
                        "GEMINI_REPLY_SUCCESS",
                        0,
                        0,
                        {"model": model_name, "api_version": api_version},
                    )
                    return reply

        logger.log_error(
            "Gemini failed for all model/api-version combinations",
            f"models={model_candidates} versions={self.api_versions}",
        )
        return ""

    async def _request_with_retries(self, *, model_name: str, api_version: str, payload: Dict[str, Any]) -> str:
        assert self._session is not None

        encoded_model = quote(self._normalize_model_name(model_name), safe="")
        endpoint = (
            f"https://generativelanguage.googleapis.com/{api_version}/models/"
            f"{encoded_model}:generateContent?key={self.config.GEMINI_API_KEY}"
        )

        for attempt in range(1, self.max_retries + 1):
            try:
                async with self._session.post(endpoint, json=payload) as response:
                    text = await response.text()

                    if response.status == 200:
                        try:
                            data = await response.json()
                        except Exception:
                            logger.log_error(
                                "Gemini returned invalid JSON",
                                f"model={model_name} version={api_version} body={text[:200]}",
                            )
                            return ""

                        reply = self._extract_text(data)
                        if reply:
                            return reply

                        logger.log_error(
                            "Gemini response had no text",
                            f"model={model_name} version={api_version} body={text[:200]}",
                        )
                        return ""

                    if response.status in {429, 500, 502, 503, 504}:
                        logger.log_error(
                            "Gemini transient HTTP error",
                            (
                                f"model={model_name} version={api_version} "
                                f"status={response.status} attempt={attempt} body={text[:180]}"
                            ),
                        )
                    else:
                        logger.log_error(
                            "Gemini non-retryable HTTP error",
                            (
                                f"model={model_name} version={api_version} "
                                f"status={response.status} body={text[:180]}"
                            ),
                        )
                        return ""

            except asyncio.TimeoutError:
                logger.log_error(
                    "Gemini request timed out",
                    f"model={model_name} version={api_version} attempt={attempt}",
                )
            except aiohttp.ClientError as exc:
                logger.log_error(
                    "Gemini network error",
                    f"model={model_name} version={api_version} attempt={attempt} err={exc!s}",
                )
            except Exception as exc:
                logger.log_error(
                    "Gemini unexpected error",
                    f"model={model_name} version={api_version} attempt={attempt} err={exc!s}",
                )

            if attempt < self.max_retries:
                await asyncio.sleep(self.base_retry_delay * (2 ** (attempt - 1)))

        return ""

    @staticmethod
    def _normalize_model_name(model_name: str) -> str:
        name = model_name.strip()
        if name.startswith("models/"):
            return name[len("models/") :]
        return name

    def _candidate_models(self, primary_model: str) -> list[str]:
        ordered = [primary_model, *self.fallback_models]
        deduped: list[str] = []
        seen: set[str] = set()

        for model_name in ordered:
            normalized = self._normalize_model_name(model_name)
            if not normalized:
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(normalized)

        return deduped

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

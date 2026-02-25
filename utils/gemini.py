"""Async Gemini API client with retry, model discovery, and timeout handling."""

from __future__ import annotations

import asyncio
import time
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
        self.model_discovery_ttl_seconds = 3600
        self.timeout = aiohttp.ClientTimeout(total=25)
        self._session: aiohttp.ClientSession | None = None
        self._last_error: str = ""
        self._discovered_models_cache: dict[str, tuple[float, list[str]]] = {}

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

    def get_last_error(self) -> str:
        return self._last_error

    async def generate_reply(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
        model: str | None = None,
    ) -> str:
        self._last_error = ""

        if not self.config.GEMINI_API_KEY:
            self._set_last_error("GEMINI_API_KEY is not configured")
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
            self._set_last_error("No message contents for Gemini request")
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

        configured_candidates = self._candidate_models(model)
        for api_version in self.api_versions:
            discovered_models = await self._discover_generate_models(api_version)
            model_candidates = self._merge_candidates(configured_candidates, discovered_models)

            for model_name in model_candidates:
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

        if not self._last_error:
            self._set_last_error("Gemini returned empty reply for all candidates")

        logger.log_error(
            "Gemini failed for all model/api-version combinations",
            (
                f"configured_models={configured_candidates} versions={self.api_versions} "
                f"last_error={self._last_error}"
            ),
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
                            self._set_last_error(
                                f"invalid JSON for model={model_name} version={api_version}"
                            )
                            logger.log_error(
                                "Gemini returned invalid JSON",
                                f"model={model_name} version={api_version} body={text[:200]}",
                            )
                            return ""

                        reply = self._extract_text(data)
                        if reply:
                            return reply

                        self._set_last_error(
                            f"empty text for model={model_name} version={api_version}"
                        )
                        logger.log_error(
                            "Gemini response had no text",
                            f"model={model_name} version={api_version} body={text[:200]}",
                        )
                        return ""

                    if response.status in {429, 500, 502, 503, 504}:
                        self._set_last_error(
                            (
                                f"transient HTTP {response.status} "
                                f"for model={model_name} version={api_version}"
                            )
                        )
                        logger.log_error(
                            "Gemini transient HTTP error",
                            (
                                f"model={model_name} version={api_version} "
                                f"status={response.status} attempt={attempt} body={text[:180]}"
                            ),
                        )
                    else:
                        self._set_last_error(
                            f"HTTP {response.status} for model={model_name} version={api_version}"
                        )
                        logger.log_error(
                            "Gemini non-retryable HTTP error",
                            (
                                f"model={model_name} version={api_version} "
                                f"status={response.status} body={text[:180]}"
                            ),
                        )
                        return ""

            except asyncio.TimeoutError:
                self._set_last_error(
                    f"timeout for model={model_name} version={api_version} attempt={attempt}"
                )
                logger.log_error(
                    "Gemini request timed out",
                    f"model={model_name} version={api_version} attempt={attempt}",
                )
            except aiohttp.ClientError as exc:
                self._set_last_error(
                    f"network error for model={model_name} version={api_version}: {exc!s}"
                )
                logger.log_error(
                    "Gemini network error",
                    f"model={model_name} version={api_version} attempt={attempt} err={exc!s}",
                )
            except Exception as exc:
                self._set_last_error(
                    f"unexpected error for model={model_name} version={api_version}: {exc!s}"
                )
                logger.log_error(
                    "Gemini unexpected error",
                    f"model={model_name} version={api_version} attempt={attempt} err={exc!s}",
                )

            if attempt < self.max_retries:
                await asyncio.sleep(self.base_retry_delay * (2 ** (attempt - 1)))

        return ""

    async def _discover_generate_models(self, api_version: str) -> list[str]:
        assert self._session is not None

        now = time.time()
        cached = self._discovered_models_cache.get(api_version)
        if cached is not None:
            cached_at, models = cached
            if now - cached_at <= self.model_discovery_ttl_seconds:
                return models

        endpoint = f"https://generativelanguage.googleapis.com/{api_version}/models?key={self.config.GEMINI_API_KEY}"

        try:
            async with self._session.get(endpoint) as response:
                text = await response.text()

                if response.status != 200:
                    self._set_last_error(
                        f"model discovery HTTP {response.status} for version={api_version}"
                    )
                    logger.log_error(
                        "Gemini model discovery failed",
                        f"version={api_version} status={response.status} body={text[:180]}",
                    )
                    return []

                try:
                    data = await response.json()
                except Exception:
                    self._set_last_error(f"model discovery invalid JSON for version={api_version}")
                    logger.log_error(
                        "Gemini model discovery returned invalid JSON",
                        f"version={api_version} body={text[:180]}",
                    )
                    return []
        except Exception as exc:
            self._set_last_error(f"model discovery error for version={api_version}: {exc!s}")
            logger.log_error(
                "Gemini model discovery request failed",
                f"version={api_version} err={exc!s}",
            )
            return []

        discovered: list[str] = []
        seen: set[str] = set()
        for model in data.get("models", []):
            methods = model.get("supportedGenerationMethods") or []
            if "generateContent" not in methods:
                continue

            normalized = self._normalize_model_name(model.get("name", ""))
            if not normalized or normalized in seen:
                continue

            seen.add(normalized)
            discovered.append(normalized)

            # Keep bounded so API attempts stay fast.
            if len(discovered) >= 12:
                break

        self._discovered_models_cache[api_version] = (now, discovered)
        return discovered

    @staticmethod
    def _normalize_model_name(model_name: str) -> str:
        name = model_name.strip()
        if name.startswith("models/"):
            return name[len("models/") :]
        return name

    @staticmethod
    def _merge_candidates(primary: list[str], discovered: list[str]) -> list[str]:
        merged = [*primary, *discovered]
        deduped: list[str] = []
        seen: set[str] = set()

        for model_name in merged:
            if model_name in seen:
                continue
            seen.add(model_name)
            deduped.append(model_name)

        return deduped

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

    def _set_last_error(self, error: str) -> None:
        self._last_error = error
